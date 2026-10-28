# meta.json enthaelt die Konfiguration (LED-Strip, Linien, Zuege), fahrplan.json die Umlaeufe

# Wichtige information --------
# Jeder Zug hat im Fahrplan einen eigenen Umlauf mit echten UTC-Zeiten

import argparse
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from classes import Route, Train, Trip, Stop, Controller
from led_backend import PixelStrip, FakeStrip, HAVE_RPI
from ui import run_ui

META_PATH = Path(__file__).with_name("meta.json")
FAHRPLAN_PATH = Path(__file__).with_name("fahrplan.json")
LOG = logging.getLogger(__name__)


def load_json(path):
    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


def build_strip(led_config, dry_run=False):
    if dry_run or not HAVE_RPI:
        # ohne Hardware: LED-Streifen als ASCII-Zeile im Terminal
        return FakeStrip(led_config["count"], render=True)
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
                    Stop(
                        stop["station_id"],
                        stop["arrival"],
                        stop["departure"],
                        stop.get("delay_in_sec", 0),
                    )
                    for stop in trip_config["stops"]
                ],
                cycle_seconds=trip_config.get("cycle_seconds"),
            )
            trip.rebase_to_date(day)
            trips.append(trip)
        return trips
    return []


def journeys_to_trips(journeys):
    """Wandelt Live-Fahrten (live_feed.LiveJourney) in einmalige Trips um.

    Die Echtzeit (Prognose) steckt schon in arrival/departure, delay bleibt 0.
    """
    trips = []
    for journey in journeys:
        stops = [Stop(call.station_id, call.arrival, call.departure, 0) for call in journey.calls]
        trips.append(Trip(id=journey.journey_ref, train_id=journey.journey_ref, stops=stops, cyclic=False))
    return trips


def _format_log_time(value):
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _log_live_snapshot(route_config, journeys):
    station_names = {
        station["id"]: station.get("name", str(station["id"]))
        for station in route_config["stations"]
    }
    route_name = route_config.get("name", route_config["id"])
    LOG.info(
        "Route %s (%s): %d Bahnen live",
        route_config["id"],
        route_name,
        len(journeys),
    )
    for journey in journeys:
        LOG.info(
            "TRIAS Fahrt %s auf Route %s: Linie %s, Ziel %s",
            journey.journey_ref,
            route_name,
            journey.line_name or journey.line_ref or "unbekannt",
            journey.destination or "unbekannt",
        )
        for call in journey.calls:
            LOG.info(
                "  Halt %s: Ankunft prognostiziert %s, fahrplanmaessig %s",
                station_names.get(call.station_id, str(call.station_id)),
                _format_log_time(call.arrival),
                _format_log_time(call.planned_arrival),
            )


def build_live_source(meta):
    """Liefert eine Funktion now -> {route_id: [Trip]} auf Basis der TRIAS-API."""
    from live_feed import LiveFeed, TriasClient, load_requestor_key

    trias = meta["trias"]
    key = load_requestor_key(trias.get("requestor_key_env", "TRIAS_REQUESTOR_KEY"))
    client = TriasClient(trias["endpoint"], key)
    feed = LiveFeed(
        client,
        meta["routes"],
        lookback_minutes=trias.get("lookback_minutes", 45),
        lead_seconds=trias.get("lead_seconds", 120),
    )
    route_configs = {route["id"]: route for route in meta["routes"]}

    def source(now):
        snapshot = feed.fetch(now)
        for route_id, journeys in snapshot.items():
            route_config = route_configs.get(route_id)
            if route_config is not None:
                _log_live_snapshot(route_config, journeys)
        return {route_id: journeys_to_trips(journeys) for route_id, journeys in snapshot.items()}

    return source


def build_route(route_config, fahrplan, day, live=False):
    station_names = {
        station["id"]: station.get("name", str(station["id"]))
        for station in route_config["stations"]
    }
    if live:
        # Live-Modus: die Zuege kommen zur Laufzeit aus der API (Route.set_trips)
        return Route(
            route_config["id"],
            route_config["led_layout"],
            [],
            tuple(route_config["color"]),
            route_config["start_of_route"],
            [],
            station_names=station_names,
            name=route_config.get("name", f"Linie {route_config['id']}"),
        )
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
        station_names=station_names,
        name=route_config.get("name", f"Linie {route_config['id']}"),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Freiburger Stadtbahnen auf dem LED-Streifen")
    parser.add_argument("--source", choices=["live", "fahrplan"], default="live",
                        help="live = Echtzeit aus der TRIAS-API (Standard), fahrplan = fahrplan.json")
    parser.add_argument("--dry-run", action="store_true",
                        help="ohne LED-Hardware laufen, Streifen als ASCII im Terminal zeigen")
    ui_group = parser.add_mutually_exclusive_group()
    ui_group.add_argument("--ui", dest="ui", action="store_true",
                          help="Touchscreen-UI im Vollbild starten")
    ui_group.add_argument("--terminal", dest="ui", action="store_false",
                          help="bisherigen Terminalbetrieb verwenden")
    parser.set_defaults(ui=None)
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")

    meta = load_json(META_PATH)
    live = args.source == "live"
    fahrplan = [] if live else load_json(FAHRPLAN_PATH)["fahrplan"]
    today = datetime.now(timezone.utc).date()

    strip = build_strip(meta["led"], dry_run=args.dry_run)
    # Muss einmal aufgerufen werden, bevor setPixelColor()/show() benutzt wird
    strip.begin()

    routes = [build_route(route_config, fahrplan, today, live=live) for route_config in meta["routes"]]

    controller = Controller(routes, strip)
    controller.tickinterval = meta["tickinterval_ms"]
    controller.resync_interval_seconds = meta.get("resync_interval_seconds", 60)
    if live:
        controller.trip_source = build_live_source(meta)
        controller.live_refresh_seconds = meta["trias"].get("poll_interval_seconds", 30)
    use_ui = args.ui if args.ui is not None else HAVE_RPI and not args.dry_run
    try:
        if use_ui:
            run_ui(routes, controller)
        else:
            controller.start()
    except KeyboardInterrupt:
        pass
    finally:
        controller.stop()
        controller.reset_strip()
        strip.show()
    if not use_ui:
        print()
