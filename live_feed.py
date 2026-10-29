"""Live TRIAS (VDV) departure feed for the LED departure board.

Standard library only. Talks to a TRIAS 1.2 endpoint (text/xml POST) and
converts StopEvent responses into tz-aware UTC journey/call objects.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from xml.sax.saxutils import escape

LOG = logging.getLogger(__name__)

TRIAS_NS = "http://www.vdv.de/trias"
SIRI_NS = "http://www.siri.org.uk/siri"

_NS = {"t": TRIAS_NS, "s": SIRI_NS}

ACTIVE_END_GRACE_SECONDS = 30


class TriasError(Exception):
    """Raised when a TRIAS request or response fails."""


@dataclass
class LiveCall:
    station_id: int
    arrival: datetime
    departure: datetime
    planned_arrival: datetime
    planned_departure: datetime


@dataclass
class LiveJourney:
    journey_ref: str
    line_ref: str
    line_name: str
    destination: str
    calls: list[LiveCall] = field(default_factory=list)

    @property
    def delay_seconds(self) -> float:
        """Largest departure delay over all calls, never negative."""
        if not self.calls:
            return 0.0
        delays = [
            (call.departure - call.planned_departure).total_seconds()
            for call in self.calls
        ]
        return max(0.0, max(delays))


@dataclass(frozen=True)
class LiveConnection:
    id: str
    origin_station_id: int
    destination_station_id: int
    first_boundary_station_id: int
    second_boundary_station_id: int
    departure: datetime
    arrival: datetime
    transfer_arrival: datetime
    transfer_departure: datetime
    delay_seconds: float
    first_journey_ref: str
    second_journey_ref: str
    first_calls: tuple[LiveCall, ...] = ()
    second_calls: tuple[LiveCall, ...] = ()


@dataclass
class LiveRouteSnapshot:
    journeys: list[LiveJourney] = field(default_factory=list)
    connections: list[LiveConnection] = field(default_factory=list)


def station_key(stop_point_ref: str) -> str:
    """Return the station-level part of a platform-level stop ref."""
    return ":".join((stop_point_ref or "").strip().split(":")[:3])


# ---------------------------------------------------------------------------
# parsing helpers


def _text(element):
    if element is None or element.text is None:
        return None
    value = element.text.strip()
    return value or None


def _child_text(parent, path):
    if parent is None:
        return None
    return _text(parent.find(path, _NS))


def _parse_time(value):
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _service_time(call_at_stop, service_tag, part):
    """Read e.g. CallAtStop/ServiceDeparture/EstimatedTime."""
    node = call_at_stop.find("t:%s/t:%s" % (service_tag, part), _NS)
    value = _text(node)
    return _parse_time(value) if value else None


def _check_errors(root):
    status_element = root.find(".//s:Status", _NS)
    if status_element is None:
        status_element = root.find(
            ".//{%s}ServiceDelivery/s:Status" % TRIAS_NS, _NS
        )
    status = _text(status_element)
    message = None
    for error in root.iter("{%s}ErrorMessage" % TRIAS_NS):
        text = _text(error)
        if text:
            message = text
            break
    if (status is not None and status.lower() == "false") or message:
        raise TriasError(message or "TRIAS request failed (Status false)")


def _call_from_element(call_at_stop, station_id):
    arr_est = _service_time(call_at_stop, "ServiceArrival", "EstimatedTime")
    arr_plan = _service_time(call_at_stop, "ServiceArrival", "TimetabledTime")
    dep_est = _service_time(call_at_stop, "ServiceDeparture", "EstimatedTime")
    dep_plan = _service_time(call_at_stop, "ServiceDeparture", "TimetabledTime")

    arrival = arr_est or arr_plan or dep_est or dep_plan
    departure = dep_est or dep_plan or arrival
    planned_arrival = arr_plan or dep_plan or arrival
    planned_departure = dep_plan or planned_arrival

    if arrival is None or departure is None:
        raise TriasError("CallAtStop without any usable time")
    if departure < arrival:
        departure = arrival
    if planned_departure < planned_arrival:
        planned_departure = planned_arrival

    return LiveCall(
        station_id=station_id,
        arrival=arrival,
        departure=departure,
        planned_arrival=planned_arrival,
        planned_departure=planned_departure,
    )


def parse_stop_events(xml_bytes, station_refs):
    """Parse a TRIAS StopEventResponse into journeys of mapped calls."""
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        raise TriasError("Invalid TRIAS XML: %s" % exc) from exc

    _check_errors(root)

    journeys = []
    for stop_event in root.iter("{%s}StopEvent" % TRIAS_NS):
        service = stop_event.find("t:Service", _NS)
        journey_ref = _child_text(service, "t:JourneyRef")
        line_ref = _child_text(service, "t:ServiceSection/t:LineRef")
        line_name = _child_text(service, "t:ServiceSection/t:PublishedLineName/t:Text")
        destination = _child_text(service, "t:DestinationText/t:Text")
        if not journey_ref:
            continue

        call_elements = []
        this_call = stop_event.find("t:ThisCall/t:CallAtStop", _NS)
        if this_call is not None:
            call_elements.append(this_call)
        for onward in stop_event.findall("t:OnwardCall/t:CallAtStop", _NS):
            call_elements.append(onward)

        calls = []
        for call_at_stop in call_elements:
            ref = _child_text(call_at_stop, "t:StopPointRef")
            if not ref:
                continue
            key = station_key(ref)
            if key not in station_refs:
                continue
            calls.append(_call_from_element(call_at_stop, station_refs[key]))

        if len(calls) < 2:
            continue

        journeys.append(
            LiveJourney(
                journey_ref=journey_ref,
                line_ref=line_ref or "",
                line_name=line_name or "",
                destination=destination or "",
                calls=calls,
            )
        )
    return journeys


# ---------------------------------------------------------------------------
# client


def _format_utc(value):
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class TriasClient:
    def __init__(self, endpoint, requestor_key, timeout=15.0):
        self.endpoint = endpoint
        self.requestor_key = requestor_key
        self.timeout = timeout

    def build_stop_event_request(
        self,
        stop_ref,
        line_refs,
        dep_arr_time,
        number_of_results=12,
    ):
        lines = "".join(
            "<Line><LineRef>%s</LineRef></Line>" % escape(line_ref)
            for line_ref in line_refs
        )
        xml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Trias version="1.2" xmlns="%s" xmlns:siri="%s">'
            "<ServiceRequest>"
            "<siri:RequestTimestamp>%s</siri:RequestTimestamp>"
            "<siri:RequestorRef>%s</siri:RequestorRef>"
            "<RequestPayload><StopEventRequest>"
            "<Location><LocationRef><StopPointRef>%s</StopPointRef></LocationRef>"
            "<DepArrTime>%s</DepArrTime></Location>"
            "<Params><LineFilter>%s<Exclude>false</Exclude></LineFilter>"
            "<NumberOfResults>%d</NumberOfResults>"
            "<StopEventType>departure</StopEventType>"
            "<IncludeRealtimeData>true</IncludeRealtimeData>"
            "<IncludeOnwardCalls>true</IncludeOnwardCalls>"
            "</Params></StopEventRequest></RequestPayload>"
            "</ServiceRequest></Trias>"
        ) % (
            TRIAS_NS,
            SIRI_NS,
            _format_utc(datetime.now(timezone.utc)),
            escape(self.requestor_key),
            escape(stop_ref),
            _format_utc(dep_arr_time),
            lines,
            int(number_of_results),
        )
        return xml.encode("utf-8")

    def stop_events(
        self,
        stop_ref,
        line_refs,
        dep_arr_time,
        number_of_results=12,
    ):
        body = self.build_stop_event_request(
            stop_ref, line_refs, dep_arr_time, number_of_results
        )
        request = urllib.request.Request(
            self.endpoint,
            data=body,
            method="POST",
            headers={
                "Content-Type": "text/xml; charset=utf-8",
                "Accept": "text/xml",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return response.read()
        except (urllib.error.HTTPError, urllib.error.URLError, OSError) as exc:
            raise TriasError(
                "TRIAS request to %s failed: %s" % (self.endpoint, exc)
            ) from exc


# ---------------------------------------------------------------------------
# live feed


class LiveFeed:
    def __init__(
        self,
        client,
        routes,
        lookback_minutes=45,
        lead_seconds=120,
        number_of_results=12,
        closure_provider=None,
    ):
        self.client = client
        self.routes = routes
        self.lookback_minutes = lookback_minutes
        self.lead_seconds = lead_seconds
        self.number_of_results = number_of_results
        self.closure_provider = closure_provider

    @staticmethod
    def _clip_journey(route, journey, origin_id, destination_id):
        if not journey.calls or journey.calls[0].station_id != origin_id:
            return None
        station_ids = [station["id"] for station in route["stations"]]
        station_order = {
            station_id: index for index, station_id in enumerate(station_ids)
        }
        if origin_id not in station_order or destination_id not in station_order:
            raise ValueError("Journey endpoint is not part of the configured route")

        try:
            terminal_index = next(
                index
                for index, call in enumerate(journey.calls)
                if call.station_id == destination_id
            )
        except StopIteration:
            return None
        if terminal_index == 0:
            return None

        direction = (
            1
            if station_order[destination_id] > station_order[origin_id]
            else -1
        )
        calls = journey.calls[:terminal_index + 1]
        call_indices = [station_order[call.station_id] for call in calls]
        if any(
            (later - earlier) * direction < 0
            for earlier, later in zip(call_indices, call_indices[1:])
        ):
            return None

        names = {
            station["id"]: station.get("name", str(station["id"]))
            for station in route["stations"]
        }
        return LiveJourney(
            journey_ref=f"{journey.journey_ref}@{origin_id}-{destination_id}",
            line_ref=journey.line_ref,
            line_name=journey.line_name,
            destination=names[destination_id],
            calls=calls,
        )

    @staticmethod
    def _journey_is_active(journey, now, lead_seconds):
        if not journey.calls:
            return False
        start = journey.calls[0].departure - timedelta(seconds=lead_seconds)
        end = journey.calls[-1].arrival + timedelta(
            seconds=ACTIVE_END_GRACE_SECONDS
        )
        return start <= now <= end

    def _pair_legs(
        self,
        first_legs,
        second_legs,
        origin_id,
        destination_id,
        now,
    ):
        transfer_buffer = timedelta(minutes=5)
        available_second_legs = sorted(
            second_legs,
            key=lambda journey: (journey.calls[0].departure, journey.journey_ref),
        )
        used_second_refs = set()
        connections = []
        for first in sorted(
            first_legs,
            key=lambda journey: (
                journey.calls[-1].arrival,
                journey.journey_ref,
            ),
        ):
            earliest_departure = first.calls[-1].arrival + transfer_buffer
            second = next(
                (
                    journey
                    for journey in available_second_legs
                    if journey.journey_ref not in used_second_refs
                    and journey.calls[0].departure >= earliest_departure
                ),
                None,
            )
            if second is None:
                continue
            used_second_refs.add(second.journey_ref)
            connections.append(
                LiveConnection(
                    id=f"{first.journey_ref}|{second.journey_ref}",
                    origin_station_id=origin_id,
                    destination_station_id=destination_id,
                    first_boundary_station_id=first.calls[-1].station_id,
                    second_boundary_station_id=second.calls[0].station_id,
                    departure=first.calls[0].departure,
                    arrival=second.calls[-1].arrival,
                    transfer_arrival=first.calls[-1].arrival,
                    transfer_departure=second.calls[0].departure,
                    delay_seconds=max(
                        first.delay_seconds,
                        second.delay_seconds,
                    ),
                    first_journey_ref=first.journey_ref,
                    second_journey_ref=second.journey_ref,
                    first_calls=tuple(first.calls),
                    second_calls=tuple(second.calls),
                )
            )

        return [
            connection
            for connection in connections
            if (
                connection.departure - timedelta(seconds=self.lead_seconds)
                <= now
                <= connection.arrival + timedelta(
                    seconds=ACTIVE_END_GRACE_SECONDS
                )
            )
        ]

    def fetch(self, now):
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)

        result = {}
        closures = (
            self.closure_provider()
            if self.closure_provider is not None
            else {}
        )
        for route in self.routes:
            route_id = route["id"]
            trias = route["trias"]
            line_refs = trias["line_refs"]
            origin_refs = trias["origin_refs"]
            station_refs = {
                station_key(station["trias_ref"]): station["id"]
                for station in route["stations"]
            }
            dep_arr_time = now - timedelta(minutes=self.lookback_minutes)

            closure = closures.get(route_id)
            stations = route["stations"]
            station_ids = [station["id"] for station in stations]
            station_order = {
                station_id: index for index, station_id in enumerate(station_ids)
            }
            refs_by_station_id = {
                station["id"]: station["trias_ref"] for station in stations
            }
            if closure is None:
                requests = [
                    (station_refs[station_key(origin_ref)], origin_ref)
                    for origin_ref in origin_refs
                ]
            else:
                first_boundary, second_boundary = closure
                if first_boundary not in station_order or second_boundary not in station_order:
                    raise ValueError(f"Closure contains an unknown station on route {route_id}")
                low_boundary, high_boundary = sorted(
                    closure,
                    key=station_order.__getitem__,
                )
                left_endpoint = station_ids[0]
                right_endpoint = station_ids[-1]
                origin_ref_by_id = {
                    station_refs[station_key(origin_ref)]: origin_ref
                    for origin_ref in origin_refs
                }
                request_station_ids = (
                    left_endpoint,
                    right_endpoint,
                    low_boundary,
                    high_boundary,
                )
                requests = []
                seen_station_ids = set()
                for station_id in request_station_ids:
                    if station_id in seen_station_ids:
                        continue
                    seen_station_ids.add(station_id)
                    requests.append(
                        (
                            station_id,
                            origin_ref_by_id.get(
                                station_id,
                                refs_by_station_id[station_id],
                            ),
                        )
                    )

            journeys_by_origin = {}
            failures = 0
            for origin_id, origin_ref in requests:
                try:
                    payload = self.client.stop_events(
                        origin_ref,
                        line_refs,
                        dep_arr_time,
                        self.number_of_results,
                    )
                    journeys = parse_stop_events(payload, station_refs)
                except TriasError as exc:
                    failures += 1
                    LOG.warning(
                        "TRIAS request failed for route %s origin %s: %s",
                        route_id,
                        origin_ref,
                        exc,
                    )
                    continue
                journeys_by_origin[origin_id] = journeys

            if failures and failures == len(requests):
                raise TriasError(
                    "All TRIAS requests failed for route %s" % route_id
                )

            if closure is None:
                left_endpoint = station_ids[0]
                right_endpoint = station_ids[-1]
                by_ref = {}
                for origin_id, journeys in journeys_by_origin.items():
                    if origin_id == left_endpoint:
                        destination_id = right_endpoint
                    elif origin_id == right_endpoint:
                        destination_id = left_endpoint
                    else:
                        continue
                    for journey in journeys:
                        clipped = self._clip_journey(
                            route,
                            journey,
                            origin_id,
                            destination_id,
                        )
                        if clipped is not None:
                            by_ref[clipped.journey_ref] = clipped
                active = [
                    journey
                    for journey in by_ref.values()
                    if self._journey_is_active(
                        journey,
                        now,
                        self.lead_seconds,
                    )
                ]
                active.sort(key=lambda journey: journey.calls[0].departure)
                result[route_id] = LiveRouteSnapshot(journeys=active)
                continue

            first_boundary, second_boundary = closure
            low_boundary, high_boundary = sorted(
                closure,
                key=station_order.__getitem__,
            )
            left_endpoint = station_ids[0]
            right_endpoint = station_ids[-1]
            leg_specs = (
                (left_endpoint, low_boundary),
                (low_boundary, left_endpoint),
                (right_endpoint, high_boundary),
                (high_boundary, right_endpoint),
            )
            legs_by_pair = {}
            all_segments = {}
            for origin_id, destination_id in leg_specs:
                clipped_by_ref = {}
                for journey in journeys_by_origin.get(origin_id, []):
                    clipped = self._clip_journey(
                        route,
                        journey,
                        origin_id,
                        destination_id,
                    )
                    if clipped is not None:
                        clipped_by_ref[clipped.journey_ref] = clipped
                legs_by_pair[(origin_id, destination_id)] = list(
                    clipped_by_ref.values()
                )
                all_segments.update(clipped_by_ref)

            connections = self._pair_legs(
                legs_by_pair[(left_endpoint, low_boundary)],
                legs_by_pair[(high_boundary, right_endpoint)],
                left_endpoint,
                right_endpoint,
                now,
            )
            connections.extend(
                self._pair_legs(
                    legs_by_pair[(right_endpoint, high_boundary)],
                    legs_by_pair[(low_boundary, left_endpoint)],
                    right_endpoint,
                    left_endpoint,
                    now,
                )
            )
            active_segments = [
                journey
                for journey in all_segments.values()
                if self._journey_is_active(
                    journey,
                    now,
                    self.lead_seconds,
                )
            ]
            active_segments.sort(key=lambda journey: journey.calls[0].departure)
            connections.sort(key=lambda connection: connection.departure)
            result[route_id] = LiveRouteSnapshot(
                journeys=active_segments,
                connections=connections,
            )
        return result


# ---------------------------------------------------------------------------
# configuration / CLI


def _read_dotenv(path):
    values = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return values
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key.strip()] = value
    return values


def load_requestor_key(env_var="TRIAS_REQUESTOR_KEY", dotenv_path=None):
    value = os.environ.get(env_var)
    if value:
        return value
    path = Path(dotenv_path) if dotenv_path else Path(__file__).with_name(".env")
    key = _read_dotenv(path).get(env_var)
    if not key:
        raise TriasError(
            "Missing TRIAS requestor key: set %s in the environment or in %s"
            % (env_var, path)
        )
    return key


def _position_text(route, journey, now):
    names = {station["id"]: station.get("name", str(station["id"])) for station in route["stations"]}
    calls = journey.calls
    if now < calls[0].departure:
        return "at %s" % names.get(calls[0].station_id, calls[0].station_id)
    for current, following in zip(calls, calls[1:]):
        if current.departure <= now <= following.arrival:
            return "between %s and %s" % (
                names.get(current.station_id, current.station_id),
                names.get(following.station_id, following.station_id),
            )
    return "at %s" % names.get(calls[-1].station_id, calls[-1].station_id)


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    meta_path = Path(__file__).with_name("meta.json")
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print("Cannot read %s: %s" % (meta_path, exc))
        return 1

    try:
        trias = meta["trias"]
        endpoint = trias["endpoint"]
        routes = meta["routes"]
    except KeyError as exc:
        print(
            "meta.json is missing required key %s (need meta['trias']['endpoint'] "
            "and meta['routes'])" % exc
        )
        return 1

    lookback = trias.get("lookback_minutes", 45)
    try:
        requestor_key = trias.get("requestor_key") or load_requestor_key()
    except TriasError as exc:
        print(exc)
        return 1

    client = TriasClient(endpoint, requestor_key)
    feed = LiveFeed(client, routes, lookback_minutes=lookback)
    now = datetime.now(timezone.utc)
    try:
        journeys_by_route = feed.fetch(now)
    except TriasError as exc:
        print("TRIAS error: %s" % exc)
        return 1

    for route in routes:
        route_id = route["id"]
        print("Route %s (%s)" % (route_id, route.get("name", "")))
        for journey in journeys_by_route.get(route_id, []):
            delay = journey.delay_seconds
            print(
                "  %s -> %s  %+ds  %s"
                % (
                    journey.line_name or journey.line_ref,
                    journey.destination,
                    int(round(delay)),
                    _position_text(route, journey, now),
                )
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
