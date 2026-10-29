"""Tests for route/train display helpers and LED selection."""

import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from classes import Controller, Route, RouteConnection, Train, Trip, Stop
from led_backend import FakeStrip
from live_feed import LiveCall, LiveConnection, LiveJourney
from main import journeys_to_connections, journeys_to_trips
from ui import (
    StopTimeline,
    StopTimelineEntry,
    TramUI,
    connection_stop_timeline,
    filter_connections,
    filter_trains,
    route_direction_destination_ids,
    train_stop_timeline,
    train_info,
    walking_connection_instruction,
)


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


class RouteSelectionUITests(unittest.TestCase):
    def test_route_button_labels_closure_and_regular_routes(self):
        closed_route = make_route()
        closed_route.closed_section = (1, 2)
        regular_route = make_route()
        regular_route.id = 8
        regular_route.name = "Linie 8"
        app = TramUI.__new__(TramUI)
        app.controller = MagicMock()
        app.routes = [closed_route, regular_route]
        app.root = MagicMock()
        app.root.winfo_children.return_value = []
        app.tk = MagicMock()
        app.closure_store = None
        app._header = MagicMock()

        app.show_routes()

        button_labels = [
            call.kwargs["text"] for call in app.tk.Button.call_args_list
        ]
        self.assertEqual(button_labels, ["Linie 7 · ⚠ Baustelle", "Linie 8"])
        app.controller.select_route.assert_called_once_with(None)

    def test_train_plan_header_shows_closure_next_to_route_name(self):
        route = make_route()
        route.closed_section = (1, 2)
        app = TramUI.__new__(TramUI)
        app.controller = MagicMock()
        app.routes = [route]
        app.root = MagicMock()
        app.tk = MagicMock()
        app.ttk = MagicMock()
        app._clear = MagicMock()
        app._header = MagicMock()
        app._update_filter_buttons = MagicMock()
        app._build_train_table = MagicMock()
        app._refresh_train_rows = MagicMock()

        app.show_trains(route.id)

        app._header.assert_called_once_with("Linie 7 · ⚠ Baustelle", "Linien")
        app.controller.select_route.assert_called_once_with(route.id)


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

    def test_stop_timeline_shows_all_stops_in_trip_direction_with_arrival_times(self):
        train = make_train("journey-1", direction=-1)
        route = make_route([train])

        timeline = train_stop_timeline(route, train)

        self.assertEqual(
            timeline.current,
            StopTimelineEntry(
                "Moosgrund",
                START,
                START + timedelta(seconds=10),
            ),
        )
        self.assertEqual(
            timeline.upcoming,
            (
                StopTimelineEntry(
                    "Diakoniekrankenhaus",
                    START + timedelta(seconds=70),
                    START + timedelta(seconds=80),
                ),
                StopTimelineEntry(
                    "Moosweiher",
                    START + timedelta(seconds=140),
                    START + timedelta(seconds=150),
                ),
            ),
        )
        self.assertEqual(timeline.past, ())
        self.assertEqual(timeline.next_destination, "Diakoniekrankenhaus")

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

    def test_detail_summary_shows_direction_times_delay_current_and_next_stop(self):
        train = make_train("journey-1")
        train.at_station = False
        route = make_route([train])
        app = TramUI.__new__(TramUI)
        app.screen = "detail"
        app.route = route
        app._detail_connection_id = None
        app._detail_train_id = train.trip.id
        app._detail_labels = {
            key: MagicMock()
            for key in ("direction", "times", "delay", "current", "next")
        }
        app._refresh_detail_stop_table = MagicMock()
        app._refresh_detail_closure_banner = MagicMock()

        app._refresh_detail()

        app._detail_labels["direction"].configure.assert_called_once_with(
            text="Fahrtrichtung: Moosgrund"
        )
        app._detail_labels["times"].configure.assert_called_once_with(
            text=(
                f"Abfahrt {TramUI._format_time(START + timedelta(seconds=10))}"
                f" · Ankunft {TramUI._format_time(START + timedelta(seconds=140))}"
            )
        )
        app._detail_labels["current"].configure.assert_called_once_with(
            text="Zuletzt erreichter Halt: Moosweiher"
        )
        app._detail_labels["next"].configure.assert_called_once_with(
            text="Nächstes Ziel: Diakoniekrankenhaus"
        )
        app._refresh_detail_closure_banner.assert_called_once_with(None)

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

    def test_closed_route_keeps_outer_direction_destinations(self):
        route = make_route()
        route.closed_section = (1, 2)
        toward_moosgrund = RouteConnection(
            id="outbound",
            origin_station_id=0,
            destination_station_id=2,
            first_boundary_station_id=1,
            second_boundary_station_id=2,
            departure=START,
            arrival=START + timedelta(minutes=20),
            transfer_arrival=START + timedelta(minutes=10),
            transfer_departure=START + timedelta(minutes=15),
            delay_seconds=0,
        )
        toward_moosweiher = RouteConnection(
            id="inbound",
            origin_station_id=2,
            destination_station_id=0,
            first_boundary_station_id=2,
            second_boundary_station_id=1,
            departure=START,
            arrival=START + timedelta(minutes=20),
            transfer_arrival=START + timedelta(minutes=10),
            transfer_departure=START + timedelta(minutes=15),
            delay_seconds=0,
        )

        self.assertEqual(route_direction_destination_ids(route), (0, 2))
        self.assertEqual(
            filter_connections(
                [toward_moosgrund, toward_moosweiher],
                2,
            ),
            [toward_moosgrund],
        )
        self.assertEqual(
            walking_connection_instruction(route, toward_moosgrund),
            "Zu Fuß: Diakoniekrankenhaus → Moosgrund",
        )


