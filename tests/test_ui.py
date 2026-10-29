"""Tests for route/train display helpers and LED selection."""

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from classes import Controller, Route, Train, Trip, Stop
from led_backend import FakeStrip
from live_feed import LiveCall, LiveJourney
from main import journeys_to_trips
from ui import TramUI, filter_trains, train_info


START = datetime(2026, 1, 1, 5, 0, tzinfo=timezone.utc)


def make_route(trains=None):
    return Route(
        7,
        [5, 5, 5],
        list(trains or []),
        (255, 0, 0),
        0,
        station_names={
            0: "Moosweiher",
            1: "Diakoniekrankenhaus",
            2: "Moosgrund",
        },
        name="Linie 7",
    )


def make_train(train_id, direction=1, cyclic=False):
    station_ids = (0, 1, 2) if direction > 0 else (2, 1, 0)
    trip = Trip(
        train_id,
        train_id,
        [
            Stop(
                station_id,
                START + timedelta(seconds=index * 70),
                START + timedelta(seconds=index * 70 + 10),
            )
            for index, station_id in enumerate(station_ids)
        ],
        cyclic=cyclic,
    )
    train = Train(train_id, trip)
    train.direction = direction
    train.stop_index = 0
    train.next_index = 1
    train.at_station = False
    return train


class TrainInfoTests(unittest.TestCase):
    def test_summary_includes_route_names_times_position_and_direction(self):
        train = make_train("journey-1")
        route = make_route([train])
        train.position = 2

        info = train_info(route, train)

        self.assertEqual(info.origin, "Moosweiher")
        self.assertEqual(info.destination, "Moosgrund")
        self.assertEqual(info.departure, START + timedelta(seconds=10))
        self.assertEqual(info.arrival, START + timedelta(seconds=140))
        self.assertEqual(info.position, "Zwischen Moosweiher und Diakoniekrankenhaus")
        self.assertEqual(info.direction_destination, "Moosgrund")

    def test_summary_uses_cumulative_schedule_delay_at_current_stop(self):
        train = make_train("journey-1")
        route = make_route([train])
        train.trip.stops[0].delay_seconds = 60
        train.trip.stops[1].delay_seconds = 90
        train.stop_index = 1

        self.assertEqual(
            train_info(route, train).current_delay,
            timedelta(seconds=150),
        )

    def test_summary_uses_reported_delay_at_current_live_stop(self):
        journey = LiveJourney(
            journey_ref="live-1",
            line_ref="line-7",
            line_name="Linie 7",
            destination="Moosgrund",
            calls=[
                LiveCall(
                    0,
                    START,
                    START + timedelta(seconds=5),
                    START,
                    START + timedelta(seconds=10),
                ),
                LiveCall(
                    1,
                    START + timedelta(minutes=10, seconds=180),
                    START + timedelta(minutes=10, seconds=190),
                    START + timedelta(minutes=10),
                    START + timedelta(minutes=10, seconds=10),
                ),
                LiveCall(
                    2,
                    START + timedelta(minutes=20, seconds=600),
                    START + timedelta(minutes=20, seconds=610),
                    START + timedelta(minutes=20),
                    START + timedelta(minutes=20, seconds=10),
                ),
            ],
        )
        trip = journeys_to_trips([journey])[0]
        train = Train("live-1", trip)
        train.stop_index = 1
        train.at_station = True
        route = make_route([train])

        info = train_info(route, train)

        self.assertEqual(info.current_delay, timedelta(seconds=180))
        self.assertEqual(trip.stops[1].delay_seconds, 0)
        self.assertEqual(trip.stops[1].reported_delay_seconds, 180)
        self.assertEqual(trip.stops[0].reported_delay_seconds, 0)

    def test_delay_format_uses_minutes_and_marks_punctual_trains(self):
        self.assertEqual(TramUI._format_delay(timedelta(0)), "Pünktlich")
        self.assertEqual(
            TramUI._format_delay(timedelta(seconds=61)),
            "+1 min",
        )
        self.assertEqual(
            TramUI._format_delay(timedelta(seconds=90)),
            "+2 min",
        )
        self.assertEqual(
            TramUI._format_delay(timedelta(seconds=-10)),
            "Pünktlich",
        )

    def test_direction_filter_uses_current_direction_and_keeps_all_option(self):
        outbound = make_train("outbound", direction=1)
        inbound = make_train("inbound", direction=-1)
        route = make_route([outbound, inbound])

        self.assertEqual(filter_trains(route, route.trains, None), route.trains)
        self.assertEqual(filter_trains(route, route.trains, 2), [outbound])
        self.assertEqual(filter_trains(route, route.trains, 0), [inbound])


class TrainTableLayoutTests(unittest.TestCase):
    def test_journey_column_is_narrower_and_other_columns_expand(self):
        app = TramUI.__new__(TramUI)
        ttk = MagicMock()

        app._build_train_table(MagicMock(), ttk)

        tree = ttk.Treeview.return_value
        tree.column.assert_any_call("journey", width=194, anchor="w", stretch=False)
        tree.column.assert_any_call("delay", width=120, anchor="center", stretch=True)
        tree.column.assert_any_call(
            "departure", width=120, anchor="center", stretch=True
        )
        tree.column.assert_any_call("arrival", width=120, anchor="center", stretch=True)
        tree.column.assert_any_call("action", width=200, anchor="center", stretch=True)


class ControllerTrainSelectionTests(unittest.TestCase):
    def test_selected_train_is_the_only_train_rendered(self):
        selected = make_train("selected", cyclic=True)
        other = make_train("other", cyclic=True)
        selected.position = 2
        other.position = 8
        route = make_route([selected, other])
        strip = FakeStrip(15)
        controller = Controller([route], strip)
        controller.select_train(route.id, selected.trip.id)

        controller.reset_strip()
        controller.draw(route)

        self.assertEqual(strip.getPixelColor(2), 0xFF0000)
        self.assertEqual(strip.getPixelColor(1), 0xFF0000)
        self.assertEqual(strip.getPixelColor(8), 0)
        self.assertEqual(strip.getPixelColor(7), 0)

    def test_clearing_selection_restores_all_trains(self):
        first = make_train("first", cyclic=True)
        second = make_train("second", cyclic=True)
        first.position = 2
        second.position = 8
        route = make_route([first, second])
        strip = FakeStrip(15)
        controller = Controller([route], strip)
        controller.select_train(route.id, first.trip.id)
        controller.select_train(None)

        controller.reset_strip()
        controller.draw(route)

        self.assertEqual(strip.getPixelColor(2), 0xFF0000)
        self.assertEqual(strip.getPixelColor(8), 0xFF0000)


if __name__ == "__main__":
    unittest.main()
