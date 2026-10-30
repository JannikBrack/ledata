"""Unit tests for live_feed.py (no network access)."""

import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import live_feed
from live_feed import (
    LiveCall,
    LiveFeed,
    LiveJourney,
    TriasClient,
    TriasError,
    load_requestor_key,
    parse_stop_events,
    station_key,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"
MOOS = (FIXTURES / "stop_events_moosweiher.xml").read_bytes()
LASS = (FIXTURES / "stop_events_lassbergstrasse.xml").read_bytes()

STATION_REFS = {
    "de:08311:30800": 0,
    "de:08311:30801": 1,
    "de:08311:30802": 2,
    "de:08311:30504": 3,
    "de:08311:30503": 4,
    "de:08311:30502": 5,
    "de:08311:30501": 6,
    "de:08311:30500": 7,
    "de:08311:30108": 8,
    "de:08311:6508": 9,
    "de:08311:30106": 10,
    "de:08311:30100": 11,
    "de:08311:30118": 12,
    "de:08311:30119": 13,
    "de:08311:30120": 14,
    "de:08311:30306": 15,
    "de:08311:30305": 16,
    "de:08311:30304": 17,
    "de:08311:30303": 18,
    "de:08311:30302": 19,
    "de:08311:30301": 20,
    "de:08311:30300": 21,
}


class FakeClient:
    """Returns fixture bytes, or raises for configured stop refs."""

    def __init__(self, payload=MOOS, fail_refs=()):
        self.payload = payload
        self.fail_refs = set(fail_refs)
        self.calls = []

    def stop_events(self, stop_ref, line_refs, dep_arr_time, number_of_results=12):
        self.calls.append((stop_ref, list(line_refs), dep_arr_time, number_of_results))
        if stop_ref in self.fail_refs:
            raise TriasError("simulated network failure")
        return self.payload


def _assert_monotonic(testcase, calls):
    for earlier, later in zip(calls, calls[1:]):
        testcase.assertGreaterEqual(later.arrival, earlier.departure)
        testcase.assertGreaterEqual(later.departure, later.arrival)


class ParseTests(unittest.TestCase):
    def test_station_key(self):
        self.assertEqual(station_key("de:08311:30801:1:2"), "de:08311:30801")
        self.assertEqual(station_key("de:08311:30800"), "de:08311:30800")

    def test_moosweiher_ascending(self):
        journeys = parse_stop_events(MOOS, STATION_REFS)
        self.assertEqual(len(journeys), 12)
        for journey in journeys:
            self.assertEqual(len(journey.calls), 22)
            self.assertEqual([c.station_id for c in journey.calls], list(range(22)))
            _assert_monotonic(self, journey.calls)
            self.assertEqual(journey.calls[0].arrival, journey.calls[0].departure)
            for call in journey.calls:
                self.assertEqual(call.arrival.tzinfo, timezone.utc)
                self.assertEqual(call.departure.tzinfo, timezone.utc)
            self.assertEqual(journey.line_name, "1")
            self.assertIn("frb:11001:I:R", journey.line_ref)
            self.assertEqual(journey.destination, "Littenweiler")

    def test_lassbergstrasse_descending(self):
        journeys = parse_stop_events(LASS, STATION_REFS)
        self.assertEqual(len(journeys), 12)
        for journey in journeys:
            self.assertEqual(len(journey.calls), 22)
            self.assertEqual([c.station_id for c in journey.calls], list(range(21, -1, -1)))
            _assert_monotonic(self, journey.calls)
            self.assertEqual(journey.calls[0].arrival, journey.calls[0].departure)
            self.assertEqual(journey.line_name, "1")
            self.assertIn("frb:11001:I:H", journey.line_ref)
            self.assertEqual(journey.destination, "Landwasser")

    def test_unmapped_stop_is_skipped(self):
        partial = dict(STATION_REFS)
        del partial["de:08311:30504"]
        journeys = parse_stop_events(MOOS, partial)
        self.assertEqual(len(journeys), 12)
        for journey in journeys:
            self.assertEqual(len(journey.calls), 21)
            self.assertNotIn(3, [c.station_id for c in journey.calls])

    def test_journey_with_fewer_than_two_mapped_calls_is_dropped(self):
        self.assertEqual(parse_stop_events(MOOS, {"de:08311:30800": 0}), [])
        journeys = parse_stop_events(
            MOOS, {"de:08311:30800": 0, "de:08311:30801": 1}
        )
        self.assertEqual(len(journeys), 12)
        self.assertEqual([c.station_id for c in journeys[0].calls], [0, 1])

    def test_delay_seconds(self):
        journeys = parse_stop_events(MOOS, STATION_REFS)
        journey = journeys[0]
        expected = max(
            0.0,
            max(
                (c.departure - c.planned_departure).total_seconds()
                for c in journey.calls
            ),
        )
        self.assertAlmostEqual(journey.delay_seconds, expected)
        self.assertGreaterEqual(journey.delay_seconds, 0.0)
        self.assertGreater(journey.delay_seconds, 0.0)


class FetchTests(unittest.TestCase):
    def setUp(self):
        self.route = {
            "id": 7,
            "trias": {
                "line_refs": ["frb:11001:I:H", "frb:11001:I:R"],
                "origin_refs": ["de:08311:30800", "de:08311:30300"],
            },
            "stations": [
                {"id": station_id, "name": ref, "trias_ref": ref}
                for ref, station_id in STATION_REFS.items()
            ],
        }

    def _median_midpoint(self, journeys):
        ordered = sorted(journeys, key=lambda j: j.calls[0].departure)
        median = ordered[len(ordered) // 2]
        return median.calls[0].departure + (
            median.calls[-1].arrival - median.calls[0].departure
        ) / 2

    def test_fetch_returns_only_active_journeys(self):
        parsed = parse_stop_events(MOOS, STATION_REFS)
        now = self._median_midpoint(parsed)

        # Independent loop computing the expected active journeys.
        lead = timedelta(seconds=120)
        expected_refs = []
        for journey in sorted(parsed, key=lambda j: j.calls[0].departure):
            origin_id = journey.calls[0].station_id
            if origin_id == 0:
                destination_id = 21
            elif origin_id == 21:
                destination_id = 0
            else:
                continue
            clipped = LiveFeed._clip_journey(
                self.route,
                journey,
                origin_id,
                destination_id,
            )
            if clipped is None:
                continue
            first_departure = clipped.calls[0].departure
            last_arrival = clipped.calls[-1].arrival
            if (first_departure - lead) <= now <= (last_arrival + timedelta(seconds=30)):
                expected_refs.append(clipped.journey_ref)

        client = FakeClient(MOOS)
        feed = LiveFeed(client, [self.route])
        result = feed.fetch(now)

        journeys = result[7].journeys
        self.assertEqual([j.journey_ref for j in journeys], expected_refs)
        self.assertEqual(len(journeys), len(expected_refs))
        self.assertGreater(len(journeys), 0)
        self.assertLess(len(journeys), 12)
        departures = [j.calls[0].departure for j in journeys]
        self.assertEqual(departures, sorted(departures))
        self.assertTrue(
            all(
                (journey.calls[0].station_id, journey.calls[-1].station_id)
                in ((0, 21), (21, 0))
                for journey in journeys
            )
        )
        # Both origins were queried with lookback applied.
        self.assertEqual(len(client.calls), 2)
        for _, _, dep_arr_time, _ in client.calls:
            self.assertEqual(dep_arr_time, now - timedelta(minutes=45))

    def test_fetch_can_be_limited_to_one_route(self):
        other_route = {**self.route, "id": 8}
        client = FakeClient(MOOS)
        feed = LiveFeed(client, [self.route, other_route])
        parsed = parse_stop_events(MOOS, STATION_REFS)
        now = self._median_midpoint(parsed)

        result = feed.fetch(now, route_id=7)

        self.assertEqual(set(result), {7})
        self.assertEqual(len(client.calls), 2)

    def test_fetch_merges_duplicate_journey_refs(self):
        parsed = parse_stop_events(MOOS, STATION_REFS)
        now = self._median_midpoint(parsed)
        result = LiveFeed(FakeClient(MOOS), [self.route]).fetch(now)
        refs = [j.journey_ref for j in result[7].journeys]
        self.assertEqual(len(refs), len(set(refs)))

    def test_fetch_uses_closure_snapshot_for_live_journeys(self):
        parsed = parse_stop_events(MOOS, STATION_REFS)
        now = self._median_midpoint(parsed)
        client = FakeClient(MOOS)
        feed = LiveFeed(
            client,
            [self.route],
            closure_provider=lambda: {7: (10, 13)},
        )

        result = feed.fetch(now)

        self.assertGreater(len(result[7].journeys), 0)
        self.assertEqual(len(client.calls), 4)
        self.assertEqual(
            {call[0] for call in client.calls},
            {
                "de:08311:30800",
                "de:08311:30300",
                "de:08311:30106",
                "de:08311:30119",
            },
        )
        self.assertTrue(
            all(
                journey.calls[-1].station_id == 10
                for journey in result[7].journeys
            )
        )

    def test_fetch_pairs_both_directions_but_keeps_physical_segments(self):
        now = datetime(2026, 10, 27, 8, 0, tzinfo=timezone.utc)

        def segment(ref, station_ids, departure, duration):
            step = duration / (len(station_ids) - 1)
            calls = []
            for index, station_id in enumerate(station_ids):
                time = departure + step * index
                calls.append(LiveCall(station_id, time, time, time, time))
            return LiveJourney(
                journey_ref=ref,
                line_ref="line-1",
                line_name="1",
                destination=str(station_ids[-1]),
                calls=calls,
            )

        journeys_by_origin = {
            "de:08311:30800": [
                segment(
                    "out-first",
                    list(range(11)),
                    now - timedelta(minutes=15),
                    timedelta(minutes=20),
                )
            ],
            "de:08311:30300": [
                segment(
                    "in-first",
                    list(range(21, 12, -1)),
                    now - timedelta(minutes=15),
                    timedelta(minutes=20),
                )
            ],
            "de:08311:30106": [
                segment(
                    "in-second",
                    list(range(10, -1, -1)),
                    now + timedelta(minutes=10),
                    timedelta(minutes=20),
                )
            ],
            "de:08311:30119": [
                segment(
                    "out-second",
                    list(range(13, 22)),
                    now + timedelta(minutes=10),
                    timedelta(minutes=20),
                )
            ],
        }

        class OriginClient:
            def stop_events(self, origin_ref, *_args):
                return origin_ref.encode()

        def parse_for_origin(payload, _station_refs):
            return journeys_by_origin[payload.decode()]

        feed = LiveFeed(
            OriginClient(),
            [self.route],
            lead_seconds=600,
            closure_provider=lambda: {7: (10, 13)},
        )
        with patch.object(live_feed, "parse_stop_events", parse_for_origin):
            snapshot = feed.fetch(now)[7]

        self.assertEqual(len(snapshot.journeys), 4)
        self.assertEqual(
            {
                (connection.origin_station_id, connection.destination_station_id)
                for connection in snapshot.connections
            },
            {(0, 21), (21, 0)},
        )
        self.assertEqual(
            {
                (connection.first_journey_ref, connection.second_journey_ref)
                for connection in snapshot.connections
            },
            {
                ("out-first@0-10", "out-second@13-21"),
                ("in-first@21-13", "in-second@10-0"),
            },
        )

    def test_fetch_outside_window_is_empty(self):
        parsed = parse_stop_events(MOOS, STATION_REFS)
        future = max(j.calls[-1].arrival for j in parsed) + timedelta(hours=3)
        result = LiveFeed(FakeClient(MOOS), [self.route]).fetch(future)
        self.assertEqual(result[7].journeys, [])

    def test_fetch_continues_after_one_origin_failure(self):
        parsed = parse_stop_events(MOOS, STATION_REFS)
        now = self._median_midpoint(parsed)
        client = FakeClient(MOOS, fail_refs=["de:08311:30300"])
        result = LiveFeed(client, [self.route]).fetch(now)
        self.assertGreater(len(result[7].journeys), 0)

    def test_fetch_raises_when_all_origins_fail(self):
        client = FakeClient(MOOS, fail_refs=["de:08311:30800", "de:08311:30300"])
        with self.assertRaises(TriasError):
            LiveFeed(client, [self.route]).fetch(
                datetime(2026, 10, 27, 9, 30, tzinfo=timezone.utc)
            )

    def test_multi_station_closure_truncates_at_each_directional_terminal(self):
        outbound = parse_stop_events(MOOS, STATION_REFS)[0]
        inbound = parse_stop_events(LASS, STATION_REFS)[0]

        outbound_part = LiveFeed._clip_journey(self.route, outbound, 0, 10)
        inbound_part = LiveFeed._clip_journey(self.route, inbound, 21, 13)

        self.assertEqual(
            [call.station_id for call in outbound_part.calls],
            list(range(11)),
        )
        self.assertEqual(
            [call.station_id for call in inbound_part.calls],
            list(range(21, 12, -1)),
        )
        self.assertEqual(outbound_part.destination, self.route["stations"][10]["name"])
        self.assertEqual(inbound_part.destination, self.route["stations"][13]["name"])

    def test_closure_drops_journey_starting_at_boundary_into_closed_track(self):
        journey = parse_stop_events(MOOS, STATION_REFS)[0]
        journey.calls = journey.calls[10:]

        self.assertIsNone(
            LiveFeed._clip_journey(self.route, journey, 10, 0)
        )

    def test_leg_matching_uses_five_minute_buffer_and_never_reuses_second_leg(self):
        now = datetime(2026, 10, 27, 8, 0, tzinfo=timezone.utc)

        def segment(ref, origin, destination, departure, arrival):
            return LiveJourney(
                journey_ref=ref,
                line_ref="line-1",
                line_name="1",
                destination=str(destination),
                calls=[
                    LiveCall(origin, departure, departure, departure, departure),
                    LiveCall(destination, arrival, arrival, arrival, arrival),
                ],
            )

        first_legs = [
            segment(
                "first-1",
                0,
                10,
                now - timedelta(minutes=20),
                now + timedelta(minutes=10),
            ),
            segment(
                "first-2",
                0,
                10,
                now - timedelta(minutes=19),
                now + timedelta(minutes=11),
            ),
        ]
        second_legs = [
            segment(
                "too-soon",
                13,
                21,
                now + timedelta(minutes=14),
                now + timedelta(minutes=24),
            ),
            segment(
                "next",
                13,
                21,
                now + timedelta(minutes=15),
                now + timedelta(minutes=25),
            ),
            segment(
                "later",
                13,
                21,
                now + timedelta(minutes=18),
                now + timedelta(minutes=28),
            ),
        ]
        feed = LiveFeed(FakeClient(), [self.route])

        connections = feed._pair_legs(
            first_legs,
            second_legs,
            0,
            21,
            now,
        )

        self.assertEqual(
            [
                (connection.first_journey_ref, connection.second_journey_ref)
                for connection in connections
            ],
            [("first-1", "next"), ("first-2", "later")],
        )
        self.assertEqual(
            [call.station_id for call in connections[0].first_calls],
            [0, 10],
        )
        self.assertEqual(
            [call.station_id for call in connections[0].second_calls],
            [13, 21],
        )


class RouteConfigTests(unittest.TestCase):
    def test_line_three_has_ordered_live_stops_and_matching_led_positions(self):
        meta = json.loads(
            (Path(__file__).resolve().parents[1] / "meta.json").read_text(
                encoding="utf-8"
            )
        )
        route = next(route for route in meta["routes"] if route["id"] == 2)

        self.assertEqual(route["name"], "Linie 3")
        self.assertEqual(
            [station["name"] for station in route["stations"]],
            [
                "Gundelfinger Straße",
                "Glottertalstraße",
                "Berggasse",
                "Reutebachgasse",
                "Tullastraße",
                "Hornusstraße",
                "Okenstraße",
                "Hauptstraße",
                "Tennenbacher Straße",
                "Europaplatz",
                "Bertoldsbrunnen",
                "Stadttheater",
                "Hauptbahnhof",
                "Eschholzstraße",
                "Rathaus im Stühlinger",
                "Runzmattenweg",
                "Bissierstraße",
                "Rohrgraben",
                "Bugginger Straße",
                "Am Lindenwäldle",
                "VAG-Zentrum",
                "Munzinger Straße",
            ],
        )
        self.assertEqual(
            route["led_layout"],
            [
                7, 8, 7, 5, 7, 9, 6, 13, 7, 8, 7,
                7, 7, 8, 5, 8, 3, 3, 3, 2, 3, 1,
            ],
        )
        self.assertEqual(len(route["stations"]), len(route["led_layout"]))
        self.assertEqual(route["start_of_route"], 0)
        positions = [station["position"] for station in route["stations"]]
        self.assertEqual(
            positions,
            [
                route["start_of_route"] + sum(route["led_layout"][:index])
                for index in range(len(route["stations"]))
            ],
        )
        self.assertTrue(
            all(0 <= position < meta["led"]["count"] for position in positions)
        )
        self.assertEqual(route["color"], [255, 128, 0])
        line_one = next(route for route in meta["routes"] if route["id"] == 0)
        self.assertEqual(
            route["stations"][-1]["position"],
            line_one["stations"][-1]["position"],
        )
        self.assertEqual(
            [station["trias_ref"] for station in route["stations"]],
            [
                "de:08311:750",
                "de:08311:30432",
                "de:08311:30431",
                "de:08311:30202",
                "de:08311:30201",
                "de:08311:30200",
                "de:08311:30203",
                "de:08311:30204",
                "de:08311:30102",
                "de:08311:30101",
                "de:08311:30100",
                "de:08311:30106",
                "de:08311:6508",
                "de:08311:30108",
                "de:08311:30500",
                "de:08311:30501",
                "de:08311:30505",
                "de:08311:30607",
                "de:08311:30600",
                "de:08311:30601",
                "de:08311:30715",
                "de:08311:30716",
            ],
        )
        self.assertEqual(
            route["trias"]["line_refs"],
            ["frb:11003:I:H", "frb:11003:I:R"],
        )
        self.assertEqual(
            route["trias"]["origin_refs"],
            ["de:08311:750", "de:08311:30716"],
        )

    def test_line_two_has_ordered_live_stops_and_matching_led_positions(self):
        meta = json.loads(
            (Path(__file__).resolve().parents[1] / "meta.json").read_text(
                encoding="utf-8"
            )
        )
        route = next(route for route in meta["routes"] if route["id"] == 1)

        self.assertEqual(
            [station["name"] for station in route["stations"]],
            [
                "Hornusstraße",
                "Eugen-Martin-Straße",
                "Zollhallenplatz",
                "Hauptfriedhof",
                "Friedrich-Ebert-Platz",
                "Robert-Koch-Straße",
                "Rathaus im Stühlinger",
                "Eschholzstraße",
                "Hauptbahnhof",
                "Stadttheater",
                "Bertoldsbrunnen",
                "Holzmarkt",
                "Johanneskirche",
                "Lorettostraße",
                "Holbeinstraße",
                "Wonnhalde",
                "Wiesenweg",
                "Klosterplatz",
                "Dorfstraße",
            ],
        )
        self.assertEqual(
            route["led_layout"],
            [13, 4, 9, 4, 14, 9, 14, 8, 8, 7, 5, 5, 4, 4, 4, 4, 4, 3, 1],
        )
        self.assertEqual(len(route["stations"]), len(route["led_layout"]))
        self.assertEqual(route["start_of_route"], 0)
        self.assertEqual(
            [station["position"] for station in route["stations"]],
            [
                0,
                13,
                17,
                26,
                30,
                44,
                53,
                67,
                75,
                83,
                90,
                95,
                100,
                104,
                108,
                112,
                116,
                120,
                123,
            ],
        )
        self.assertEqual(
            [station["position"] for station in route["stations"]],
            [
                route["start_of_route"]
                + sum(route["led_layout"][:index])
                for index in range(len(route["stations"]))
            ],
        )
        self.assertEqual(route["color"], [19, 165, 56])
        self.assertEqual(
            route["trias"]["line_refs"],
            ["frb:11002:I:H", "frb:11002:I:R"],
        )
        self.assertEqual(
            route["trias"]["origin_refs"],
            ["de:08311:30200", "de:08311:30400"],
        )


class RequestTests(unittest.TestCase):
    def test_build_request_contains_filter_and_escaped_key(self):
        client = TriasClient("https://efa-bw.de/trias", "AB&CD")
        body = client.build_stop_event_request(
            "de:08311:30800",
            ["frb:11001:I:H", "frb:11001:I:R"],
            datetime(2026, 10, 27, 9, 0, tzinfo=timezone.utc),
        )
        text = body.decode("utf-8")
        self.assertIn("<Exclude>false</Exclude>", text)
        self.assertIn("frb:11001:I:H", text)
        self.assertIn("frb:11001:I:R", text)
        self.assertIn("AB&amp;CD", text)
        self.assertNotIn("AB&CD", text)
        self.assertIn("<StopEventType>departure</StopEventType>", text)
        self.assertIn("<NumberOfResults>12</NumberOfResults>", text)
        self.assertIn("2026-10-27T09:00:00Z", text)
        self.assertIn('xmlns="http://www.vdv.de/trias"', text)


class ErrorTests(unittest.TestCase):
    def _doc(self, body):
        return (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Trias version="1.2" xmlns="http://www.vdv.de/trias" '
            'xmlns:siri="http://www.siri.org.uk/siri">'
            "<ServiceDelivery>%s</ServiceDelivery></Trias>" % body
        ).encode("utf-8")

    def test_status_false_raises(self):
        payload = self._doc("<siri:Status>false</siri:Status>")
        with self.assertRaises(TriasError):
            parse_stop_events(payload, STATION_REFS)

    def test_error_message_raises(self):
        payload = self._doc(
            "<siri:Status>true</siri:Status><ErrorMessage>boom</ErrorMessage>"
        )
        with self.assertRaises(TriasError) as caught:
            parse_stop_events(payload, STATION_REFS)
        self.assertIn("boom", str(caught.exception))

    def test_broken_xml_raises(self):
        with self.assertRaises(TriasError):
            parse_stop_events(b"<not-xml", STATION_REFS)


class RequestorKeyTests(unittest.TestCase):
    def test_env_wins(self):
        old = os.environ.get("TRIAS_REQUESTOR_KEY")
        os.environ["TRIAS_REQUESTOR_KEY"] = "env-key"
        try:
            self.assertEqual(load_requestor_key(), "env-key")
        finally:
            if old is None:
                os.environ.pop("TRIAS_REQUESTOR_KEY", None)
            else:
                os.environ["TRIAS_REQUESTOR_KEY"] = old

    def test_dotenv_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            dotenv = Path(tmp) / ".env"
            dotenv.write_text(
                "# comment\nTRIAS_REQUESTOR_KEY=dotenv-key\nOTHER=x\n",
                encoding="utf-8",
            )
            old = os.environ.pop("TRIAS_REQUESTOR_KEY", None)
            try:
                self.assertEqual(load_requestor_key(dotenv_path=dotenv), "dotenv-key")
            finally:
                if old is not None:
                    os.environ["TRIAS_REQUESTOR_KEY"] = old

    def test_missing_key_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / ".env"
            old = os.environ.pop("TRIAS_REQUESTOR_KEY", None)
            try:
                with self.assertRaises(TriasError):
                    load_requestor_key(dotenv_path=missing)
            finally:
                if old is not None:
                    os.environ["TRIAS_REQUESTOR_KEY"] = old


if __name__ == "__main__":
    unittest.main()
