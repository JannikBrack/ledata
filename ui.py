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
    return TrainInfo(
        train_id=train.trip.id,
        origin=_station_name(route, stops[0].station_id),
        destination=_station_name(route, stops[-1].station_id),
        departure=train.trip.departure_at(0) + offset,
        arrival=train.trip.arrival_at(len(stops) - 1) + offset,
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


class TramUI:
    def __init__(self, root, routes: list[Route], controller: Controller):
        import tkinter as tk
        from tkinter import messagebox, ttk

        self.tk = tk
        self.ttk = ttk
        self.messagebox = messagebox
        self.root = root
        self.routes = routes
        self.controller = controller
        self.route: Route | None = None
        self.screen = "routes"
        self.direction_id: int | None = None
        self._row_trains: dict[str, Train] = {}
        self._detail_train_id: str | int | None = None
        self._detail_labels = {}

        self.root.title("Straßenbahn-Anzeige")
        self.root.attributes("-fullscreen", True)
        self.root.configure(background="#f3f5f7")
        self.root.bind("<Escape>", lambda _event: self.go_back())
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.show_routes()
        self.root.after(1000, self.refresh)

    def _clear(self):
        for child in self.root.winfo_children():
            child.destroy()

    def _header(self, title: str, back_label: str | None = None):
        tk = self.tk
        header = tk.Frame(self.root, background="#f3f5f7", padx=24, pady=18)
        header.pack(fill="x")
        if back_label:
            tk.Button(
                header,
                text=back_label,
                command=self.go_back,
                font=("TkDefaultFont", 16),
                padx=18,
                pady=10,
            ).pack(side="left", padx=(0, 20))
        tk.Label(
            header,
            text=title,
            background="#f3f5f7",
            font=("TkDefaultFont", 24, "bold"),
            anchor="w",
        ).pack(side="left", fill="x", expand=True)
        tk.Button(
            header,
            text="Beenden",
            command=self.close,
            font=("TkDefaultFont", 14),
            padx=14,
            pady=8,
        ).pack(side="right")

    def show_routes(self):
        self.controller.select_train(None)
        self.route = None
        self.screen = "routes"
        self._clear()
        self._header("Linie auswählen")

        tk = self.tk
        body = tk.Frame(self.root, background="#f3f5f7", padx=24, pady=12)
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
            tk.Button(
                body,
                text=route.name,
                command=lambda route_id=route.id: self.show_trains(route_id),
                background=self._color(route.color),
                foreground="white",
                activebackground=self._color(route.color),
                activeforeground="white",
                font=("TkDefaultFont", 22, "bold"),
                padx=24,
                pady=18,
            ).grid(row=index // 2, column=index % 2, sticky="nsew", padx=8, pady=8)
        for column in range(2):
            body.grid_columnconfigure(column, weight=1)
        for row in range((len(self.routes) + 1) // 2):
            body.grid_rowconfigure(row, weight=1)

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
        controls = tk.Frame(self.root, background="#f3f5f7", padx=24, pady=4)
        controls.pack(fill="x")
        tk.Label(
            controls,
            text="Richtung:",
            background="#f3f5f7",
            font=("TkDefaultFont", 16),
        ).pack(side="left", padx=(0, 12))

        endpoints = self.route.stations
        options = {"Alle Richtungen": None}
        if endpoints:
            options[f"Nach {_station_name(self.route, endpoints[0].id)}"] = endpoints[0].id
            options[f"Nach {_station_name(self.route, endpoints[-1].id)}"] = endpoints[-1].id
        self._filter_options = options
        self._filter_var = tk.StringVar(value="Alle Richtungen")
        chooser = ttk.Combobox(
            controls,
            textvariable=self._filter_var,
            values=list(options),
            state="readonly",
            font=("TkDefaultFont", 15),
            width=28,
        )
        chooser.pack(side="left", pady=4)
        chooser.bind("<<ComboboxSelected>>", self._filter_changed)

        table_frame = tk.Frame(self.root, padx=24, pady=12)
        table_frame.pack(fill="both", expand=True)
        columns = ("journey", "departure", "arrival")
        self._tree = ttk.Treeview(
            table_frame,
            columns=columns,
            show="headings",
            selectmode="browse",
        )
        self._tree.heading("journey", text="Herkunft → Ziel")
        self._tree.heading("departure", text="Abfahrt")
        self._tree.heading("arrival", text="Ankunft")
        self._tree.column("journey", width=560, anchor="w")
        self._tree.column("departure", width=150, anchor="center")
        self._tree.column("arrival", width=150, anchor="center")
        ttk.Style().configure("Treeview", rowheight=44, font=("TkDefaultFont", 15))
        ttk.Style().configure("Treeview.Heading", font=("TkDefaultFont", 14, "bold"))
        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=scrollbar.set)
        self._tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self._tree.bind("<<TreeviewSelect>>", self._train_selected)
        self._empty_label = tk.Label(
            self.root,
            text="Es sind aktuell keine Bahnen verfügbar.",
            background="#f3f5f7",
            font=("TkDefaultFont", 16),
        )
        self._empty_label.pack(anchor="w", padx=24, pady=(0, 16))
        self._row_trains = {}
        self._refresh_train_rows()

    def _filter_changed(self, _event=None):
        self.direction_id = self._filter_options[self._filter_var.get()]
        self._refresh_train_rows()

    def _refresh_train_rows(self):
        if self.screen != "trains" or self.route is None:
            return
        trains = filter_trains(
            self.route,
            self.route.trains,
            self.direction_id,
        )
        visible_ids = set()
        row_trains = {}
        for train in trains:
            row_id = str(train.trip.id)
            info = train_info(self.route, train)
            values = (
                f"{info.origin} → {info.destination}",
                self._format_time(info.departure),
                self._format_time(info.arrival),
            )
            if self._tree.exists(row_id):
                self._tree.item(row_id, values=values)
            else:
                self._tree.insert("", "end", iid=row_id, values=values)
            visible_ids.add(row_id)
            row_trains[row_id] = train
        for row_id in self._tree.get_children():
            if row_id not in visible_ids:
                self._tree.delete(row_id)
        self._row_trains = row_trains
        self._empty_label.configure(
            text="Es sind aktuell keine Bahnen in dieser Richtung verfügbar."
            if self.direction_id is not None
            else "Es sind aktuell keine Bahnen verfügbar."
        )
        if trains:
            self._empty_label.pack_forget()
        else:
            self._empty_label.pack(anchor="w", padx=24, pady=(0, 16))

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
        content = self.tk.Frame(self.root, background="#f3f5f7", padx=32, pady=24)
        content.pack(fill="both", expand=True)
        self._detail_labels = {}
        for key in ("journey", "times", "position", "direction"):
            label = self.tk.Label(
                content,
                background="#f3f5f7",
                font=("TkDefaultFont", 22 if key == "position" else 19),
                anchor="w",
                justify="left",
                wraplength=1000,
            )
            label.pack(fill="x", pady=12)
            self._detail_labels[key] = label
        self._refresh_detail()

    @staticmethod
    def _format_time(value: datetime) -> str:
        return value.astimezone().strftime("%H:%M")

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
        self._detail_labels["position"].configure(text=f"Position: {info.position}")
        self._detail_labels["direction"].configure(
            text=f"Fahrtrichtung: {info.direction_destination}"
        )

    def go_back(self):
        if self.screen == "detail" and self.route is not None:
            self.controller.select_train(None)
            self.show_trains(self.route.id)
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


def run_ui(routes: list[Route], controller: Controller):
    import tkinter as tk

    root = tk.Tk()
    app = TramUI(root, routes, controller)
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