class TrainTableLayoutTests(unittest.TestCase):
    def test_columns_have_no_closure_warning_and_fill_table_width(self):
        app = TramUI.__new__(TramUI)
        app.route = make_route()
        app.route.closed_section = (1, 2)
        ttk = MagicMock()

        app._build_train_table(MagicMock(), ttk)
        tree = ttk.Treeview.return_value
        self.assertNotIn("closure", ttk.Treeview.call_args.kwargs["columns"])
        for table_width, expected_other_widths in (
            (800, [111, 111, 111, 187]),
            (1200, [167, 167, 167, 279]),
        ):
            with self.subTest(table_width=table_width):
                app._resize_train_columns(SimpleNamespace(width=table_width))
                resized_columns = {
                    call.args[0]: call.kwargs["width"]
                    for call in tree.column.call_args_list[-5:]
                }

                self.assertEqual(resized_columns["journey"], round(table_width * 0.35))
                self.assertNotIn("closure", resized_columns)
                self.assertEqual(
                    [
                        resized_columns[column]
                        for column in ("delay", "departure", "arrival", "action")
                    ],
                    expected_other_widths,
                )
                self.assertEqual(sum(resized_columns.values()), table_width)

    def test_train_table_has_no_closure_column(self):
        app = TramUI.__new__(TramUI)
        app.route = make_route()
        ttk = MagicMock()

        app._build_train_table(MagicMock(), ttk)

        self.assertNotIn("closure", ttk.Treeview.call_args.kwargs["columns"])

    def test_detail_stop_columns_fit_narrow_and_wide_touchscreens(self):
        app = TramUI.__new__(TramUI)
        app._detail_stop_tree = MagicMock()

        app._resize_detail_columns(SimpleNamespace(width=440))
        narrow = {
            call.args[0]: call.kwargs["width"]
            for call in app._detail_stop_tree.column.call_args_list[-3:]
        }
        self.assertEqual(narrow["#0"], 276)
        self.assertEqual(narrow["arrival"], 80)
        self.assertEqual(narrow["departure"], 80)
        self.assertEqual(sum(narrow.values()), 436)

        app._resize_detail_columns(SimpleNamespace(width=760))
        wide = {
            call.args[0]: call.kwargs["width"]
            for call in app._detail_stop_tree.column.call_args_list[-3:]
        }
        self.assertEqual(wide["#0"], 516)
        self.assertEqual(wide["arrival"], 120)
        self.assertEqual(wide["departure"], 120)
        self.assertEqual(sum(wide.values()), 756)

    def test_detail_stop_table_groups_stops_and_keeps_expansion_state_on_refresh(self):
        class Tree:
            def __init__(self):
                self.items = {}
                self.children = {"": []}

            def exists(self, item_id):
                return item_id in self.items

            def item(self, item_id, option=None, **values):
                if values:
                    self.items[item_id].update(values)
                return self.items[item_id].get(option) if option else self.items[item_id]

            def insert(self, parent, index, iid, **values):
                siblings = self.children.setdefault(parent, [])
                if index == "end":
                    siblings.append(iid)
                else:
                    siblings.insert(index, iid)
                self.items[iid] = {"parent": parent, **values}
                self.children.setdefault(iid, [])

            def move(self, item_id, parent, index):
                old_parent = self.items[item_id]["parent"]
                self.children[old_parent].remove(item_id)
                siblings = self.children.setdefault(parent, [])
                siblings.insert(index, item_id)
                self.items[item_id]["parent"] = parent

            def get_children(self, parent=""):
                return tuple(self.children.get(parent, []))

            def delete(self, item_id):
                for child in list(self.children.get(item_id, [])):
                    self.delete(child)
                parent = self.items[item_id]["parent"]
                self.children[parent].remove(item_id)
                self.children.pop(item_id, None)
                del self.items[item_id]

        app = TramUI.__new__(TramUI)
        app._detail_stop_tree = Tree()
        timeline = StopTimeline(
            upcoming=(
                StopTimelineEntry(
                    "Moosgrund",
                    START + timedelta(minutes=10),
                    START + timedelta(minutes=11),
                ),
                StopTimelineEntry(
                    "Baustelle / Fußweg: Diakoniekrankenhaus → Moosgrund",
                    None,
                    is_closure=True,
                ),
            ),
            current=StopTimelineEntry(
                "Diakoniekrankenhaus",
                START,
                START + timedelta(minutes=1),
            ),
            past=(StopTimelineEntry("Moosweiher", START - timedelta(minutes=10)),),
            current_position="An Haltestelle Diakoniekrankenhaus",
            next_destination="Moosgrund",
        )

        app._refresh_detail_stop_table(timeline)
        tree = app._detail_stop_tree

        self.assertEqual(
            tree.get_children(),
            ("upcoming", "current", "past"),
        )
        self.assertFalse(tree.item("upcoming")["open"])
        self.assertFalse(tree.item("past")["open"])
        self.assertEqual(tree.item("current")["tags"], ("current",))
        self.assertEqual(
            tree.item("current")["values"],
            (TramUI._format_time(START), TramUI._format_time(START + timedelta(minutes=1))),
        )
        self.assertEqual(
            tree.item("upcoming-entry-1")["tags"],
            ("closure",),
        )

        tree.item("upcoming", open=True)
        updated = StopTimeline(
            upcoming=(StopTimelineEntry("Moosgrund", START + timedelta(minutes=10)),),
            current=StopTimelineEntry("Moosgrund", START + timedelta(minutes=10)),
            past=timeline.past + (timeline.current,),
            current_position="An Haltestelle Moosgrund",
            next_destination="Ziel erreicht",
        )
        app._refresh_detail_stop_table(updated)

        self.assertTrue(tree.item("upcoming")["open"])
        self.assertEqual(tree.item("current")["text"], "Moosgrund")
        self.assertEqual(tree.item("past")["text"], "Bereits angefahren (2)")

    def test_journeys_to_connections_keeps_component_trip_ids(self):
        source = LiveConnection(
            id="first|second",
            origin_station_id=0,
            destination_station_id=3,
            first_boundary_station_id=1,
            second_boundary_station_id=2,
            departure=START,
            arrival=START + timedelta(minutes=15),
            transfer_arrival=START + timedelta(minutes=5),
            transfer_departure=START + timedelta(minutes=10),
            delay_seconds=0,
            first_journey_ref="first",
            second_journey_ref="second",
            first_calls=(
                LiveCall(0, START, START, START, START),
                LiveCall(
                    1,
                    START + timedelta(minutes=5),
                    START + timedelta(minutes=5),
                    START + timedelta(minutes=5),
                    START + timedelta(minutes=5),
                ),
            ),
            second_calls=(
                LiveCall(
                    2,
                    START + timedelta(minutes=10),
                    START + timedelta(minutes=10),
                    START + timedelta(minutes=10),
                    START + timedelta(minutes=10),
                ),
                LiveCall(
                    3,
                    START + timedelta(minutes=15),
                    START + timedelta(minutes=15),
                    START + timedelta(minutes=15),
                    START + timedelta(minutes=15),
                ),
            ),
        )

        connection = journeys_to_connections([source])[0]

        self.assertEqual(connection.first_trip_id, "first")
        self.assertEqual(connection.second_trip_id, "second")
        self.assertEqual(
            [stop.station_id for stop in connection.first_stops],
            [0, 1],
        )
        self.assertEqual(
            [stop.station_id for stop in connection.second_stops],
            [2, 3],
        )

    def test_connection_detail_summary_omits_transfer_departure(self):
        route = make_route()
        connection = RouteConnection(
            id="outbound",
            origin_station_id=0,
            destination_station_id=2,
            first_boundary_station_id=1,
            second_boundary_station_id=2,
            departure=START,
            arrival=START + timedelta(minutes=20),
            transfer_arrival=START + timedelta(minutes=10),
            transfer_departure=START + timedelta(minutes=15),
            delay_seconds=60,
        )
        route.connections = [connection]
        app = TramUI.__new__(TramUI)
        app.screen = "detail"
        app.route = route
        app._detail_connection_id = connection.id
        app._detail_labels = {
            key: MagicMock()
            for key in ("direction", "times", "delay", "current", "next")
        }
        app._refresh_detail_stop_table = MagicMock()
        app._refresh_detail_closure_banner = MagicMock()
        timeline = StopTimeline(
            upcoming=(),
            current=StopTimelineEntry("Moosgrund", START),
            past=(),
            current_position="An Haltestelle Moosgrund",
            next_destination="Ziel erreicht",
            closure_info="Baustelle",
        )

        with patch("ui.connection_stop_timeline", return_value=timeline):
            app._refresh_detail()

        times_text = app._detail_labels["times"].configure.call_args.kwargs["text"]
        self.assertIn("Abfahrt", times_text)
        self.assertIn("Ankunft", times_text)
        self.assertNotIn("Weiterfahrt", times_text)
        app._detail_labels["current"].configure.assert_called_once_with(
            text="Aktueller Halt: Moosgrund"
        )
        app._detail_labels["next"].configure.assert_called_once_with(
            text="Nächstes Ziel: Ziel erreicht"
        )
        app._refresh_detail_closure_banner.assert_called_once_with(
            "Baustelle: Diakoniekrankenhaus → Moosgrund · Fußweg/Umstieg 5 min"
        )

    def test_connection_stop_timeline_inserts_closure_between_actual_legs(self):
        route = Route(
            7,
            [5, 5, 5, 5],
            [],
            (255, 0, 0),
            0,
            station_names={
                0: "Moosweiher",
                1: "Diakoniekrankenhaus",
                2: "Moosgrund",
                3: "Paduaallee",
            },
        )
        first_trip = Trip(
            "first-leg",
            "first-leg",
            [
                Stop(0, START, START),
                Stop(1, START + timedelta(minutes=5), START + timedelta(minutes=5)),
            ],
            cyclic=False,
        )
        second_trip = Trip(
            "second-leg",
            "second-leg",
            [
                Stop(2, START + timedelta(minutes=10), START + timedelta(minutes=10)),
                Stop(3, START + timedelta(minutes=15), START + timedelta(minutes=15)),
            ],
            cyclic=False,
        )
        # A connection can outlive the active-trips snapshot used by the route.
        route.trips = []
        connection = RouteConnection(
            id="connection",
            origin_station_id=0,
            destination_station_id=3,
            first_boundary_station_id=1,
            second_boundary_station_id=2,
            departure=START,
            arrival=START + timedelta(minutes=15),
            transfer_arrival=START + timedelta(minutes=5),
            transfer_departure=START + timedelta(minutes=10),
            delay_seconds=0,
            first_trip_id="first-leg",
            second_trip_id="second-leg",
            first_stops=tuple(first_trip.stops),
            second_stops=tuple(second_trip.stops),
        )

        timeline = connection_stop_timeline(
            route,
            connection,
            START + timedelta(minutes=7),
        )

        self.assertEqual(
            timeline,
            StopTimeline(
                upcoming=(
                    StopTimelineEntry(
                        "Moosgrund",
                        START + timedelta(minutes=10),
                        START + timedelta(minutes=10),
                    ),
                    StopTimelineEntry(
                        "Paduaallee",
                        START + timedelta(minutes=15),
                        START + timedelta(minutes=15),
                    ),
                ),
                current=StopTimelineEntry(
                    "Baustelle / Fußweg: Diakoniekrankenhaus → Moosgrund",
                    None,
                    is_closure=True,
                ),
                past=(
                    StopTimelineEntry("Moosweiher", START, START),
                    StopTimelineEntry(
                        "Diakoniekrankenhaus",
                        START + timedelta(minutes=5),
                        START + timedelta(minutes=5),
                    ),
                ),
                current_position="Zu Fuß zwischen Diakoniekrankenhaus und Moosgrund",
                next_destination="Moosgrund",
                closure_info="Baustelle: Diakoniekrankenhaus → Moosgrund · Fußweg/Umstieg 5 min",
            ),
        )

    def test_connection_stop_timeline_reverses_closure_boundaries_with_direction(self):
        route = Route(
            7,
            [5, 5, 5, 5],
            [],
            (255, 0, 0),
            0,
            station_names={
                0: "Moosweiher",
                1: "Diakoniekrankenhaus",
                2: "Moosgrund",
                3: "Paduaallee",
            },
        )
        first_trip = Trip(
            "first-leg",
            "first-leg",
            [
                Stop(3, START, START),
                Stop(2, START + timedelta(minutes=5), START + timedelta(minutes=5)),
            ],
            cyclic=False,
        )
        second_trip = Trip(
            "second-leg",
            "second-leg",
            [
                Stop(1, START + timedelta(minutes=10), START + timedelta(minutes=10)),
                Stop(0, START + timedelta(minutes=15), START + timedelta(minutes=15)),
            ],
            cyclic=False,
        )
        route.trips = []
        connection = RouteConnection(
            id="connection-reverse",
            origin_station_id=3,
            destination_station_id=0,
            first_boundary_station_id=2,
            second_boundary_station_id=1,
            departure=START,
            arrival=START + timedelta(minutes=15),
            transfer_arrival=START + timedelta(minutes=5),
            transfer_departure=START + timedelta(minutes=10),
            delay_seconds=0,
            first_trip_id="first-leg",
            second_trip_id="second-leg",
            first_stops=tuple(first_trip.stops),
            second_stops=tuple(second_trip.stops),
        )

        timeline = connection_stop_timeline(
            route,
            connection,
            START + timedelta(minutes=7),
        )
        self.assertEqual(
            timeline.current.name,
            "Baustelle / Fußweg: Moosgrund → Diakoniekrankenhaus",
        )
        self.assertEqual(
            [entry.name for entry in timeline.past],
            ["Paduaallee", "Moosgrund"],
        )
        self.assertEqual(
            [entry.name for entry in timeline.upcoming],
            ["Diakoniekrankenhaus", "Moosweiher"],
        )
        self.assertEqual(
            timeline.closure_info,
            "Baustelle: Moosgrund → Diakoniekrankenhaus · Fußweg/Umstieg 5 min",
        )

    def test_connection_rows_do_not_include_empty_closure_value(self):
        app = TramUI.__new__(TramUI)
        app.route = make_route()
        app.route.closed_section = (1, 2)
        app._tree = MagicMock()
        app._tree.exists.return_value = False
        connection = RouteConnection(
            id="outbound",
            origin_station_id=0,
            destination_station_id=2,
            first_boundary_station_id=1,
            second_boundary_station_id=2,
            departure=START,
            arrival=START + timedelta(minutes=20),
            transfer_arrival=START + timedelta(minutes=10),
            transfer_departure=START + timedelta(minutes=15),
            delay_seconds=0,
        )

        app._refresh_connection_table([connection])

        row_values = app._tree.insert.call_args.kwargs["values"]
        self.assertEqual(len(row_values), 5)
        self.assertEqual(row_values[1], "Pünktlich")


