import math
import time
from datetime import datetime, timedelta, timezone

from rpi_ws281x import PixelStrip, Color


def parse_utc(value) -> datetime:
    """Wandelt einen ISO-8601-Zeitstempel (z. B. '2026-01-01T05:00:00Z') in eine UTC-datetime um."""
    if isinstance(value, datetime):
        moment = value
    else:
        moment = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


def format_utc(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


class Stop():
    """Ein Halt im Fahrplan mit echter Ankunfts- und Abfahrtszeit in UTC."""
    station_id: int
    arrival: datetime
    departure: datetime

    def __init__(self, station_id, arrival, departure) -> None:
        self.station_id = station_id
        self.arrival = parse_utc(arrival)
        self.departure = parse_utc(departure)

    @property
    def dwell_seconds(self) -> float:
        # Haltedauer ergibt sich aus Abfahrtszeit minus Ankunftszeit
        return max(0.0, (self.departure - self.arrival).total_seconds())

    def __str__(self) -> str:
        return (
            "Stop("
            f"station_id={self.station_id}, "
            f"arrival={format_utc(self.arrival)}, "
            f"departure={format_utc(self.departure)}, "
            f"dwell_seconds={self.dwell_seconds:.0f}"
            ")"
        )


class Trip():
    """Ein kompletter Umlauf eines Zuges, beschrieben durch seine Halte.

    Der Umlauf laeuft von der ersten bis zur letzten Station und wieder zurueck.
    Nach cycle_seconds beginnt er von vorne, deshalb steht die Startstation nur
    einmal (am Anfang) in der Liste.
    """
    id: str
    train_id: int
    stops: list[Stop]
    delay_seconds: float
    cycle_seconds: float

    def __init__(self, id, train_id, stops, delay_seconds=0.0, cycle_seconds=None) -> None:
        self.id = id
        self.train_id = train_id
        self.stops = stops
        self.delay_seconds = delay_seconds
        if cycle_seconds:
            self.cycle_seconds = float(cycle_seconds)
        else:
            self.cycle_seconds = (stops[-1].departure - stops[0].arrival).total_seconds()

    def __str__(self) -> str:
        return (
            "Trip("
            f"id={self.id}, "
            f"train_id={self.train_id}, "
            f"stops={len(self.stops)}, "
            f"delay_seconds={self.delay_seconds:.0f}, "
            f"cycle_seconds={self.cycle_seconds:.0f}"
            ")"
        )

    def rebase_to_date(self, day):
        """Verschiebt den kompletten Umlauf auf das angegebene Datum (UTC).

        Die Abstaende zwischen den Halten bleiben dabei unveraendert, ein
        Umlauf ueber Mitternacht bleibt also korrekt.
        """
        first = self.stops[0].arrival
        anchor = datetime.combine(day, first.timetz())
        shift = anchor - first
        if not shift:
            return
        for stop in self.stops:
            stop.arrival += shift
            stop.departure += shift

    @property
    def cycle(self) -> timedelta:
        return timedelta(seconds=self.cycle_seconds)

    @property
    def start_time(self) -> datetime:
        return self.arrival_at(0)

    def arrival_at(self, index) -> datetime:
        return self.stops[index].arrival + timedelta(seconds=self.delay_seconds)

    def departure_at(self, index) -> datetime:
        return self.stops[index].departure + timedelta(seconds=self.delay_seconds)

    def dwell_seconds_at(self, index) -> float:
        return self.stops[index].dwell_seconds

    def cycle_offset(self, now) -> timedelta:
        """Wie weit der laufende Zyklus gegenueber dem Fahrplan verschoben ist."""
        return math.floor((now - self.start_time) / self.cycle) * self.cycle

    def locate(self, now):
        """Wo sich der Zug zum Zeitpunkt 'now' befindet.

        Liefert (index, zustand, beginn, ende):
        - zustand 'haltend': der Zug steht am Halt 'index', beginn/ende sind
          seine Ankunfts- und Abfahrtszeit
        - zustand 'fahrend': der Zug ist unterwegs vom Halt 'index' zum
          naechsten, beginn/ende sind Abfahrts- und Ankunftszeit
        """
        offset = self.cycle_offset(now)
        last = len(self.stops) - 1
        for index in range(len(self.stops)):
            arrival = self.arrival_at(index) + offset
            if now < arrival:
                previous = index - 1
                if previous < 0:
                    return last, "fahrend", self.departure_at(last) + offset - self.cycle, arrival
                return previous, "fahrend", self.departure_at(previous) + offset, arrival
            if now < self.departure_at(index) + offset:
                return index, "haltend", arrival, self.departure_at(index) + offset
        # nach der letzten Abfahrt faehrt der Zug zurueck zum Start des naechsten Zyklus
        return last, "fahrend", self.departure_at(last) + offset, self.arrival_at(0) + offset + self.cycle


class Train():
    id: int
    length: int = 2
    trip: Trip
    direction: int
    distance: int # distance to next station
    position: int
    target_position: int # led position of the next stop
    stop_index: int # index of the current stop in the trip
    next_index: int # index of the next stop in the trip
    cycle_offset: timedelta # shift of the running cycle against the timetable
    ticks_to_move: int # countdown until the next led step
    ticks_per_led: int # ticks the train needs for a single led step
    minute_value: int # the number of ticks needet to complete a hole minute
    at_station: bool # True while the train is standing in a station
    departure_time: datetime | None # geplante Abfahrtszeit am aktuellen Halt (UTC)
    arrival_time: datetime | None # geplante Ankunftszeit am naechsten Halt (UTC)

    def __init__(self, id, trip) -> None:
        self.id = id
        self.trip = trip
        self.direction = 1
        self.position = 0
        self.target_position = 0
        self.stop_index = 0
        self.next_index = 0
        self.cycle_offset = timedelta(0)
        self.distance = 0
        self.minute_value = 600
        self.ticks_per_led = 1
        self.ticks_to_move = 1
        self.at_station = False
        self.departure_time = None
        self.arrival_time = None

    def __str__(self) -> str:
        return (
            "Train("
            f"id={self.id}, "
            f"length={self.length}, "
            f"direction={self.direction}, "
            f"position={self.position}, "
            f"stop={self.trip.stops[self.stop_index].station_id}, "
            f"departure={format_utc(self.departure_time) if self.departure_time else '-'}, "
            f"arrival={format_utc(self.arrival_time) if self.arrival_time else '-'}"
            ")"
        )

    def move(self, route):
        self.ticks_to_move -= 1
        if self.ticks_to_move > 0:
            return

        if self.position != self.target_position:
            self.position += self.direction

        if self.position == self.target_position:
            # der naechste Halt ist erreicht -> Haltezeit und naechster Abschnitt
            self.stop_index = self.next_index
            self.at_station = True
            self.plan_next_leg(route)
            self.ticks_to_move += self.seconds_to_ticks(self.trip.dwell_seconds_at(self.stop_index))
        else:
            self.at_station = False
            self.ticks_to_move = self.ticks_per_led

        print(self)

    def occupied_positions(self) -> list[int]:
        # the train covers its head position plus the leds behind it
        return [self.position - offset * self.direction for offset in range(self.length)]

    def seconds_to_ticks(self, seconds) -> int:
        return max(0, round(seconds * self.minute_value / 60))

    def set_pace(self, travel_seconds, distance):
        ticks = self.seconds_to_ticks(travel_seconds)
        self.ticks_per_led = max(1, round(ticks / distance)) if distance > 0 else 1
        self.ticks_to_move = self.ticks_per_led

    def plan_next_leg(self, route):
        """Plant den Abschnitt vom aktuellen Halt zum naechsten Halt des Umlaufs."""
        trip = self.trip
        index = self.stop_index
        departure = trip.departure_at(index) + self.cycle_offset

        next_index = index + 1
        if next_index >= len(trip.stops):
            # der Umlauf beginnt von vorne
            next_index = 0
            self.cycle_offset += trip.cycle
        arrival = trip.arrival_at(next_index) + self.cycle_offset

        self.next_index = next_index
        self.departure_time = departure
        self.arrival_time = arrival

        self.position = route.position_of_station(trip.stops[index].station_id)
        self.target_position = route.position_of_station(trip.stops[next_index].station_id)
        self.distance = abs(self.target_position - self.position)
        self.direction = 1 if self.target_position >= self.position else -1
        # Fahrzeit ergibt sich aus der Ankunftszeit am naechsten Halt
        self.set_pace((arrival - departure).total_seconds(), self.distance)

    def sync_to_time(self, route, now):
        """Setzt den Zug auf die Position, die zur aktuellen Uhrzeit gehoert."""
        trip = self.trip
        self.cycle_offset = trip.cycle_offset(now)
        index, state, begin, end = trip.locate(now)
        self.stop_index = index
        self.at_station = state == "haltend"
        self.plan_next_leg(route)

        if self.at_station:
            # nur die restliche Haltezeit abwarten
            self.ticks_to_move = self.ticks_per_led + self.seconds_to_ticks((end - now).total_seconds())
            return

        # unterwegs: Position zwischen den beiden Haltestellen interpolieren
        span = abs(self.target_position - self.position)
        total = (end - begin).total_seconds()
        progress = (now - begin).total_seconds() / total if total > 0 else 1.0
        progress = min(max(progress, 0.0), 1.0)
        steps = min(int(progress * span), max(span - 1, 0))
        self.position += steps * self.direction
        remaining_leds = max(1, abs(self.target_position - self.position))
        self.set_pace(max(0.0, (end - now).total_seconds()), remaining_leds)


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
    trips: list[Trip]
    color: tuple[int, int, int]
    max_led_count: int
    start_of_route: int
    end_of_route: int

    # station_information is a var that will get a array of numbers representing the route defined in main.py
    def __init__(self, id, route_information, trains, color, start_of_route, trips=None) -> None:
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

        self.trips = trips or []

        self.color = color

        self.start_of_route = start_of_route
        self.end_of_route = start_of_route + self.max_led_count - 1

    def __str__(self) -> str:
        return (
            "Route("
            f"id={self.id}, "
            f"stations=[{', '.join(str(station) for station in self.stations)}], "
            f"trains=[{', '.join(str(train) for train in self.trains)}], "
            f"trips=[{', '.join(str(trip) for trip in self.trips)}], "
            f"color={self.color}, "
            f"max_led_count={self.max_led_count}, "
            f"start_of_route={self.start_of_route}, "
            f"end_of_route={self.end_of_route}"
            ")"
        )

    def is_station(self, position) -> bool:
        return any(station.position == position for station in self.stations)

    def position_of_station(self, station_id) -> int:
        for station in self.stations:
            if station.id == station_id:
                return station.position
        return self.start_of_route

    def trip_for_train(self, train_id):
        for trip in self.trips:
            if trip.train_id == train_id:
                return trip
        return None

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
    blink_interval: int = 800 # in ms | on/off time of a train standing in a station
    resync_interval_seconds: float = 60.0 # wie oft die Zuege gegen die UTC-Uhr abgeglichen werden
    ticks: int = 0
    strip: PixelStrip
    stopped: bool = True

    def __init__(self, routes, strip) -> None:
        self.routes = routes
        self.strip = strip
        self.ticks = 0

    def __str__(self) -> str:
        return (
            "Controller("
            f"routes=[{', '.join(str(route) for route in self.routes)}], "
            f"tickinterval={self.tickinterval}, "
            f"strip_pixels={self.strip.numPixels()}"
            ")"
        )

    def is_blink_on(self) -> bool:
        ticks_per_blink = max(1, round(self.blink_interval / self.tickinterval))
        return (self.ticks // ticks_per_blink) % 2 == 0

    def draw(self, route: Route):
        blink_on = self.is_blink_on()
        stopped_positions = {train.position for train in route.trains if train.at_station}

        for station in route.stations:
            if station.position in stopped_positions:
                # TEMPORAER: waehrend der Haltezeit blinkt die Haltestelle rot
                self.set_pixel(station.position, Color(255, 0, 0) if blink_on else Color(0, 0, 0))
            else:
                self.set_pixel(station.position, Color(255, 255, 255))

        for train in route.trains:
            if train.at_station:
                # in a station the train is only the single blinking dot of the station
                continue
            for position in train.occupied_positions():
                self.set_pixel(position, Color(*route.color))

    def set_pixel(self, position, color):
        if 0 <= position < self.strip.numPixels():
            self.strip.setPixelColor(position, color)

    def reset_strip(self):
        for i in range(self.strip.numPixels()):
            self.strip.setPixelColor(i, Color(0, 0, 0))

    def sync_trains(self):
        """Setzt alle Zuege auf die Position, die zur aktuellen UTC-Zeit gehoert."""
        now = datetime.now(timezone.utc)
        for route in self.routes:
            for train in route.trains:
                train.sync_to_time(route, now)

    def start(self):
        self.stopped = False
        minute_value = round(60000 / self.tickinterval)
        for route in self.routes:
            for train in route.trains:
                train.minute_value = minute_value
        self.sync_trains()
        ticks_per_resync = max(1, round(self.resync_interval_seconds * 1000 / self.tickinterval))
        while not self.stopped:
            self.ticks += 1
            if self.ticks % ticks_per_resync == 0:
                # regelmaessiger Abgleich, damit sich Rundungsfehler nicht aufsummieren
                self.sync_trains()
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