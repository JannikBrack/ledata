import time

from rpi_ws281x import PixelStrip, Color

class Train():
    id: int
    length: int = 2
    direction: int
    distance: int # distance to next station
    position: int
    ticks_to_move: int # countdown until the next led step
    ticks_per_led: int # ticks the train needs for a single led step
    minute_value: int # the number of ticks needet to complete a hole minute
    travel_time_in_minutes: float # time the train needs between two stations

    def __init__(self, id, direction, position, travel_time_in_minutes=1.0) -> None:
        self.id = id
        self.direction = direction
        self.position = position
        self.travel_time_in_minutes = travel_time_in_minutes
        self.distance = 0
        self.minute_value = 600
        self.ticks_per_led = 1
        self.ticks_to_move = 1

    def __str__(self) -> str:
        return (
            "Train("
            f"id={self.id}, "
            f"length={self.length}, "
            f"direction={self.direction}, "
            f"position={self.position}"
            ")"
        )

    def move(self, route):
        self.ticks_to_move -= 1
        if self.ticks_to_move > 0:
            return

        next_move = self.position + (1 * self.direction)
        if next_move < route.start_of_route or next_move > route.end_of_route:
            self.switch_direction()
            next_move = self.position + (1 * self.direction)
        self.position = next_move

        # a new schedule is only needed once the train reaches the next station
        if route.is_station(self.position):
            self.refresh_schedule(route)
        else:
            self.ticks_to_move = self.ticks_per_led

        print(self)

    def switch_direction(self):
        if self.direction == -1:
            self.direction = 1
        elif self.direction == 1:
            self.direction = -1    

    def refresh_schedule(self, route):
        distance = route.distance_to_next_station(self.position, self.direction)
        if distance == 0:
            # no station left in front of the train -> it is at the end of the route
            self.switch_direction()
            distance = route.distance_to_next_station(self.position, self.direction)
        self.distance = distance
        self.calculate_arrival(self.travel_time_in_minutes)

    def calculate_arrival(self, duration_in_minutes):
        if self.distance <= 0:
            self.ticks_per_led = 1
        else:
            self.ticks_per_led = max(1, round((duration_in_minutes * self.minute_value) / self.distance))
        self.ticks_to_move = self.ticks_per_led

    def calculate_delay(self, delay_in_minutes):
        self.ticks_to_move += round(delay_in_minutes * self.minute_value)


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

    def is_station(self, position) -> bool:
        return any(station.position == position for station in self.stations)

    def distance_to_next_station(self, position, direction) -> int:
        positions_ahead = [
            station.position
            for station in self.stations
            if (station.position - position) * direction > 0
        ]
        if not positions_ahead:
            return 0
        next_position = min(positions_ahead) if direction > 0 else max(positions_ahead)
        return abs(next_position - position)

    def move_trains(self):
        for train in self.trains:
            train.move(self)

class Controller():
    routes: list[Route]
    tickinterval: int = 100 # in ms | Tickinterval 100 ms -> 1 Minute = 60 Sekunden = 60.000 Milisekunden = 600 Ticks 
    strip: PixelStrip
    stopped: bool = True

    def __init__(self, routes, strip) -> None:
        self.routes = routes
        self.strip = strip

    def __str__(self) -> str:
        return (
            "Controller("
            f"routes=[{', '.join(str(route) for route in self.routes)}], "
            f"tickinterval={self.tickinterval}, "
            f"strip_pixels={self.strip.numPixels()}"
            ")"
        )

    def draw(self, route: Route):
        for i in range(self.strip.numPixels()):
            for station in route.stations:
                if station.position == i:
                    self.strip.setPixelColor(i, Color(255, 255, 255))
            for train in route.trains:
                if train.position == i:
                    self.strip.setPixelColor(i, Color(*route.color))

    def reset_strip(self):
        for i in range(self.strip.numPixels()):
            self.strip.setPixelColor(i, Color(0, 0, 0))

    def start(self):
        self.stopped = False
        minute_value = round(60000 / self.tickinterval)
        for route in self.routes:
            for train in route.trains:
                train.minute_value = minute_value
                train.refresh_schedule(route)
        while not self.stopped:
            self.reset_strip()
            for route in self.routes:
                route.move_trains()
                self.draw(route)
            self.strip.show()
            time.sleep(self.tickinterval / 1000)

    def stop(self):
        self.stopped = True


# Kontroller move requests (intervall mäßig) und der Zug macht die Valedierungen jeh nach dem ob er sich bewegen darf anhand der ausgerechneten 
# led/time variable, welche berechnet wird um zu definieren wie lange der zug brauchen darf um an der nächsten haltestelle anzukommen
# definierter Tickinterval 100 ms -> 1 Minute = 60 Sekunden = 60.000 Milisekunden = 600 Ticks 