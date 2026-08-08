# Alle Konfigurationen (LED-Strip, Linien, Züge, Fahrzeiten) stehen in fahrplan.json

# Wichtige information --------
# Jeder Zug hat im Fahrplan einen eigenen Umlauf mit echten UTC-Zeiten

import json
from datetime import datetime, timezone
from pathlib import Path

from classes import Route, Train, Trip, Stop, Controller
from rpi_ws281x import PixelStrip

CONFIG_PATH = Path(__file__).with_name("fahrplan.json")


def load_config(path=CONFIG_PATH):
    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


def build_strip(led_config):
    return PixelStrip(
        led_config["count"],
        led_config["pin"],
        led_config["freq_hz"],
        led_config["dma"],
        led_config["invert"],
        led_config["brightness"],
        led_config["channel"],
    )


def build_trips(fahrplan, route_id, day):
    # Alle Zeiten im Fahrplan sind echte UTC-Zeitstempel (ISO 8601) und werden
    # beim Laden auf das angegebene Datum umdatiert
    for entry in fahrplan:
        if entry["route_id"] != route_id:
            continue
        trips = []
        for trip_config in entry["trips"]:
            trip = Trip(
                id=trip_config["id"],
                train_id=trip_config["train_id"],
                stops=[
                    Stop(stop["station_id"], stop["arrival"], stop["departure"])
                    for stop in trip_config["stops"]
                ],
                delay_seconds=trip_config.get("delay_seconds", 0),
                cycle_seconds=trip_config.get("cycle_seconds"),
            )
            trip.rebase_to_date(day)
            trips.append(trip)
        return trips
    return []


def build_route(route_config, fahrplan, day):
    trips = build_trips(fahrplan, route_config["id"], day)
    trips_by_train = {trip.train_id: trip for trip in trips}

    # Richtung und Startposition ergeben sich aus dem Umlauf und der aktuellen Uhrzeit
    trains = [
        Train(id=train["id"], trip=trips_by_train[train["id"]])
        for train in route_config["trains"]
    ]

    return Route(
        route_config["id"],
        route_config["led_layout"],
        trains,
        tuple(route_config["color"]),
        route_config["start_of_route"],
        trips,
    )


if __name__ == "__main__":
    config = load_config()
    meta = config["meta"]
    fahrplan = config["fahrplan"]
    today = datetime.now(timezone.utc).date()

    strip = build_strip(meta["led"])
    # Muss einmal aufgerufen werden, bevor setPixelColor()/show() benutzt wird
    strip.begin()

    routes = [build_route(route_config, fahrplan, today) for route_config in meta["routes"]]

    controller = Controller(routes, strip)
    controller.tickinterval = meta["tickinterval_ms"]
    controller.resync_interval_seconds = meta.get("resync_interval_seconds", 60)
    controller.start()