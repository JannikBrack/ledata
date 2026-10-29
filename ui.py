"""Touchscreen UI for selecting routes and live trains on the LED board."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from queue import Empty, Queue
from threading import Thread

from classes import (
    Controller,
    Route,
    RouteConnection,
    Train,
    Trip,
    train_direction_destination_id,
)


@dataclass(frozen=True)
class TrainInfo:
    train_id: str | int
    origin: str
    destination: str
    departure: datetime
    arrival: datetime
    current_delay: timedelta
    position: str
    direction_destination: str


@dataclass(frozen=True)
class StopTimelineEntry:
    name: str
    arrival: datetime | None
    departure: datetime | None = None
    is_closure: bool = False


@dataclass(frozen=True)
class StopTimeline:
    upcoming: tuple[StopTimelineEntry, ...]
    current: StopTimelineEntry
    past: tuple[StopTimelineEntry, ...]
    current_position: str
    next_destination: str
    closure_info: str | None = None


def _station_name(route: Route, station_id: int) -> str:
    return route.station_names.get(station_id, str(station_id))


def _trip_stop_entry(
    route: Route,
    trip: Trip,
    index: int,
    offset: timedelta = timedelta(0),
) -> StopTimelineEntry:
    stop = trip.stops[index]
    return StopTimelineEntry(
        _station_name(route, stop.station_id),
        trip.arrival_at(index) + offset,
        trip.departure_at(index) + offset,
    )


def train_stop_timeline(route: Route, train: Train) -> StopTimeline:
    stops = train.trip.stops
    if not stops:
        raise ValueError(f"Train {train.id} has no stops")

    offset = train.cycle_offset if train.trip.cyclic else timedelta(0)
    entries = [
        _trip_stop_entry(route, train.trip, index, offset)
        for index in range(len(stops))
    ]
    current_index = min(max(train.stop_index, 0), len(stops) - 1)
    next_index = train.next_index
    next_name = (
        _station_name(route, stops[next_index].station_id)
        if 0 <= next_index < len(stops) and next_index != current_index
        else "Ziel erreicht"
    )
    upcoming = entries[current_index + 1:]
    past = entries[:current_index]
    if train.trip.cyclic and next_index == 0 and current_index == len(stops) - 1:
        upcoming = entries[:1]
        past = entries[1:current_index]

    current_name = entries[current_index].name
    current_position = (
        f"An Haltestelle {current_name}"
        if train.at_station
        else f"Zwischen {current_name} und {next_name}"
    )
    return StopTimeline(
        upcoming=tuple(upcoming),
        current=entries[current_index],
        past=tuple(past),
        current_position=current_position,
        next_destination=next_name,
    )


def connection_closure_info(route: Route, connection: RouteConnection) -> str:
    first_boundary = _station_name(route, connection.first_boundary_station_id)
    second_boundary = _station_name(route, connection.second_boundary_station_id)
    transfer_minutes = max(
        0,
        round(
            (
                connection.transfer_departure
                - connection.transfer_arrival
            ).total_seconds()
            / 60
        ),
    )
    return (
        f"Baustelle: {first_boundary} → {second_boundary}"
        f" · Fußweg/Umstieg {transfer_minutes} min"
    )


def connection_stop_timeline(
    route: Route,
    connection: RouteConnection,
    now: datetime | None = None,
) -> StopTimeline | None:
    first_stops = connection.first_stops
    second_stops = connection.second_stops
    if not first_stops or not second_stops:
        return None
    if (
        first_stops[-1].station_id != connection.first_boundary_station_id
        or second_stops[0].station_id != connection.second_boundary_station_id
    ):
        return None

    first_entries = [
        StopTimelineEntry(
            _station_name(route, stop.station_id),
            stop.arrival,
            stop.departure,
        )
        for stop in first_stops
    ]
    second_entries = [
        StopTimelineEntry(
            _station_name(route, stop.station_id),
            stop.arrival,
            stop.departure,
        )
        for stop in second_stops
    ]
    first_boundary = _station_name(route, connection.first_boundary_station_id)
    second_boundary = _station_name(route, connection.second_boundary_station_id)
    closure_entry = StopTimelineEntry(
        f"Baustelle / Fußweg: {first_boundary} → {second_boundary}",
        None,
        is_closure=True,
    )
    moment = now or datetime.now(timezone.utc)
    closure_info = connection_closure_info(route, connection)
    if moment < connection.transfer_arrival:
        first_trip = Trip(
            connection.first_trip_id or "first-leg",
            connection.first_trip_id or "first-leg",
            list(first_stops),
            cyclic=False,
        )
        index, state, _, _ = first_trip.locate(moment)
        current = first_entries[index]
        past = first_entries[:index]
        upcoming = (
            first_entries[index + 1:]
            + [closure_entry]
            + second_entries
        )
        current_name = current.name
        if index + 1 < len(first_entries):
            next_name = first_entries[index + 1].name
        else:
            next_name = second_entries[0].name
        position = (
            f"An Haltestelle {current_name}"
            if state == "haltend"
            else f"Zwischen {current_name} und {next_name}"
        )
    elif moment < connection.transfer_departure:
        current = closure_entry
        past = first_entries
        upcoming = second_entries
        position = f"Zu Fuß zwischen {first_boundary} und {second_boundary}"
        next_name = second_entries[0].name
    else:
        second_trip = Trip(
            connection.second_trip_id or "second-leg",
            connection.second_trip_id or "second-leg",
            list(second_stops),
            cyclic=False,
        )
        index, state, _, _ = second_trip.locate(moment)
        current = second_entries[index]
        past = first_entries + [closure_entry] + second_entries[:index]
        upcoming = second_entries[index + 1:]
        current_name = current.name
        next_name = (
            second_entries[index + 1].name
            if index + 1 < len(second_entries)
            else "Ziel erreicht"
        )
        position = (
            f"An Haltestelle {current_name}"
            if state == "haltend"
            else f"Zwischen {current_name} und {next_name}"
        )

    return StopTimeline(
        upcoming=tuple(upcoming),
        current=current,
        past=tuple(past),
        current_position=position,
        next_destination=next_name,
        closure_info=closure_info,
    )


def direction_destination_id(route: Route, train: Train) -> int:
    return train_direction_destination_id(route, train)


def train_position(route: Route, train: Train) -> str:
    stops = train.trip.stops
    current_name = _station_name(route, stops[train.stop_index].station_id)
    if train.at_station:
        return f"An Haltestelle {current_name}"
    next_name = _station_name(route, stops[train.next_index].station_id)
    return f"Zwischen {current_name} und {next_name}"


def train_info(route: Route, train: Train) -> TrainInfo:
    stops = train.trip.stops
    offset = train.cycle_offset if train.trip.cyclic else timedelta(0)
    destination_id = direction_destination_id(route, train)
    reported_delay = stops[train.stop_index].reported_delay_seconds
    delay_seconds = (
        reported_delay
        if reported_delay is not None
        else train.trip.delay_at(train.stop_index).total_seconds()
    )
    return TrainInfo(
        train_id=train.trip.id,
        origin=_station_name(route, stops[0].station_id),
        destination=_station_name(route, stops[-1].station_id),
        departure=train.trip.departure_at(0) + offset,
        arrival=train.trip.arrival_at(len(stops) - 1) + offset,
        current_delay=timedelta(seconds=max(0.0, delay_seconds)),
        position=train_position(route, train),
        direction_destination=_station_name(route, destination_id),
    )


def filter_trains(
    route: Route,
    trains: list[Train],
    destination_id: int | None,
) -> list[Train]:
    if destination_id is None:
        return list(trains)
    return [
        train for train in trains
        if direction_destination_id(route, train) == destination_id
    ]


def walking_connection_instruction(
    route: Route,
    connection: RouteConnection,
) -> str:
    first = _station_name(route, connection.first_boundary_station_id)
    second = _station_name(route, connection.second_boundary_station_id)
    return f"Zu Fuß: {first} → {second}"


def filter_connections(
    connections: list[RouteConnection],
    destination_id: int | None,
) -> list[RouteConnection]:
    if destination_id is None:
        return list(connections)
    return [
        connection
        for connection in connections
        if connection.destination_station_id == destination_id
    ]


def route_direction_destination_ids(route: Route) -> tuple[int, int]:
    if not route.stations:
        raise ValueError(f"Route {route.id} has no stations")
    return route.stations[0].id, route.stations[-1].id


class TramUI:
    def __init__(
        self,
        root,
        routes: list[Route],
        controller: Controller,
        closure_store=None,
    ):
        import tkinter as tk
        from tkinter import messagebox, ttk

        self.tk = tk
        self.ttk = ttk
        self.messagebox = messagebox
        self.root = root
        self.routes = routes
        self.controller = controller
        self.closure_store = closure_store
        self.route: Route | None = None
        self.screen = "routes"
        self.direction_id: int | None = None
        self._row_trains: dict[str, Train] = {}
        self._row_connections: dict[str, RouteConnection] = {}
        self._filter_buttons = {}
        self._detail_train_id: str | int | None = None
        self._detail_connection_id: str | None = None
        self._detail_labels = {}
        self._detail_stop_tree = None

        self.root.title("Straßenbahn-Anzeige")
        self.root.attributes("-fullscreen", True)
        self.root.configure(background="#f3f5f7")
        self.root.bind("<Escape>", lambda _event: self.go_back())
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.controller.require_route_selection()
        self.show_routes()
        self.root.after(1000, self.refresh)

    def _clear(self):
        for child in self.root.winfo_children():
            child.destroy()

    def _header(self, title: str, back_label: str | None = None):
        tk = self.tk
        header = tk.Frame(self.root, background="#f3f5f7", padx=12, pady=8)
        header.pack(fill="x")
        if back_label:
            tk.Button(
                header,
                text=back_label,
                command=self.go_back,
                font=("TkDefaultFont", 15, "bold"),
                padx=14,
                pady=11,
            ).pack(side="left", padx=(0, 12))
        tk.Label(
            header,
            text=title,
            background="#f3f5f7",
            font=("TkDefaultFont", 20, "bold"),
            anchor="w",
        ).pack(side="left", fill="x", expand=True)
        tk.Button(
            header,
            text="Beenden",
            command=self.close,
            font=("TkDefaultFont", 14, "bold"),
            padx=12,
            pady=11,
        ).pack(side="right")

    def show_routes(self):
        self.controller.select_route(None)
        self.controller.select_train(None)
        self.controller.select_direction(None, None)
        self.route = None
        self.screen = "routes"
        self._clear()
        self._header("Linie auswählen")

        tk = self.tk
        body = tk.Frame(self.root, background="#f3f5f7", padx=12, pady=6)
        body.pack(fill="both", expand=True)
        if not self.routes:
            tk.Label(
                body,
                text="In meta.json sind keine Linien konfiguriert.",
                background="#f3f5f7",
                font=("TkDefaultFont", 18),
            ).pack(anchor="w", pady=12)
            return

        for index, route in enumerate(self.routes):
            card = tk.Frame(body, background="#f3f5f7")
            card.grid(
                row=index // 2,
                column=index % 2,
                sticky="nsew",
                padx=6,
                pady=6,
            )
            text_color = "black" if route.color == (255, 255, 0) else "white"
            tk.Button(
                card,
                text=(
                    f"{route.name} · ⚠ Baustelle"
                    if route.closed_section
                    else route.name
                ),
                command=lambda route_id=route.id: self.show_trains(route_id),
                background=self._color(route.color),
                foreground=text_color,
                activebackground=self._color(route.color),
                activeforeground=text_color,
                font=("TkDefaultFont", 20, "bold"),
                padx=16,
                pady=12,
                wraplength=320,
            ).pack(fill="both", expand=True)
            if self.closure_store is not None:
                tk.Button(
                    card,
                    text=(
                        "Baustelle bearbeiten"
                        if route.closed_section
                        else "Baustelle eintragen"
                    ),
                    command=lambda route_id=route.id: self.show_closure_editor(route_id),
                    font=("TkDefaultFont", 13, "bold"),
                    padx=8,
                    pady=8,
                ).pack(fill="x", pady=(5, 0))
        for column in range(2):
            body.grid_columnconfigure(column, weight=1)
        for row in range((len(self.routes) + 1) // 2):
            body.grid_rowconfigure(row, weight=1)

    def show_closure_editor(self, route_id: int):
        route = next(route for route in self.routes if route.id == route_id)
        self.route = route
        self.screen = "closure"
        self._clear()
        self._header(f"Baustelle · {route.name}", "Zurück")

        tk = self.tk
        ttk = self.ttk
        body = tk.Frame(self.root, background="#f3f5f7", padx=18, pady=18)
        body.pack(fill="both", expand=True)
        tk.Label(
            body,
            text="Baustelle von/bis festlegen:",
            background="#f3f5f7",
            font=("TkDefaultFont", 18, "bold"),
        ).pack(anchor="w", pady=(0, 10))

        self._closure_station_choices = {
            _station_name(route, station.id): station.id
            for station in route.stations
        }
        current = route.closed_section
        selected_from = next(
            (
                label
                for label, station_id in self._closure_station_choices.items()
                if current is not None and station_id == current[0]
            ),
            "",
        )
        selected_to = next(
            (
                label
                for label, station_id in self._closure_station_choices.items()
                if current is not None and station_id == current[1]
            ),
            "",
        )
        labels = list(self._closure_station_choices)
        self._closure_from_choice = tk.StringVar(value=selected_from)
        self._closure_to_choice = tk.StringVar(value=selected_to)
        tk.Label(
            body,
            text="Von",
            background="#f3f5f7",
            font=("TkDefaultFont", 15, "bold"),
        ).pack(anchor="w")
        ttk.Combobox(
            body,
            textvariable=self._closure_from_choice,
            values=labels,
            state="readonly",
            font=("TkDefaultFont", 16),
        ).pack(fill="x", pady=(0, 10))
        tk.Label(
            body,
            text="Bis",
            background="#f3f5f7",
            font=("TkDefaultFont", 15, "bold"),
        ).pack(anchor="w")
        ttk.Combobox(
            body,
            textvariable=self._closure_to_choice,
            values=labels,
            state="readonly",
            font=("TkDefaultFont", 16),
        ).pack(fill="x", pady=(0, 16))

        tk.Button(
            body,
            text="Baustelle speichern",
            command=lambda: self._save_closure(route),
            font=("TkDefaultFont", 16, "bold"),
            padx=14,
            pady=12,
        ).pack(anchor="w", pady=5)
        if current is not None:
            tk.Button(
                body,
                text="Baustelle entfernen",
                command=lambda: self._remove_closure(route),
                font=("TkDefaultFont", 16, "bold"),
                padx=14,
                pady=12,
            ).pack(anchor="w", pady=5)

    def _save_closure(self, route: Route):
        first_id = self._closure_station_choices.get(
            self._closure_from_choice.get()
        )
        second_id = self._closure_station_choices.get(
            self._closure_to_choice.get()
        )
        if first_id is None or second_id is None:
            self.messagebox.showerror(
                "Baustelle nicht gespeichert",
                "Bitte Von- und Bis-Haltestelle auswählen.",
                parent=self.root,
            )
            return
        if first_id == second_id:
            self.messagebox.showerror(
                "Baustelle nicht gespeichert",
                "Von- und Bis-Haltestelle müssen verschieden sein.",
                parent=self.root,
            )
            return
        station_ids = (first_id, second_id)
        try:
            if self.closure_store is not None:
                self.closure_store.set(route.id, station_ids)
            route.set_closed_section(station_ids)
        except OSError as exc:
            self.messagebox.showerror(
                "Baustelle nicht gespeichert",
                str(exc),
                parent=self.root,
            )
            return
        self.show_routes()

    def _remove_closure(self, route: Route):
        try:
            if self.closure_store is not None:
                self.closure_store.set(route.id, None)
            route.set_closed_section(None)
        except OSError as exc:
            self.messagebox.showerror(
                "Baustelle nicht entfernt",
                str(exc),
                parent=self.root,
            )
            return
        self.show_routes()

    @staticmethod
    def _color(rgb: tuple[int, int, int]) -> str:
        return "#%02x%02x%02x" % tuple(max(0, min(255, int(value))) for value in rgb)

    def show_trains(self, route_id: int):
        self.route = next(route for route in self.routes if route.id == route_id)
        self.controller.select_route(route_id)
        self.controller.select_train(None)
        self.controller.select_direction(None, None)
        self.screen = "trains"
        self.direction_id = None
        self._clear()
        route_title = (
            f"{self.route.name} · ⚠ Baustelle"
            if self.route.closed_section
            else self.route.name
        )
        self._header(route_title, "Linien")

        tk = self.tk
        ttk = self.ttk
        controls = tk.Frame(self.root, background="#f3f5f7", padx=10, pady=2)
        controls.pack(fill="x")

        endpoints = route_direction_destination_ids(self.route)
        options = {"Alle Richtungen": None}
        for station_id in endpoints:
            options[f"Nach {_station_name(self.route, station_id)}"] = station_id
        self._filter_buttons = {}
        for label, direction_id in options.items():
            button = tk.Button(
                controls,
                text=label,
                command=lambda selected_id=direction_id: self._select_direction(selected_id),
                font=("TkDefaultFont", 13, "bold"),
                padx=6,
                pady=9,
                wraplength=230,
                relief="raised",
                bd=2,
            )
            button.pack(side="left", fill="both", expand=True, padx=4, pady=3)
            self._filter_buttons[direction_id] = button
        self._update_filter_buttons()

        table_frame = tk.Frame(self.root, padx=10, pady=6)
        table_frame.pack(fill="both", expand=True)
        self._build_train_table(table_frame, ttk)

        self._empty_label = tk.Label(
            self.root,
            text="Es sind aktuell keine Bahnen verfügbar.",
            background="#f3f5f7",
            font=("TkDefaultFont", 14),
        )
        self._empty_label.pack(anchor="w", padx=12, pady=(0, 8))
        self._row_trains = {}
        self._row_connections = {}
        self._refresh_train_rows()

    def _build_train_table(self, parent, ttk):
        columns = ("journey", "delay", "departure", "arrival", "action")
        self._tree = ttk.Treeview(
            parent,
            columns=columns,
            show="headings",
            selectmode="browse",
            style="Touch.Treeview",
            cursor="hand2",
        )
        self._tree.heading("journey", text="Herkunft → Ziel")
        self._tree.heading("delay", text="Verspätung")
        self._tree.heading("departure", text="Abfahrt")
        self._tree.heading("arrival", text="Ankunft")
        self._tree.heading("action", text="")
        self._tree.column("journey", width=270, anchor="w", stretch=False)
        self._tree.column("delay", width=81, anchor="center", stretch=False)
        self._tree.column("departure", width=81, anchor="center", stretch=False)
        self._tree.column("arrival", width=81, anchor="center", stretch=False)
        self._tree.column("action", width=134, anchor="center", stretch=False)
        self._tree.bind("<Configure>", self._resize_train_columns, add="+")
        style = ttk.Style()
        style.configure(
            "Touch.Treeview",
            rowheight=72,
            font=("TkDefaultFont", 14),
            background="#ffffff",
            fieldbackground="#ffffff",
            foreground="#263238",
        )
        style.map(
            "Touch.Treeview",
            background=[("selected", "#246c98")],
            foreground=[("selected", "white")],
        )
        style.configure("Touch.Treeview.Heading", font=("TkDefaultFont", 13, "bold"))
        self._tree.tag_configure("row_even", background="#ffffff")
        self._tree.tag_configure("row_odd", background="#eaf1f6")
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=scrollbar.set)
        self._tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self._tree.bind("<<TreeviewSelect>>", self._train_selected)

    def _resize_train_columns(self, event):
        table_width = event.width
        journey_width = round(table_width * 0.35)
        remaining_width = table_width - journey_width
        other_columns = (
            ("delay", 120),
            ("departure", 120),
            ("arrival", 120),
            ("action", 200),
        )
        total_weight = sum(weight for _, weight in other_columns)
        assigned_width = 0
        for index, (column, weight) in enumerate(other_columns):
            if index == len(other_columns) - 1:
                width = remaining_width - assigned_width
            else:
                width = round(remaining_width * weight / total_weight)
                assigned_width += width
            self._tree.column(column, width=width)
        self._tree.column("journey", width=journey_width)

    def _select_direction(self, direction_id: int | None):
        if self.route is None:
            return
        self.direction_id = direction_id
        self.controller.select_direction(self.route.id, direction_id)
        self._update_filter_buttons()
        self._refresh_train_rows()

    def _update_filter_buttons(self):
        selected_background = (
            self._color(self.route.color) if self.route is not None else "#2f6f9f"
        )
        for direction_id, button in self._filter_buttons.items():
            selected = direction_id == self.direction_id
            button.configure(
                background=selected_background if selected else "#e2e7ec",
                foreground="white" if selected else "#263238",
                activebackground=selected_background if selected else "#d2dbe3",
                activeforeground="white" if selected else "#263238",
                relief="sunken" if selected else "raised",
            )

    def _refresh_train_rows(self):
        if self.screen != "trains" or self.route is None:
            return
        if self.route.closed_section is not None:
            visible_items = filter_connections(
                self.route.connections,
                self.direction_id,
            )
            self._refresh_connection_table(visible_items)
            empty_text = (
                "Es sind aktuell keine vollständigen Verbindungen in dieser "
                "Richtung verfügbar."
                if self.direction_id is not None
                else "Es sind aktuell keine vollständigen Verbindungen verfügbar."
            )
        else:
            visible_items = filter_trains(
                self.route,
                self.route.trains,
                self.direction_id,
            )
            self._refresh_train_table(visible_items)
            empty_text = (
                "Es sind aktuell keine Bahnen in dieser Richtung verfügbar."
                if self.direction_id is not None
                else "Es sind aktuell keine Bahnen verfügbar."
            )

        self._empty_label.configure(text=empty_text)
        if visible_items:
            self._empty_label.pack_forget()
        else:
            self._empty_label.pack(anchor="w", padx=12, pady=(0, 8))

    def _refresh_train_table(self, trains: list[Train]):
        visible_ids = set()
        row_trains = {}
        for index, train in enumerate(trains):
            row_id = str(train.trip.id)
            info = train_info(self.route, train)
            values = (
                f"{info.origin} → {info.destination}",
                self._format_delay(info.current_delay),
                self._format_time(info.departure),
                self._format_time(info.arrival),
                "Tippen: Details →",
            )
            tags = ("row_even" if index % 2 == 0 else "row_odd",)
            if self._tree.exists(row_id):
                self._tree.item(row_id, values=values, tags=tags)
            else:
                self._tree.insert("", "end", iid=row_id, values=values, tags=tags)
            visible_ids.add(row_id)
            row_trains[row_id] = train
        for row_id in self._tree.get_children():
            if row_id not in visible_ids:
                self._tree.delete(row_id)
        self._row_trains = row_trains
        self._row_connections = {}

    def _refresh_connection_table(self, connections: list[RouteConnection]):
        visible_ids = set()
        row_connections = {}
        for index, connection in enumerate(connections):
            row_id = f"connection-{connection.id}"
            values = (
                (
                    f"{_station_name(self.route, connection.origin_station_id)}"
                    f" → {_station_name(self.route, connection.destination_station_id)}"
                ),
                self._format_delay(timedelta(seconds=connection.delay_seconds)),
                self._format_time(connection.departure),
                self._format_time(connection.arrival),
                "Tippen: Details →",
            )
            tags = ("row_even" if index % 2 == 0 else "row_odd",)
            if self._tree.exists(row_id):
                self._tree.item(row_id, values=values, tags=tags)
            else:
                self._tree.insert("", "end", iid=row_id, values=values, tags=tags)
            visible_ids.add(row_id)
            row_connections[row_id] = connection
        for row_id in self._tree.get_children():
            if row_id not in visible_ids:
                self._tree.delete(row_id)
        self._row_trains = {}
        self._row_connections = row_connections

    def _train_selected(self, _event=None):
        selection = self._tree.selection()
        if not selection:
            return
        row_id = selection[0]
        if row_id in self._row_connections:
            self.show_connection_detail(self._row_connections[row_id])
        elif row_id in self._row_trains:
            self.show_train_detail(self._row_trains[row_id].trip.id)

    def show_train_detail(self, train_id: str | int):
        if self.route is None:
            return
        self._detail_train_id = train_id
        self._detail_connection_id = None
        self.controller.select_train(self.route.id, train_id)
        self.screen = "detail"
        self._clear()
        self._header(f"{self.route.name} · Bahn {train_id}", "Bahnauswahl")
        self._build_detail_content()
        self._refresh_detail()

    def show_connection_detail(self, connection: RouteConnection):
        if self.route is None:
            return
        self._detail_connection_id = connection.id
        self._detail_train_id = None
        self.controller.select_train(None)
        self.screen = "detail"
        origin = _station_name(self.route, connection.origin_station_id)
        destination = _station_name(self.route, connection.destination_station_id)
        self._clear()
        self._header(f"{self.route.name} · {origin} → {destination}", "Bahnauswahl")
        self._build_detail_content()
        self._refresh_detail()

    def _build_detail_content(self):
        content = self.tk.Frame(self.root, background="#f3f5f7", padx=18, pady=12)
        content.pack(fill="both", expand=True)
        self._detail_labels = {}
        for key in ("direction", "times", "delay", "current", "next"):
            label = self.tk.Label(
                content,
                background="#f3f5f7",
                font=("TkDefaultFont", 17 if key in ("delay", "current") else 16),
                anchor="w",
                justify="left",
                wraplength=740,
            )
            label.pack(fill="x", pady=2)
            self._detail_labels[key] = label

        stops_frame = self.tk.Frame(content, background="#f3f5f7")
        stops_frame.pack(fill="both", expand=True, pady=(4, 0))
        self._detail_section_label = self.tk.Label(
            stops_frame,
            text="Haltestellen · Ankunft und Abfahrt",
            background="#f3f5f7",
            font=("TkDefaultFont", 15, "bold"),
            anchor="w",
        )
        self._detail_section_label.pack(fill="x", pady=(0, 3))
        self._detail_closure_label = self.tk.Label(
            stops_frame,
            background="#fff0d6",
            foreground="#985400",
            font=("TkDefaultFont", 14, "bold"),
            anchor="w",
            justify="left",
            wraplength=740,
            padx=8,
            pady=6,
        )
        self._detail_stop_tree = self.ttk.Treeview(
            stops_frame,
            columns=("arrival", "departure"),
            show="tree headings",
            selectmode="none",
            style="Detail.Treeview",
        )
        self._detail_stop_tree.heading("#0", text="Haltestelle", anchor="w")
        self._detail_stop_tree.heading("arrival", text="Ankunft", anchor="center")
        self._detail_stop_tree.heading("departure", text="Abfahrt", anchor="center")
        self._detail_stop_tree.column("#0", width=360, anchor="w", stretch=True)
        self._detail_stop_tree.column("arrival", width=120, anchor="center", stretch=False)
        self._detail_stop_tree.column("departure", width=120, anchor="center", stretch=False)
        self._detail_stop_tree.bind(
            "<Configure>",
            self._resize_detail_columns,
            add="+",
        )
        style = self.ttk.Style()
        style.configure(
            "Detail.Treeview",
            rowheight=38,
            font=("TkDefaultFont", 13),
            background="#ffffff",
            fieldbackground="#ffffff",
            foreground="#263238",
        )
        style.configure("Detail.Treeview.Heading", font=("TkDefaultFont", 13, "bold"))
        self._detail_stop_tree.tag_configure(
            "group",
            background="#e2e7ec",
            foreground="#263238",
            font=("TkDefaultFont", 13, "bold"),
        )
        self._detail_stop_tree.tag_configure(
            "current",
            background="#c8f2d3",
            foreground="#12602d",
            font=("TkDefaultFont", 14, "bold"),
        )
        self._detail_stop_tree.tag_configure(
            "closure",
            background="#fff0d6",
            foreground="#985400",
        )
        self._detail_stop_tree.tag_configure("row", background="#ffffff")
        self._detail_stop_tree.tag_configure(
            "unavailable",
            background="#ffffff",
            foreground="#59636e",
        )
        scrollbar = self.ttk.Scrollbar(
            stops_frame,
            orient="vertical",
            command=self._detail_stop_tree.yview,
        )
        self._detail_stop_tree.configure(yscrollcommand=scrollbar.set)
        self._detail_stop_tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self._detail_stop_tree.bind(
            "<Button-1>",
            self._toggle_detail_group,
            add="+",
        )

    def _resize_detail_columns(self, event):
        table_width = event.width
        time_width = min(120, max(80, round(table_width * 0.18)))
        station_width = max(120, table_width - 2 * time_width - 4)
        self._detail_stop_tree.column("#0", width=station_width)
        self._detail_stop_tree.column("arrival", width=time_width)
        self._detail_stop_tree.column("departure", width=time_width)

    def _toggle_detail_group(self, event):
        item_id = self._detail_stop_tree.identify_row(event.y)
        if item_id not in {"upcoming", "past"}:
            return None
        is_open = bool(self._detail_stop_tree.item(item_id, "open"))
        self._detail_stop_tree.item(item_id, open=not is_open)
        return "break"

    def _upsert_detail_tree_item(
        self,
        item_id: str,
        parent_id: str,
        index: int,
        text: str,
        values: tuple[str, str],
        tag: str,
        open_state: bool | None = None,
    ):
        tree = self._detail_stop_tree
        if tree.exists(item_id):
            tree.item(item_id, text=text, values=values, tags=(tag,))
        else:
            options = {}
            if open_state is not None:
                options["open"] = open_state
            tree.insert(
                parent_id,
                index,
                iid=item_id,
                text=text,
                values=values,
                tags=(tag,),
                **options,
            )
        tree.move(item_id, parent_id, index)

    def _sync_detail_group(
        self,
        item_id: str,
        title: str,
        entries: tuple[StopTimelineEntry, ...],
        group_index: int,
    ):
        tree = self._detail_stop_tree
        is_existing = tree.exists(item_id)
        open_state = bool(tree.item(item_id, "open")) if is_existing else False
        self._upsert_detail_tree_item(
            item_id,
            "",
            group_index,
            title,
            ("", ""),
            "group",
            open_state=open_state,
        )
        desired_children = set()
        for index, entry in enumerate(entries):
            child_id = f"{item_id}-entry-{index}"
            desired_children.add(child_id)
            self._upsert_detail_tree_item(
                child_id,
                item_id,
                index,
                entry.name,
                (
                    self._format_time(entry.arrival) if entry.arrival else "",
                    self._format_time(entry.departure) if entry.departure else "",
                ),
                "closure" if entry.is_closure else "row",
            )
        for child_id in tree.get_children(item_id):
            if child_id not in desired_children:
                tree.delete(child_id)

    def _refresh_detail_stop_table(self, timeline: StopTimeline | None):
        if self._detail_stop_tree is None:
            return
        tree = self._detail_stop_tree
        desired_roots = []
        if timeline is not None and timeline.upcoming:
            destination = next(
                (
                    entry.name
                    for entry in reversed(timeline.upcoming)
                    if not entry.is_closure
                ),
                "Ziel",
            )
            upcoming_count = sum(not entry.is_closure for entry in timeline.upcoming)
            self._sync_detail_group(
                "upcoming",
                f"Kommende Halte bis {destination} ({upcoming_count})",
                timeline.upcoming,
                len(desired_roots),
            )
            desired_roots.append("upcoming")

        if timeline is None:
            current = StopTimelineEntry(
                "Haltestellen aktuell nicht verfügbar.",
                None,
            )
            current_tag = "unavailable"
        else:
            current = timeline.current
            current_tag = "current"
        self._upsert_detail_tree_item(
            "current",
            "",
            len(desired_roots),
            current.name,
            (
                self._format_time(current.arrival) if current.arrival else "",
                self._format_time(current.departure) if current.departure else "",
            ),
            current_tag,
        )
        desired_roots.append("current")

        if timeline is not None and timeline.past:
            past_count = sum(not entry.is_closure for entry in timeline.past)
            self._sync_detail_group(
                "past",
                f"Bereits angefahren ({past_count})",
                timeline.past,
                len(desired_roots),
            )
            desired_roots.append("past")

        for item_id in tree.get_children(""):
            if item_id not in desired_roots:
                tree.delete(item_id)
        for index, item_id in enumerate(desired_roots):
            tree.move(item_id, "", index)

    def _refresh_detail_closure_banner(self, text: str | None):
        label = self._detail_closure_label
        if text is None:
            label.pack_forget()
            return
        label.configure(text=text)
        if not label.winfo_manager():
            label.pack(
                fill="x",
                before=self._detail_section_label,
                pady=(0, 4),
            )

    @staticmethod
    def _format_time(value: datetime) -> str:
        return value.astimezone().strftime("%H:%M")

    @staticmethod
    def _format_delay(value: timedelta) -> str:
        seconds = max(0.0, value.total_seconds())
        if seconds == 0:
            return "Pünktlich"
        minutes = max(1, round(seconds / 60))
        return f"+{minutes} min"

    def _refresh_detail(self):
        if self.screen != "detail" or self.route is None:
            return
        if self._detail_connection_id is not None:
            connection = next(
                (
                    item
                    for item in self.route.connections
                    if item.id == self._detail_connection_id
                ),
                None,
            )
            if connection is None:
                for label in self._detail_labels.values():
                    label.configure(text="Verbindung aktuell nicht verfügbar.")
                self._refresh_detail_stop_table(None)
                self._refresh_detail_closure_banner(None)
                return
            destination = _station_name(
                self.route, connection.destination_station_id
            )
            timeline = connection_stop_timeline(
                self.route,
                connection,
                datetime.now(timezone.utc),
            )
            self._detail_labels["times"].configure(
                text=(
                    f"Abfahrt {self._format_time(connection.departure)}"
                    f" · Ankunft {self._format_time(connection.arrival)}"
                )
            )
            delay = timedelta(seconds=connection.delay_seconds)
            self._detail_labels["delay"].configure(
                text=f"Verspätung: {self._format_delay(delay)}",
                foreground="#b33b2e" if delay else "#267246",
            )
            self._detail_labels["direction"].configure(
                text=f"Fahrtrichtung: {destination}"
            )
            if timeline is None:
                self._detail_labels["current"].configure(
                    text="Aktueller Halt: aktuell nicht verfügbar."
                )
                self._detail_labels["next"].configure(
                    text=f"Nächstes Ziel: {destination}"
                )
            elif timeline.current.is_closure:
                self._detail_labels["current"].configure(
                    text=f"Aktuelle Position: {timeline.current_position}"
                )
                self._detail_labels["next"].configure(
                    text=f"Nächstes Ziel: {timeline.next_destination}"
                )
            else:
                current_label = (
                    "Zuletzt erreichter Halt"
                    if timeline.current_position.startswith("Zwischen ")
                    else "Aktueller Halt"
                )
                self._detail_labels["current"].configure(
                    text=f"{current_label}: {timeline.current.name}"
                )
                self._detail_labels["next"].configure(
                    text=f"Nächstes Ziel: {timeline.next_destination}"
                )
            self._refresh_detail_closure_banner(
                connection_closure_info(self.route, connection)
            )
            self._refresh_detail_stop_table(timeline)
            return

        train = next(
            (
                item
                for item in self.route.trains
                if item.trip.id == self._detail_train_id
            ),
            None,
        )
        if train is None:
            for label in self._detail_labels.values():
                label.configure(text="Bahn aktuell nicht verfügbar.")
            self._refresh_detail_stop_table(None)
            self._refresh_detail_closure_banner(None)
            return
        info = train_info(self.route, train)
        timeline = train_stop_timeline(self.route, train)
        self._detail_labels["times"].configure(
            text=(
                f"Abfahrt {self._format_time(info.departure)}"
                f" · Ankunft {self._format_time(info.arrival)}"
            )
        )
        self._detail_labels["delay"].configure(
            text=f"Verspätung: {self._format_delay(info.current_delay)}",
            foreground="#b33b2e" if info.current_delay else "#267246",
        )
        self._detail_labels["direction"].configure(
            text=f"Fahrtrichtung: {info.direction_destination}"
        )
        current_label = (
            "Aktueller Halt" if train.at_station else "Zuletzt erreichter Halt"
        )
        self._detail_labels["current"].configure(
            text=f"{current_label}: {timeline.current.name}"
        )
        self._detail_labels["next"].configure(
            text=f"Nächstes Ziel: {timeline.next_destination}"
        )
        self._refresh_detail_closure_banner(None)
        self._refresh_detail_stop_table(timeline)

    def go_back(self):
        if self.screen == "detail" and self.route is not None:
            self.controller.select_train(None)
            self.show_trains(self.route.id)
        elif self.screen == "closure":
            self.show_routes()
        elif self.screen == "trains":
            self.show_routes()

    def refresh(self):
        if self.screen == "trains":
            self._refresh_train_rows()
        elif self.screen == "detail":
            self._refresh_detail()
        try:
            self.root.after(1000, self.refresh)
        except self.tk.TclError:
            pass

    def close(self):
        self.controller.select_route(None)
        self.controller.select_train(None)
        self.controller.stop()
        self.root.destroy()

    def show_controller_error(self, error: Exception):
        self.messagebox.showerror("LED-Steuerung fehlgeschlagen", str(error))
        self.close()


def run_ui(routes: list[Route], controller: Controller, closure_store=None):
    import tkinter as tk

    root = tk.Tk()
    app = TramUI(root, routes, controller, closure_store)
    errors = Queue()

    def run_controller():
        try:
            controller.start()
        except Exception as exc:
            errors.put(exc)

    worker = Thread(target=run_controller, name="led-controller", daemon=True)
    worker.start()

    def report_controller_error():
        try:
            error = errors.get_nowait()
        except Empty:
            if root.winfo_exists():
                root.after(250, report_controller_error)
        else:
            app.show_controller_error(error)

    root.after(250, report_controller_error)
    try:
        root.mainloop()
    finally:
        controller.stop()
        worker.join(timeout=2)
