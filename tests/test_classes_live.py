"""Tests fuer die Live-Erweiterung von classes.py (ohne Hardware)."""

import importlib.util
import json
import subprocess
import sys
import tempfile
import threading
import time
import types
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from classes import (
    Controller,
    Route,
    RouteConnection,
    RouteLiveData,
    Stop,
    Train,
    Trip,
)
from led_backend import FakeStrip

ROOT = Path(__file__).resolve().parents[1]
T0 = datetime(2026, 1, 1, 5, 0, 0, tzinfo=timezone.utc)


def make_route(trains=None):
    # led_layout [5,5,5] -> Stationen an 0, 5, 10 (Start 0)
    return Route(
        0,
        [5, 5, 5],
        list(trains or []),
        (255, 0, 0),
        0,
        station_names={
            0: "Moosweiher",
            1: "Diakoniekrankenhaus",
            2: "Moosgrund",
        },
    )


def make_trip(trip_id="live-0", base=None):
    base = base or T0
    stops = [
        Stop(0, base, base + timedelta(seconds=60)),
        Stop(1, base + timedelta(seconds=120), base + timedelta(seconds=150)),
        Stop(2, base + timedelta(seconds=210), base + timedelta(seconds=210)),
    ]
    return Trip(trip_id, 0, stops, cyclic=False)


class TripLocateTests(unittest.TestCase):
    def setUp(self):
        self.trip = make_trip()

    def test_cycle_offset_is_zero_and_cycle_seconds_uses_last_departure(self):
        self.assertEqual(self.trip.cycle_offset(T0 + timedelta(hours=3)), timedelta(0))
        self.assertEqual(self.trip.cycle_seconds, 210.0)

    def test_locate_before_start_is_haltend_at_first_stop(self):
        index, state, begin, end = self.trip.locate(T0 - timedelta(seconds=30))
        self.assertEqual((index, state), (0, "haltend"))
        self.assertEqual(begin, T0 - timedelta(seconds=30))
        self.assertEqual(end, T0 + timedelta(seconds=60))
        self.assertFalse(self.trip.is_active(T0 - timedelta(seconds=30)))

    def test_locate_mid_leg_is_fahrend_index_0(self):
        index, state, begin, end = self.trip.locate(T0 + timedelta(seconds=90))
        self.assertEqual((index, state), (0, "fahrend"))
        self.assertEqual(begin, T0 + timedelta(seconds=60))
        self.assertEqual(end, T0 + timedelta(seconds=120))
        self.assertTrue(self.trip.is_active(T0 + timedelta(seconds=90)))

    def test_locate_dwell_is_haltend_index_1(self):
        index, state, begin, end = self.trip.locate(T0 + timedelta(seconds=130))
        self.assertEqual((index, state), (1, "haltend"))
        self.assertEqual(begin, T0 + timedelta(seconds=120))
        self.assertEqual(end, T0 + timedelta(seconds=150))

    def test_locate_after_end_is_haltend_at_last_stop(self):
        index, state, begin, end = self.trip.locate(T0 + timedelta(seconds=300))
        self.assertEqual((index, state), (2, "haltend"))
        self.assertEqual(begin, T0 + timedelta(seconds=210))
        self.assertEqual(end, T0 + timedelta(seconds=300))
        self.assertFalse(self.trip.is_active(T0 + timedelta(seconds=300)))
        self.assertFalse(self.trip.is_active(T0 + timedelta(seconds=211)))


class TrainLiveTests(unittest.TestCase):
    def setUp(self):
        self.trip = make_trip()
        self.route = make_route()
        self.train = Train(id=self.trip.id, trip=self.trip)
        self.train.minute_value = 600

    def test_sync_to_time_interpolates_between_stations(self):
        self.train.sync_to_time(self.route, T0 + timedelta(seconds=90))
        self.assertTrue(0 < self.train.position < 5, self.train.position)
        self.assertEqual(self.train.direction, 1)
        self.assertFalse(self.train.at_station)

    def test_move_never_leaves_last_station(self):
        self.train.sync_to_time(self.route, T0 + timedelta(seconds=90))
        for _ in range(5000):
            self.train.move(self.route)
            self.assertGreaterEqual(self.train.position, 0)
            self.assertLessEqual(self.train.position, 10)
        self.assertEqual(self.train.position, 10)
        self.assertEqual(self.train.stop_index, 2)
        self.assertEqual(self.train.target_position, 10)
        self.assertEqual(self.train.ticks_per_led, 1)

    def test_inactive_train_does_not_move(self):
        self.train.sync_to_time(self.route, T0 + timedelta(seconds=300))
        self.assertEqual(self.train.position, 10)
        for _ in range(100):
            self.train.move(self.route)
        self.assertEqual(self.train.position, 10)