class DirectionFilterUITests(unittest.TestCase):
    def test_direction_button_updates_controller_selection(self):
        app = TramUI.__new__(TramUI)
        app.route = make_route()
        app.controller = MagicMock()
        app._update_filter_buttons = MagicMock()
        app._refresh_train_rows = MagicMock()

        app._select_direction(2)
        app._select_direction(None)

        self.assertIsNone(app.direction_id)
        self.assertEqual(
            [
                call.args
                for call in app.controller.select_direction.call_args_list
            ],
            [(app.route.id, 2), (app.route.id, None)],
        )

    def test_tapping_timeline_group_toggles_expansion(self):
        app = TramUI.__new__(TramUI)
        app._detail_stop_tree = MagicMock()
        app._detail_stop_tree.identify_row.return_value = "upcoming"
        app._detail_stop_tree.item.return_value = False

        result = app._toggle_detail_group(SimpleNamespace(y=12))

        self.assertEqual(result, "break")
        app._detail_stop_tree.item.assert_any_call("upcoming", open=True)


class ControllerTrainSelectionTests(unittest.TestCase):
    def test_stopped_station_blinks_in_route_color(self):
        train = make_train("stopped", cyclic=True)
        train.position = 5
        train.at_station = True
        route = make_route([train])
        route.color = (19, 165, 56)
        strip = FakeStrip(15)
        controller = Controller([route], strip)

        controller.ticks = 0
        controller.draw(route)
        self.assertEqual(strip.getPixelColor(5), 0x13A538)
        self.assertEqual(strip.getPixelColor(0), 0xFFFFFF)
        self.assertEqual(strip.getPixelColor(10), 0xFFFFFF)

        controller.reset_strip()
        controller.ticks = 8
        controller.draw(route)
        self.assertEqual(strip.getPixelColor(5), 0)

    def test_direction_selection_only_renders_trains_heading_to_selected_endpoint(self):
        outbound = make_train("outbound", direction=1, cyclic=True)
        inbound = make_train("inbound", direction=-1, cyclic=True)
        outbound.position = 2
        inbound.position = 8
        route = make_route([outbound, inbound])
        strip = FakeStrip(15)
        controller = Controller([route], strip)
        controller.select_direction(route.id, 2)

        controller.reset_strip()
        controller.draw(route)

        self.assertEqual(strip.getPixelColor(2), 0xFF0000)
        self.assertEqual(strip.getPixelColor(8), 0)

    def test_clearing_direction_selection_restores_all_trains(self):
        outbound = make_train("outbound", direction=1, cyclic=True)
        inbound = make_train("inbound", direction=-1, cyclic=True)
        outbound.position = 2
        inbound.position = 8
        route = make_route([outbound, inbound])
        strip = FakeStrip(15)
        controller = Controller([route], strip)
        controller.select_direction(route.id, 2)
        controller.select_direction(None, None)

        controller.reset_strip()
        controller.draw(route)

        self.assertEqual(strip.getPixelColor(2), 0xFF0000)
        self.assertEqual(strip.getPixelColor(8), 0xFF0000)

    def test_closed_route_direction_includes_partial_trips_to_the_same_endpoint(self):
        outbound = make_train("outbound", direction=1, cyclic=True)
        inbound = make_train("inbound", direction=-1, cyclic=True)
        outbound.trip.stops = outbound.trip.stops[:2]
        inbound.trip.stops = inbound.trip.stops[1:]
        outbound.position = 2
        inbound.position = 3
        route = make_route([outbound, inbound])
        route.set_closed_section((1, 2))
        strip = FakeStrip(15)
        controller = Controller([route], strip)
        controller.select_direction(route.id, 2)

        controller.reset_strip()
        controller.draw(route)

        self.assertEqual(strip.getPixelColor(2), 0xFF0000)
        self.assertEqual(strip.getPixelColor(3), 0)
        for position in (0, 5, 10):
            self.assertEqual(strip.getPixelColor(position), 0xFFFFFF)
        for position in range(6, 10):
            self.assertEqual(strip.getPixelColor(position), 0xFF8000)

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

    def test_closed_section_is_orange_between_station_pixels(self):
        route = make_route()
        route.set_closed_section((0, 2))
        strip = FakeStrip(15)
        controller = Controller([route], strip)

        controller.draw(route)

        self.assertEqual(strip.getPixelColor(0), 0xFFFFFF)
        self.assertEqual(strip.getPixelColor(10), 0xFFFFFF)
        for position in range(1, 10):
            self.assertEqual(strip.getPixelColor(position), 0xFF8000)


if __name__ == "__main__":
    unittest.main()
