"""Touchscreen UI for selecting routes and live trains on the LED board."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from queue import Empty, Queue
from threading import Thread

from classes import Controller, Route, Train


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


def _station_name(route: Route, station_id: int) -> str:
    return route.station_names.get(station_id, str(station_id))


def direction_destination_id(route: Route, train: Train) -> int:
    if not route.stations:
        raise ValueError(f"Route {route.id} has no stations")
    if not train.trip.cyclic:
        return train.trip.stops[-1].station_id
    return route.stations[-1].id if train.direction >= 0 else route.stations[0].id


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


def walking_instruction(
    route: Route,
    train: Train,
    closure: tuple[int, int] | None,
) -> str:
    if closure is None:
        return ""
    destination_id = train.trip.stops[-1].station_id
    other_terminal = next(
        (station_id for station_id in closure if station_id != destination_id),
        None,
    )
    if other_terminal is None:
        return ""
    return f"Zu Fuß bis {_station_name(route, other_terminal)}"


def route_direction_destination_ids(route: Route) -> tuple[int, int]:
    if route.closed_section is not None:
        return route.closed_section
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
        self._filter_buttons = {}
        self._detail_train_id: str | int | None = None
        self._detail_labels = {}

        self.root.title("Straßenbahn-Anzeige")
        self.root.attributes("-fullscreen", True)
        self.root.configure(background="#f3f5f7")
        self.root.bind("<Escape>", lambda _event: self.go_back())
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self._confirm_saved_closures()
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
        self.controller.select_train(None)
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
            tk.Button(
                card,
                text=f"⚠ {route.name}" if route.closed_section else route.name,
                command=lambda route_id=route.id: self.show_trains(route_id),
                background=self._color(route.color),
                foreground="white",
                activebackground=self._color(route.color),
                activeforeground="white",
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

    def _confirm_saved_closures(self):
        if self.closure_store is None:
            return
        for route in self.routes:
            closure = self.closure_store.get(route.id)
            if closure is None:
                continue
            start_name = _station_name(route, closure[0])
            end_name = _station_name(route, closure[1])
            keep = self.messagebox.askyesnocancel(
                "Baustelle bestätigen",
                (
                    f"Gibt es die Baustelle zwischen {start_name} und "
                    f"{end_name} auf {route.name} noch?"
                ),
                parent=self.root,
            )
            if keep is False:
                try:
                    self.closure_store.set(route.id, None)
                except OSError as exc:
                    self.messagebox.showerror(
                        "Baustelle nicht entfernt",
                        str(exc),
                        parent=self.root,
                    )
                    continue
                route.set_closed_section(None)

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
        self.controller.select_train(None)
        self.screen = "trains"
        self.direction_id = None
        self._clear()
        self._header(self.route.name, "Linien")

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
        self._refresh_train_rows()

    def _build_train_table(self, parent, ttk):
        columns = ("journey", "walk", "delay", "departure", "arrival", "action")
        self._tree = ttk.Treeview(
            parent,
            columns=columns,
            show="headings",
            selectmode="browse",
            style="Touch.Treeview",
            cursor="hand2",
        )
        self._tree.heading("journey", text="Herkunft → Ziel")
        self._tree.heading("walk", text="Fußweg bei Baustelle")
        self._tree.heading("delay", text="Verspätung")
        self._tree.heading("departure", text="Abfahrt")
        self._tree.heading("arrival", text="Ankunft")
        self._tree.heading("action", text="")
        self._tree.column("journey", width=270, anchor="w", stretch=False)
        self._tree.column("walk", width=220, anchor="w", stretch=False)
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
        walk_width = round(table_width * 0.28)
        remaining_width = table_width - journey_width - walk_width
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
        self._tree.column("walk", width=walk_width)
        self._tree.column("journey", width=journey_width)

    def _select_direction(self, direction_id: int | None):
        self.direction_id = direction_id
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
        trains = filter_trains(
            self.route,
            self.route.trains,
            self.direction_id,
        )
        self._refresh_train_table(trains)

        self._empty_label.configure(
            text="Es sind aktuell keine Bahnen in dieser Richtung verfügbar."
            if self.direction_id is not None
            else "Es sind aktuell keine Bahnen verfügbar."
        )
        if trains:
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
                walking_instruction(
                    self.route,
                    train,
                    self.route.closed_section,
                ),
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

    def _train_selected(self, _event=None):
        selection = self._tree.selection()
        if selection and selection[0] in self._row_trains:
            self.show_train_detail(self._row_trains[selection[0]].trip.id)

    def show_train_detail(self, train_id: str | int):
        if self.route is None:
            return
        self._detail_train_id = train_id
        self.controller.select_train(self.route.id, train_id)
        self.screen = "detail"
        self._clear()
        self._header(f"{self.route.name} · Bahn {train_id}", "Bahnauswahl")
        content = self.tk.Frame(self.root, background="#f3f5f7", padx=18, pady=12)
        content.pack(fill="both", expand=True)
        self._detail_labels = {}
        for key in ("journey", "times", "delay", "position", "direction"):
            label = self.tk.Label(
                content,
                background="#f3f5f7",
                font=("TkDefaultFont", 20 if key in ("delay", "position") else 17),
                anchor="w",
                justify="left",
                wraplength=740,
            )
            label.pack(fill="x", pady=8)
            self._detail_labels[key] = label
        self._refresh_detail()

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
        train = next(
            (item for item in self.route.trains if item.trip.id == self._detail_train_id),
            None,
        )
        if train is None:
            for label in self._detail_labels.values():
                label.configure(text="Bahn aktuell nicht verfügbar.")
            return
        info = train_info(self.route, train)
        self._detail_labels["journey"].configure(
            text=f"{info.origin} → {info.destination}"
        )
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
        self._detail_labels["position"].configure(text=f"Position: {info.position}")
        self._detail_labels["direction"].configure(
            text=f"Fahrtrichtung: {info.direction_destination}"
        )

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
