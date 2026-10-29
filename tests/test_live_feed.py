"""Unit tests for live_feed.py (no network access)."""

import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import live_feed
from live_feed import (
    LiveFeed,
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
            first_departure = journey.calls[0].departure
            last_arrival = journey.calls[-1].arrival
            if (first_departure - lead) <= now <= (last_arrival + timedelta(seconds=30)):
                expected_refs.append(journey.journey_ref)

        client = FakeClient(MOOS)
        feed = LiveFeed(client, [self.route])
        result = feed.fetch(now)

        journeys = result[7]
        self.assertEqual([j.journey_ref for j in journeys], expected_refs)
        self.assertEqual(len(journeys), len(expected_refs))
        self.assertGreater(len(journeys), 0)
        self.assertLess(len(journeys), 12)
        departures = [j.calls[0].departure for j in journeys]
        self.assertEqual(departures, sorted(departures))
        # Both origins were queried with lookback applied.
        self.assertEqual(len(client.calls), 2)
        for _, _, dep_arr_time, _ in client.calls:
            self.assertEqual(dep_arr_time, now - timedelta(minutes=45))

    def test_fetch_merges_duplicate_journey_refs(self):
        parsed = parse_stop_events(MOOS, STATION_REFS)
        now = self._median_midpoint(parsed)
        result = LiveFeed(FakeClient(MOOS), [self.route]).fetch(now)
        refs = [j.journey_ref for j in result[7]]
        self.assertEqual(len(refs), len(set(refs)))

    def test_fetch_uses_closure_snapshot_for_live_journeys(self):
        parsed = parse_stop_events(MOOS, STATION_REFS)
        now = self._median_midpoint(parsed)
        client = FakeClient(MOOS)
        feed = LiveFeed(
            client,
            [self.route],
            closure_provider=lambda: {7: (10, 11)},
        )

        result = feed.fetch(now)

        self.assertGreater(len(result[7]), 0)
        self.assertEqual(len(client.calls), 2)
        self.assertTrue(
            all(journey.calls[-1].station_id == 10 for journey in result[7])
        )

    def test_fetch_outside_window_is_empty(self):
        parsed = parse_stop_events(MOOS, STATION_REFS)
        future = max(j.calls[-1].arrival for j in parsed) + timedelta(hours=3)
        result = LiveFeed(FakeClient(MOOS), [self.route]).fetch(future)
        self.assertEqual(result[7], [])

    def test_fetch_continues_after_one_origin_failure(self):
        parsed = parse_stop_events(MOOS, STATION_REFS)
        now = self._median_midpoint(parsed)
        client = FakeClient(MOOS, fail_refs=["de:08311:30300"])
        result = LiveFeed(client, [self.route]).fetch(now)
        self.assertGreater(len(result[7]), 0)

    def test_fetch_raises_when_all_origins_fail(self):
        client = FakeClient(MOOS, fail_refs=["de:08311:30800", "de:08311:30300"])
        with self.assertRaises(TriasError):
            LiveFeed(client, [self.route]).fetch(
                datetime(2026, 10, 27, 9, 30, tzinfo=timezone.utc)
            )

    def test_closure_truncates_journeys_at_each_directional_terminal(self):
        outbound = parse_stop_events(MOOS, STATION_REFS)[0]
        inbound = parse_stop_events(LASS, STATION_REFS)[0]

        outbound_part = LiveFeed._truncate_at_closure(
            self.route, outbound, (10, 11)
        )
        inbound_part = LiveFeed._truncate_at_closure(
            self.route, inbound, (10, 11)
        )

        self.assertEqual(
            [call.station_id for call in outbound_part.calls],
            list(range(11)),
        )
        self.assertEqual(
            [call.station_id for call in inbound_part.calls],
            list(range(21, 10, -1)),
        )
        self.assertEqual(outbound_part.destination, self.route["stations"][10]["name"])
        self.assertEqual(inbound_part.destination, self.route["stations"][11]["name"])

    def test_closure_drops_journey_starting_at_boundary_into_closed_track(self):
        journey = parse_stop_events(MOOS, STATION_REFS)[0]
        journey.calls = journey.calls[10:]

        self.assertIsNone(
            LiveFeed._truncate_at_closure(self.route, journey, (10, 11))
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