class ArrivalLoggingTests(unittest.TestCase):
    def _train_approaching_station(self, trip, station_index):
        train = Train(id=trip.id, trip=trip)
        train.stop_index = station_index - 1
        train.next_index = station_index
        train.position = 4 if station_index == 1 else 9
        train.target_position = 5 if station_index == 1 else 10
        train.direction = 1
        train.at_station = False
        train.ticks_to_move = 1
        train.ticks_per_led = 1
        return train

    def test_arrival_logs_next_stop_and_eta_once(self):
        trip = make_trip()
        train = self._train_approaching_station(trip, 1)
        route = make_route([train])
        controller = Controller([route], FakeStrip(15))

        with self.assertLogs("classes", level="INFO") as captured:
            controller._move_trains(route)
            controller._move_trains(route)

        messages = "\n".join(captured.output)
        self.assertEqual(messages.count("angekommen"), 1)
        self.assertIn("Diakoniekrankenhaus", messages)
        self.assertIn("Moosgrund", messages)
        self.assertIn("2026-01-01T05:03:30Z", messages)

    def test_terminal_arrival_has_no_next_stop(self):
        trip = make_trip()
        train = self._train_approaching_station(trip, 2)
        route = make_route([train])
        controller = Controller([route], FakeStrip(15))

        with self.assertLogs("classes", level="INFO") as captured:
            controller._move_trains(route)

        self.assertIn("Moosgrund", captured.output[0])
        self.assertIn("keine weitere Haltestelle", captured.output[0])

    def test_time_sync_logs_arrival_transition_only_once(self):
        trip = make_trip()
        train = self._train_approaching_station(trip, 1)
        route = make_route([train])
        controller = Controller([route], FakeStrip(15))

        with self.assertLogs("classes", level="INFO") as captured:
            previous_states = controller._capture_arrival_states(route)
            train.sync_to_time(route, T0 + timedelta(seconds=130))
            controller._log_arrival_transitions(route, previous_states)

            previous_states = controller._capture_arrival_states(route)
            train.sync_to_time(route, T0 + timedelta(seconds=131))
            controller._log_arrival_transitions(route, previous_states)

        self.assertEqual(sum("angekommen" in line for line in captured.output), 1)

    def test_startup_synchronization_does_not_log_arrival(self):
        trip = make_trip()
        train = Train(id=trip.id, trip=trip)
        route = make_route([train])
        controller = Controller([route], FakeStrip(15))

        with patch("classes.logger.info") as log_info:
            controller.sync_trains()

        log_info.assert_not_called()


class SetTripsTests(unittest.TestCase):
    def test_keeps_train_object_for_same_trip_id(self):
        route = make_route()
        trip_a = make_trip("A")
        trip_b = make_trip("B")
        route.set_trips([trip_a, trip_b], T0 + timedelta(seconds=90), 600)
        self.assertEqual([train.id for train in route.trains], ["A", "B"])
        train_b = route.trains[1]

        trip_b2 = make_trip("B")
        trip_c = make_trip("C")
        route.set_trips([trip_b2, trip_c], T0 + timedelta(seconds=90), 600)

        self.assertEqual([train.id for train in route.trains], ["B", "C"])
        self.assertIs(route.trains[0], train_b)
        self.assertIs(route.trains[0].trip, trip_b2)
        self.assertIs(route.trains[1].trip, trip_c)
        self.assertEqual([trip.id for trip in route.trips], ["B", "C"])


def build_trips(module, fahrplan, route_id):
    """Kopie der kleinen build_trips-Logik aus main.py, aber fuer ein Modul."""
    for entry in fahrplan:
        if entry["route_id"] != route_id:
            continue
        trips = []
        for trip_config in entry["trips"]:
            trip = module.Trip(
                id=trip_config["id"],
                train_id=trip_config["train_id"],
                stops=[
                    module.Stop(
                        stop["station_id"],
                        stop["arrival"],
                        stop["departure"],
                        stop.get("delay_in_sec", 0),
                    )
                    for stop in trip_config["stops"]
                ],
                cycle_seconds=trip_config.get("cycle_seconds"),
            )
            trips.append(trip)
        return trips
    return []


