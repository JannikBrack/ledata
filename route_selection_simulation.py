"""Isolated LED preview for the UI's unselected-route screen."""

from datetime import datetime, timezone

from led_backend import Color


class RouteSelectionSimulation:
    def __init__(self, routes, strip) -> None:
        self.routes = routes
        self.strip = strip
        self.active = False

    def start(self):
        self.active = True

    def render(self, now: datetime | None = None):
        if not self.active:
            return

        now = now or datetime.now(timezone.utc)
        self._reset_strip()
        occupied_by_route = {}
        for route in self.routes:
            for train in route.trains:
                if not train.trip.is_active(now):
                    continue
                train.sync_to_time(route, now)
                for position in train.occupied_positions():
                    if 0 <= position < self.strip.numPixels():
                        occupied_by_route.setdefault(position, {})[route.id] = (
                            route.color
                        )

        for position, route_colors in occupied_by_route.items():
            color = (
                Color(255, 255, 255)
                if len(route_colors) > 1
                else Color(*next(iter(route_colors.values())))
            )
            self.strip.setPixelColor(position, color)
        self.strip.show()

    def stop(self):
        if not self.active:
            return
        self.active = False
        self._reset_strip()
        self.strip.show()

    def _reset_strip(self):
        for position in range(self.strip.numPixels()):
            self.strip.setPixelColor(position, Color(0, 0, 0))
