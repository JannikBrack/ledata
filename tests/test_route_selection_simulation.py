"""Tests for the isolated LED preview shown before a route is selected."""

import unittest
from datetime import datetime, timedelta, timezone

from classes import Route, Stop, Train, Trip
from led_backend import FakeStrip
from route_selection_simulation import RouteSelectionSimulation


START = datetime(2026, 1, 1, 5, 0, tzinfo=timezone.utc)


def make_route(route_id=0, color=(255, 0, 0), start=0):
    stops = [
        Stop(0, START, START + timedelta(seconds=60)),
        Stop(1, START + timedelta(seconds=120), START + timedelta(seconds=150)),
        Stop(2, START + timedelta(seconds=210), START + timedelta(seconds=210)),
    ]
    trip = Trip(f"trip-{route_id}", route_id, stops, cyclic=False)
    train = Train(f"train-{route_id}", trip)
    return Route(route_id, [5, 5, 5], [train], color, start)


class RouteSelectionSimulationTests(unittest.TestCase):
    def test_preview_uses_line_colors_and_white_for_cross_route_overlap(self):
        first = make_route()
        second = make_route(1, (0, 255, 0), start=1)
        strip = FakeStrip(15)
        simulation = RouteSelectionSimulation([first, second], strip)

        simulation.start()
        simulation.render(START + timedelta(seconds=90))

        self.assertEqual(strip.getPixelColor(1), 0xFF0000)
        self.assertEqual(strip.getPixelColor(2), 0xFFFFFF)
        self.assertEqual(strip.getPixelColor(3), 0x00FF00)
        self.assertEqual(strip.getPixelColor(5), 0)

    def test_preview_draws_a_train_at_a_station_but_no_station_markers(self):
        route = make_route()
        strip = FakeStrip(15)
        simulation = RouteSelectionSimulation([route], strip)

        simulation.start()
        simulation.render(START + timedelta(seconds=5))

        self.assertEqual(strip.getPixelColor(0), 0xFF0000)
        self.assertEqual(strip.getPixelColor(5), 0)
        self.assertEqual(strip.getPixelColor(10), 0)

    def test_preview_tracks_train_positions_over_time(self):
        route = make_route()
        strip = FakeStrip(15)
        simulation = RouteSelectionSimulation([route], strip)
        simulation.start()

        simulation.render(START + timedelta(seconds=90))
        first_position = route.trains[0].position
        simulation.render(START + timedelta(seconds=180))

        self.assertNotEqual(route.trains[0].position, first_position)
        self.assertEqual(strip.getPixelColor(route.trains[0].position), 0xFF0000)

    def test_preview_stops_and_clears_the_strip(self):
        route = make_route()
        strip = FakeStrip(15)
        simulation = RouteSelectionSimulation([route], strip)
        simulation.start()
        simulation.render(START + timedelta(seconds=90))

        simulation.stop()

        self.assertFalse(simulation.active)
        self.assertEqual([strip.getPixelColor(i) for i in range(15)], [0] * 15)


if __name__ == "__main__":
    unittest.main()
