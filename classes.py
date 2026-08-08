import time

from rpi_ws281x import PixelStrip, Color

class Train():
    id: int
    length: int = 2
    direction: int
    position: int

    def __init__(self, id, direction, position) -> None:
        self.id = id
        self.direction = direction
        self.position = position

    def __str__(self) -> str:
        return (
            "Train("
            f"id={self.id}, "
            f"length={self.length}, "
            f"direction={self.direction}, "
            f"position={self.position}"
            ")"
        )

    def move(self,start_of_route, end_of_route):
        next_move = self.position + (1 * self.direction)
        if next_move < start_of_route or next_move > end_of_route:
            self.switch_direction()
            self.position = self.position + (1 * self.direction)
        else:
            self.position = next_move

        print(self)

    def switch_direction(self):
        if self.direction == -1:
            self.direction = 1
        elif self.direction == 1:
            self.direction = -1    


class Station():
    id: int
    position: int

    def __init__(self, id, position) -> None:
        self.id = id
        self.position = position

    def __str__(self) -> str:
        return (
            "Station("
            f"id={self.id}, "
            f"position={self.position}"
            ")"
        )


class Route():
    id: int
    stations: list[Station]
    trains: list[Train]
    color: tuple[int, int, int]
    max_led_count: int
    start_of_route: int
    end_of_route: int

    # station_information is a var that will get a array of numbers representing the route defined in main.py
    def __init__(self, id, route_information, trains, color, start_of_route) -> None:
        self.id = id

        station_id = 0
        stations: list[Station] = []

        position_tracker = start_of_route
        self.max_led_count = 0

        for number_led in route_information:
            station = Station(id=station_id, position=position_tracker)
            position_tracker += number_led
            if station:
                stations.append(station)
            else:
                print(f"Error while creating station: {station_id}")
            station_id += 1
            self.max_led_count += number_led

        self.stations = stations

        self.trains = trains

        self.color = color

        self.start_of_route = start_of_route
        self.end_of_route = start_of_route + self.max_led_count - 1

    def __str__(self) -> str:
        return (
            "Route("
            f"id={self.id}, "
            f"stations=[{', '.join(str(station) for station in self.stations)}], "
            f"trains=[{', '.join(str(train) for train in self.trains)}], "
            f"color={self.color}, "
            f"max_led_count={self.max_led_count}, "
            f"start_of_route={self.start_of_route}, "
            f"end_of_route={self.end_of_route}"
            ")"
        )

    def move_trains(self):
        for train in self.trains:
            train.move(self.start_of_route, self.end_of_route)

class Controller():
    routes: list[Route]
    delay: int = 50
    strip: PixelStrip

    def __init__(self, routes, strip) -> None:
        self.routes = routes
        self.strip = strip

    def __str__(self) -> str:
        return (
            "Controller("
            f"routes=[{', '.join(str(route) for route in self.routes)}], "
            f"delay={self.delay}, "
            f"strip_pixels={self.strip.numPixels()}"
            ")"
        )

    def show(self, route: Route):
        for i in range(self.strip.numPixels()):
            for station in route.stations:
                if station.position == i:
                    self.strip.setPixelColor(i, Color(255, 255, 255))
            for train in route.trains:
                if train.position == i:
                    self.strip.setPixelColor(i, Color(255, 0, 0))
        self.strip.show()

    def reset_strip(self):
        for i in range(self.strip.numPixels()):
            self.strip.setPixelColor(i, Color(0, 0, 0))

    def start(self):
        for _ in range(0, 500):
            for route in self.routes:
                route.move_trains()
                self.reset_strip()
                self.show(route)
                time.sleep(self.delay / 1000)
                