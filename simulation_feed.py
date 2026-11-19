"""Lokale Fahrplan-Simulation als Ersatz fuer ausfallende Live-Daten.

Die Simulation erzeugt fuer jede Linie dauerhaft laufende Rundkurse von einer
Endstation zur anderen und zurueck. Linie 1 uebernimmt ihr Zeitmuster aus
fahrplan.json; alle uebrigen Linien werden aus den LED-Abstaenden abgeleitet.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from classes import RouteLiveData, Stop, Trip, parse_utc

DEFAULT_TRAM_COUNT = 4
DEFAULT_SECONDS_PER_LED = 1.9
DEFAULT_DWELL_SECONDS = 10.0
DEFAULT_TERMINUS_DWELL_SECONDS = 45.0


class SimulationFeed:
    """Erzeugt zyklische Rundkurse fuer die LED- und UI-Darstellung."""

    def __init__(
        self,
        routes,
        fahrplan=None,
        tram_count=DEFAULT_TRAM_COUNT,
        seconds_per_led=DEFAULT_SECONDS_PER_LED,
        dwell_seconds=DEFAULT_DWELL_SECONDS,
        terminus_dwell_seconds=DEFAULT_TERMINUS_DWELL_SECONDS,
    ) -> None:
        self.routes = list(routes)
        self.tram_count = max(1, int(tram_count))
        self.seconds_per_led = float(seconds_per_led)
        self.dwell_seconds = max(0.0, float(dwell_seconds))
        self.terminus_dwell_seconds = max(0.0, float(terminus_dwell_seconds))
        self._fahrplan_by_route = {}
        for entry in fahrplan or []:
            try:
                self._fahrplan_by_route[entry["route_id"]] = entry
            except (KeyError, TypeError):
                continue
        self._templates = {
            route.id: self._build_template(route) for route in self.routes
        }

    # ------------------------------------------------------------------
    # template building

    def _build_template(self, route):
        entry = self._fahrplan_by_route.get(route.id)
        if entry and entry.get("trips"):
            return self._template_from_fahrplan(entry)
        return self._template_from_distances(route)

    @staticmethod
    def _template_from_fahrplan(entry):
        """Use the first configured trip as the timing pattern for the route."""
        trip = entry["trips"][0]
        configured = trip.get("stops") or []
        if len(configured) < 2:
            raise ValueError(
                "Fahrplan-Umlauf fuer Linie %s hat zu wenige Halte" % entry["route_id"]
            )

        first_arrival = parse_utc(configured[0]["arrival"])
        template = []
        for stop in configured:
            arrival = parse_utc(stop["arrival"])
            departure = parse_utc(stop["departure"])
            template.append(
                (
                    int(stop["station_id"]),
                    (arrival - first_arrival).total_seconds(),
                    max(0.0, (departure - arrival).total_seconds()),
                )
            )

        last_departure_offset = template[-1][1] + template[-1][2]
        configured_cycle = trip.get("cycle_seconds")
        cycle = (
            float(configured_cycle)
            if configured_cycle
            else max(0.0, last_departure_offset)
        )
        cycle = max(cycle, last_departure_offset)

        first_station_id = template[0][0]
        if template[-1][0] != first_station_id:
            # Der Fahrplan endet am vorletzten Halt; die Rueckfahrt zur
            # Startendstation wird als letzter Halt ergaenzt.
            template.append((first_station_id, cycle, 0.0))
        else:
            cycle = max(cycle, template[-1][1] + template[-1][2])
        return tuple(template), cycle

    def _template_from_distances(self, route):
        stations = route.stations
        count = len(stations)
        if count < 2:
            raise ValueError("Linie %s hat zu wenige Haltestellen" % route.id)

        # 0 .. n-1 und zurueck bis zur Startendstation 0
        sequence = list(range(count)) + list(range(count - 2, -1, -1))
        template = []
        elapsed = 0.0
        for index, station_index in enumerate(sequence):
            station = stations[station_index]
            if index > 0:
                previous = stations[sequence[index - 1]]
                distance = abs(station.position - previous.position)
                elapsed += max(1.0, distance * self.seconds_per_led)
            if index == 0 or station_index == count - 1:
                dwell = self.terminus_dwell_seconds
            elif index == len(sequence) - 1:
                dwell = 0.0
            else:
                dwell = self.dwell_seconds
            template.append((station.id, elapsed, dwell))
            elapsed += dwell
        return tuple(template), elapsed

    # ------------------------------------------------------------------
    # snapshot

    def snapshot(self, now=None, route_id=None) -> dict[int, RouteLiveData]:
        """Liefert fuer jede (oder eine) Linie vier zyklische Trips."""
        now = now or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        now = now.astimezone(timezone.utc)
        day_start = datetime(
            now.year,
            now.month,
            now.day,
            tzinfo=timezone.utc,
        )

        result = {}
        for route in self.routes:
            if route_id is not None and route.id != route_id:
                continue
            template, cycle = self._templates[route.id]
            trips = self._trips_for_route(route, template, cycle, day_start)
            result[route.id] = RouteLiveData(trips=trips, connections=[])
        return result

    def _trips_for_route(self, route, template, cycle, day_start):
        cycle = max(float(cycle), 1.0)
        headway = cycle / self.tram_count
        trips = []
        for index in range(self.tram_count):
            start = day_start + timedelta(seconds=headway * index)
            stops = [
                Stop(
                    station_id,
                    start + timedelta(seconds=arrival_offset),
                    start + timedelta(seconds=arrival_offset + dwell),
                )
                for station_id, arrival_offset, dwell in template
            ]
            trip_id = f"sim-{route.id}-{index}"
            trips.append(
                Trip(
                    id=trip_id,
                    train_id=trip_id,
                    stops=stops,
                    cycle_seconds=cycle,
                    cyclic=True,
                )
            )
        return trips
