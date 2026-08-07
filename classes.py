import time

from rpi_ws281x import PixelStrip, Color

class Train():
    _id: int
    _length: int = 2
    _direction: int
    _position: int

    def __init__(self, id, direction, position) -> None:
        self._id = id
        self._direction = direction
        self._position = position

    def __str__(self) -> str:
        return (
            "Train("
            f"id={self._id}, "
            f"length={self._length}, "
            f"direction={self._direction}, "
            f"position={self._position}"
            ")"
        )

    def move(self,start_of_route, end_of_route):
        next_move = self._position + (1 * self._direction)
        if next_move < start_of_route or next_move > end_of_route:
            self.switch_direction()
            self._position = self._position + (1 * self._direction)
        else:
            self._position = next_move

        print(self)

    def switch_direction(self):
        if self._direction == -1:
            self._direction = 1
        elif self._direction == 1:
            self._direction = -1    


class Station():
    _id: int
    _position: int

    def __init__(self, id, position) -> None:
        self._id = id
        self._position = position

    def __str__(self) -> str:
        return (
            "Station("
            f"id={self._id}, "
            f"position={self._position}"
            ")"
        )


class Route():
    _id: int
    _stations: list[Station]
    _trains: list[Train]
    _color: tuple[int, int, int]
    _max_led_count: int
    _start_of_route: int
    _end_of_route: int

    # station_information is a var that will get a array of numbers representing the route defined in main.py
    def __init__(self, id, route_information, trains, color, start_of_route) -> None:
        self._id = id

        station_id = 0
        stations: list[Station] = []

        position_tracker = start_of_route
        self._max_led_count = 0

        for number_led in route_information:
            station = Station(id=station_id, position=position_tracker)
            position_tracker += number_led
            if station:
                stations.append(station)
            else:
                print(f"Error while creating station: {station_id}")
            station_id += 1
            self._max_led_count += number_led

        self._stations = stations

        self._trains = trains

        self._color = color

        self._start_of_route = start_of_route
        self._end_of_route = start_of_route + self._max_led_count - 1

    def __str__(self) -> str:
        return (
            "Route("
            f"id={self._id}, "
            f"stations=[{', '.join(str(station) for station in self._stations)}], "
            f"trains=[{', '.join(str(train) for train in self._trains)}], "
            f"color={self._color}, "
            f"max_led_count={self._max_led_count}, "
            f"start_of_route={self._start_of_route}, "
            f"end_of_route={self._end_of_route}"
            ")"
        )

    def move_trains(self):
        for train in self._trains:
            train.move(self._start_of_route, self._end_of_route)

class Controller():
    _routes: list[Route]
    _delay: int = 200
    _strip: PixelStrip

    def __init__(self, routes, strip) -> None:
        self._routes = routes
        self._strip = strip

    def __str__(self) -> str:
        return (
            "Controller("
            f"routes=[{', '.join(str(route) for route in self._routes)}], "
            f"delay={self._delay}, "
            f"strip_pixels={self._strip.numPixels()}"
            ")"
        )

    def show(self, route: Route):
        for i in range(self._strip.numPixels()):
            for station in route._stations:
                if station._position == i:
                    self._strip.setPixelColor(i, Color(255, 255, 255))
            for train in route._trains:
                if train._position == i:
                    self._strip.setPixelColor(i, Color(255, 0, 0))
        self._strip.show()


    def start(self):
        for _ in range(0, 500):
            for route in self._routes:
                route.move_trains()
                self.show(route)
                time.sleep(self._delay / 1000)
                