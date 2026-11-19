"""Tests fuer die lokale Fahrplan-Simulation."""

import unittest
from datetime import datetime, timedelta, timezone

from classes import Route, Train
from simulation_feed import SimulationFeed

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)


def make_route(route_id=0, layout=(10, 10, 10), names=None):
    station_names = names or {
        index: f"Halt {index}" for index in range(len(layout))
    }
    return Route(
        route_id,
        list(layout),
        [],
        (255, 0, 0),
        0,
        station_names=station_names,
        name=f"Linie {route_id}",
    )


def make_fahrplan(cycle_seconds=300):
    return [
        {
            "route_id": 0,
            "trips": [
                {
                    "id": "L0-Umlauf-0",
                    "train_id": 0,
                    "cycle_seconds": cycle_seconds,
                    "stops": [
                        {
                            "station_id": 0,
                            "arrival": "2026-01-01T05:00:00Z",
                            "departure": "2026-01-01T05:00:40Z",
                        },
                        {
                            "station_id": 1,
                            "arrival": "2026-01-01T05:00:50Z",
                            "departure": "2026-01-01T05:01:00Z",
                        },
                        {
                            "station_id": 2,
                            "arrival": "2026-01-01T05:01:15Z",
                            "departure": "2026-01-01T05:01:25Z",
                        },
                    ],
                }
            ],
        }
    ]


class SimulationFeedTests(unittest.TestCase):
    def test_builds_four_cyclic_round_trips_per_route(self):
        route = make_route()
        feed = SimulationFeed(
            [route],
            seconds_per_led=10,
            dwell_seconds=10,
            terminus_dwell_seconds=45,
        )

        snapshot = feed.snapshot(NOW)

        trips = snapshot[route.id].trips
        self.assertEqual(len(trips), 4)
        self.assertEqual(
            [trip.id for trip in trips],
            [f"sim-{route.id}-{index}" for index in range(4)],
        )
        for trip in trips:
            self.assertTrue(trip.cyclic)
            self.assertEqual(
                [stop.station_id for stop in trip.stops],
                [0, 1, 2, 1, 0],
            )
            self.assertEqual(trip.stops[0].station_id, trip.stops[-1].station_id)
            self.assertEqual(trip.stops[-1].dwell_seconds, 0)

    def test_travel_times_scale_with_led_distance_and_dwells(self):
        route = make_route(layout=(20, 10, 5))
        feed = SimulationFeed(
            [route],
            seconds_per_led=1.0,
            dwell_seconds=10,
            terminus_dwell_seconds=45,
        )

        trip = feed.snapshot(NOW)[route.id].trips[0]

        # 0 -> 1: 20 LEDs, 1 -> 2: 10 LEDs, zurueck 10 + 20
        self.assertEqual(trip.stops[0].dwell_seconds, 45)
        self.assertEqual(trip.stops[1].dwell_seconds, 10)
        self.assertEqual(trip.stops[2].dwell_seconds, 45)
        self.assertEqual(trip.stops[3].dwell_seconds, 10)
        self.assertEqual(trip.stops[4].dwell_seconds, 0)

        travel = [
            (
                trip.stops[index + 1].arrival
                - trip.stops[index].departure
            ).total_seconds()
            for index in range(len(trip.stops) - 1)
        ]
        self.assertEqual(travel, [20.0, 10.0, 10.0, 20.0])
        self.assertEqual(trip.cycle_seconds, 45 + 20 + 10 + 10 + 45 + 10 + 10 + 20)

    def test_trams_are_evenly_staggered(self):
        route = make_route()
        feed = SimulationFeed([route], seconds_per_led=10)
        trips = feed.snapshot(NOW)[route.id].trips

        starts = [trip.stops[0].arrival for trip in trips]
        headway = trips[0].cycle_seconds / 4
        for earlier, later in zip(starts, starts[1:]):
            self.assertAlmostEqual(
                (later - earlier).total_seconds(),
                headway,
                places=6,
            )

    def test_route_uses_fahrplan_pattern_and_ends_at_start_terminus(self):
        route = make_route()
        feed = SimulationFeed([route], make_fahrplan(cycle_seconds=300))

        trip = feed.snapshot(NOW)[route.id].trips[0]

        self.assertEqual(
            [stop.station_id for stop in trip.stops],
            [0, 1, 2, 0],
        )
        self.assertEqual(trip.stops[0].dwell_seconds, 40)
        self.assertEqual(trip.stops[1].dwell_seconds, 10)
        self.assertEqual(trip.stops[2].dwell_seconds, 10)
        self.assertEqual(trip.stops[3].dwell_seconds, 0)
        self.assertEqual(trip.cycle_seconds, 300)
        self.assertEqual(
            (trip.stops[-1].arrival - trip.stops[0].arrival).total_seconds(),
            300,
        )

    def test_route_filter_returns_only_requested_route(self):
        first = make_route(0)
        second = make_route(1, layout=(5, 5))
        feed = SimulationFeed([first, second], seconds_per_led=1)

        snapshot = feed.snapshot(NOW, route_id=second.id)

        self.assertEqual(list(snapshot), [second.id])

    def test_cyclic_trips_locate_valid_state_over_full_cycle(self):
        route = make_route()
        feed = SimulationFeed(
            [route],
            seconds_per_led=10,
            dwell_seconds=10,
            terminus_dwell_seconds=45,
        )
        trip = feed.snapshot(NOW)[route.id].trips[0]
        start = trip.start_time

        for second in (0, 20, 100, 200, 300, 400, 500, 510, 511, 600):
            index, state, begin, end = trip.locate(
                start + timedelta(seconds=second)
            )
            self.assertIn(state, {"haltend", "fahrend"})
            self.assertGreaterEqual(index, 0)
            self.assertLess(index, len(trip.stops))
            self.assertLessEqual(begin, end)

    def test_route_set_trips_creates_four_filterable_trains(self):
        route = make_route()
        feed = SimulationFeed([route], seconds_per_led=10)
        trips = feed.snapshot(NOW)[route.id].trips

        route.set_trips(trips, NOW, 600)

        self.assertEqual(len(route.trains), 4)
        self.assertTrue(all(isinstance(train, Train) for train in route.trains))
        self.assertTrue(all(train.is_visible(NOW) for train in route.trains))


if __name__ == "__main__":
    unittest.main()