def load_original_classes():
    """Laedt classes.py aus HEAD als eigenes Modul (mit rpi_ws281x-Stub)."""
    source = subprocess.run(
        ["git", "show", "HEAD:classes.py"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    stub = types.ModuleType("rpi_ws281x")
    stub.PixelStrip = object
    stub.Color = lambda r, g, b: (int(r) << 16) | (int(g) << 8) | int(b)
    had_stub = "rpi_ws281x" in sys.modules
    previous = sys.modules.get("rpi_ws281x")
    sys.modules["rpi_ws281x"] = stub

    handle = tempfile.NamedTemporaryFile(
        "w", suffix="_original_classes.py", delete=False, encoding="utf-8"
    )
    handle.write(source)
    handle.close()
    try:
        spec = importlib.util.spec_from_file_location("original_classes_head", handle.name)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        Path(handle.name).unlink(missing_ok=True)
        if had_stub:
            sys.modules["rpi_ws281x"] = previous
        else:
            sys.modules.pop("rpi_ws281x", None)
    return module


class CyclicRegressionTests(unittest.TestCase):
    def test_cyclic_locate_matches_original_classes(self):
        original = load_original_classes()
        fahrplan = json.loads((ROOT / "fahrplan.json").read_text(encoding="utf-8"))["fahrplan"]

        new_trips = build_trips(sys.modules["classes"], fahrplan, 0)
        old_trips = build_trips(original, fahrplan, 0)
        new_trip = next(trip for trip in new_trips if trip.train_id == 0)
        old_trip = next(trip for trip in old_trips if trip.train_id == 0)

        sample_times = [
            T0 + timedelta(seconds=30),     # mitten im ersten Halt
            T0 + timedelta(seconds=150),    # auf dem Weg zwischen zwei Halten
            T0 + timedelta(seconds=5000),   # mehrere Zyklen spaeter
        ]
        for moment in sample_times:
            with self.subTest(moment=moment):
                self.assertEqual(new_trip.locate(moment), old_trip.locate(moment))
                self.assertTrue(new_trip.is_active(moment))


class ControllerLiveTests(unittest.TestCase):
    def test_controller_fills_trains_from_trip_source(self):
        route = make_route()
        strip = FakeStrip(15)
        strip.begin()
        controller = Controller([route], strip)
        controller.tickinterval = 50
        controller.resync_interval_seconds = 60
        controller.live_refresh_seconds = 0.05

        now = datetime.now(timezone.utc)
        trips = [make_trip("live-0", base=now - timedelta(seconds=90))]
        controller.trip_source = lambda moment: {0: trips}

        errors = []

        def run():
            try:
                controller.start()
            except BaseException as exc:  # noqa: BLE001 - im Test weiterreichen
                errors.append(exc)

        thread = threading.Thread(target=run, daemon=True)
        thread.start()
        deadline = time.time() + 1.0
        while time.time() < deadline and not route.trains:
            time.sleep(0.01)
        controller.stop()
        thread.join(timeout=2.0)

        self.assertFalse(thread.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual([train.id for train in route.trains], ["live-0"])
        self.assertIs(route.trains[0].trip, trips[0])

    def test_controller_keeps_physical_trips_separate_from_connections(self):
        route = make_route()
        route.set_closed_section((1, 2))
        controller = Controller([route], FakeStrip(15))
        now = datetime.now(timezone.utc)
        trip = make_trip("left-half", base=now - timedelta(seconds=90))
        connection = RouteConnection(
            id="left-half|right-half",
            origin_station_id=0,
            destination_station_id=2,
            first_boundary_station_id=1,
            second_boundary_station_id=2,
            departure=now - timedelta(minutes=1),
            arrival=now + timedelta(minutes=10),
            transfer_arrival=now + timedelta(minutes=2),
            transfer_departure=now + timedelta(minutes=7),
            delay_seconds=0,
        )
        controller._live_queue.put(
            {0: RouteLiveData(trips=[trip], connections=[connection])}
        )

        controller._drain_live_queue(600)

        self.assertEqual([train.trip.id for train in route.trains], ["left-half"])
        self.assertEqual(route.connections, [connection])

    def test_controller_survives_raising_trip_source(self):
        route = make_route([Train(id=0, trip=make_trip("stable"))])
        strip = FakeStrip(15)
        controller = Controller([route], strip)
        controller.tickinterval = 20
        controller.live_refresh_seconds = 0.05

        def boom(moment):
            raise RuntimeError("kaputt")

        controller.trip_source = boom

        thread = threading.Thread(target=controller.start, daemon=True)
        with self.assertLogs("classes", level="ERROR"):
            thread.start()
            time.sleep(0.3)
            controller.stop()
            thread.join(timeout=2.0)

        self.assertFalse(thread.is_alive())
        self.assertEqual([train.id for train in route.trains], [0])


if __name__ == "__main__":
    unittest.main()
