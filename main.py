# Alle Konfigurationen (LED-Strip, Linien, Züge, Fahrzeiten) stehen in fahrplan.json

# Wichtige information --------
# Trains müssen auf bahnhöfen starten

import json
from pathlib import Path

from classes import Route, Train, Controller
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


def build_route(route_config):
    travel_time_in_minutes = route_config["default_travel_time_seconds"] / 60

    # Die Startposition eines Zuges wird über die Haltestellen-Id angegeben
    station_positions = {
        station["id"]: station["position"] for station in route_config["stations"]
    }

    trains = [
        Train(
            id=train["id"],
            direction=train["direction"],
            position=station_positions[train["start_station"]],
            travel_time_in_minutes=travel_time_in_minutes,
        )
        for train in route_config["trains"]
    ]

    return Route(
        route_config["id"],
        route_config["led_layout"],
        trains,
        tuple(route_config["color"]),
        route_config["start_of_route"],
    )


if __name__ == "__main__":
    config = load_config()
    meta = config["meta"]

    strip = build_strip(meta["led"])
    # Muss einmal aufgerufen werden, bevor setPixelColor()/show() benutzt wird
    strip.begin()

    routes = [build_route(route_config) for route_config in meta["routes"]]

    controller = Controller(routes, strip)
    controller.tickinterval = meta["tickinterval_ms"]
    controller.start()