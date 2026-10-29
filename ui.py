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
        self.is_portrait = root.winfo_screenheight() > root.winfo_screenwidth()
        self.route: Route | None = None
        self.screen = "routes"
        self.direction_id: int | None = None
        self._row_trains: dict[str, Train] = {}
        self._filter_buttons = {}
        self._train_cards = {}
        self._train_card_order: list[str] = []
        self._train_cards_frame = None
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
        header = tk.Frame(
            self.root,
            background="#f3f5f7",
            padx=8 if self.is_portrait else 12,
            pady=6 if self.is_portrait else 8,
        )
        header.pack(fill="x")
        if back_label:
            tk.Button(
                header,
                text=back_label,
                command=self.go_back,
                font=("TkDefaultFont", 13 if self.is_portrait else 15, "bold"),
                padx=10 if self.is_portrait else 14,
                pady=9 if self.is_portrait else 11,
            ).pack(side="left", padx=(0, 8 if self.is_portrait else 12))
        tk.Label(
            header,
            text=title,
            background="#f3f5f7",
            font=("TkDefaultFont", 17 if self.is_portrait else 20, "bold"),
            anchor="w",
        ).pack(side="left", fill="x", expand=True)
        tk.Button(
            header,
            text="Beenden",
            command=self.close,
            font=("TkDefaultFont", 12 if self.is_portrait else 14, "bold"),
            padx=9 if self.is_portrait else 12,
            pady=9 if self.is_portrait else 11,
        ).pack(side="right")

    def show_routes(self):
        self.controller.select_train(None)
        self.route = None
        self.screen = "routes"
        self._clear()
        self._header("Linie auswählen")

        tk = self.tk
        body = tk.Frame(
            self.root,
            background="#f3f5f7",
            padx=8 if self.is_portrait else 12,
            pady=6,
        )
        body.pack(fill="both", expand=True)
        if not self.routes:
            tk.Label(
                body,
                text="In meta.json sind keine Linien konfiguriert.",
                background="#f3f5f7",
                font=("TkDefaultFont", 18),
            ).pack(anchor="w", pady=12)
            return

        column_count = 1 if self.is_portrait else 2
        for index, route in enumerate(self.routes):
            tk.Button(
                body,
                text=route.name,
                command=lambda route_id=route.id: self.show_trains(route_id),
                background=self._color(route.color),
                foreground="white",
                activebackground=self._color(route.color),
                activeforeground="white",
                font=("TkDefaultFont", 18 if self.is_portrait else 20, "bold"),
                padx=16,
                pady=14 if self.is_portrait else 16,
                wraplength=390 if self.is_portrait else 320,
            ).grid(
                row=index // column_count,
                column=index % column_count,
                sticky="nsew",
                padx=6,
                pady=6,
            )
        for column in range(column_count):
            body.grid_columnconfigure(column, weight=1)
        for row in range((len(self.routes) + column_count - 1) // column_count):
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
        controls = tk.Frame(
            self.root,
            background="#f3f5f7",
            padx=6 if self.is_portrait else 10,
            pady=2,
        )
        controls.pack(fill="x")

        endpoints = self.route.stations
        options = {"Alle Richtungen": None}
        if endpoints:
            options[f"Nach {_station_name(self.route, endpoints[0].id)}"] = endpoints[0].id
            options[f"Nach {_station_name(self.route, endpoints[-1].id)}"] = endpoints[-1].id
        self._filter_buttons = {}
        for label, direction_id in options.items():
            button = tk.Button(
                controls,
                text=label,
                command=lambda selected_id=direction_id: self._select_direction(selected_id),
                font=("TkDefaultFont", 11 if self.is_portrait else 13, "bold"),
                padx=6,
                pady=8 if self.is_portrait else 9,
                wraplength=130 if self.is_portrait else 230,
                relief="raised",
                bd=2,
            )
            button.pack(side="left", fill="both", expand=True, padx=4, pady=3)
            self._filter_buttons[direction_id] = button
        self._update_filter_buttons()

        table_frame = tk.Frame(
            self.root,
            padx=6 if self.is_portrait else 10,
            pady=6,
        )
        table_frame.pack(fill="both", expand=True)
        self._tree = None
        self._train_canvas = None
        self._train_cards_frame = None
        self._train_cards = {}
        self._train_card_order = []
        if self.is_portrait:
            self._build_train_cards(table_frame)
        else:
            self._build_train_table(table_frame, ttk)

        self._empty_label = tk.Label(
            self.root,
            text="Es sind aktuell keine Bahnen verfügbar.",
            background="#f3f5f7",
            font=("TkDefaultFont", 12 if self.is_portrait else 14),
        )
        self._empty_label.pack(
            anchor="w",
            padx=8 if self.is_portrait else 12,
            pady=(0, 8),
        )
        self._row_trains = {}
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
        self._tree.column("journey", width=310, anchor="w", stretch=True)
        self._tree.column("delay", width=95, anchor="center", stretch=False)
        self._tree.column("departure", width=95, anchor="center", stretch=False)
        self._tree.column("arrival", width=95, anchor="center", stretch=False)
        self._tree.column("action", width=160, anchor="center", stretch=False)
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

    def _build_train_cards(self, parent):
        canvas = self.tk.Canvas(parent, background="#f3f5f7", highlightthickness=0)
        scrollbar = self.tk.Scrollbar(
            parent,
            orient="vertical",
            command=canvas.yview,
            width=24,
        )
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        cards = self.tk.Frame(canvas, background="#f3f5f7")
        window_id = canvas.create_window((0, 0), window=cards, anchor="nw")
        cards.bind(
            "<Configure>",
            lambda _event: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.bind(
            "<Configure>",
            lambda event: canvas.itemconfigure(window_id, width=event.width),
        )
        self._train_canvas = canvas
        self._train_cards_frame = cards

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
        if self.is_portrait:
            self._refresh_train_cards(trains)
        else:
            self._refresh_train_table(trains)

        self._empty_label.configure(
            text="Es sind aktuell keine Bahnen in dieser Richtung verfügbar."
            if self.direction_id is not None
            else "Es sind aktuell keine Bahnen verfügbar."
        )
        if trains:
            self._empty_label.pack_forget()
        else:
            self._empty_label.pack(
                anchor="w",
                padx=8 if self.is_portrait else 12,
                pady=(0, 8),
            )

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

    def _refresh_train_cards(self, trains: list[Train]):
        if self._train_cards_frame is None:
            return
        order = []
        for index, train in enumerate(trains):
            row_id = str(train.trip.id)
            info = train_info(self.route, train)
            text = (
                f"{info.origin} → {info.destination}\n"
                f"Verspätung: {self._format_delay(info.current_delay)}\n"
                f"Abfahrt {self._format_time(info.departure)}"
                f" · Ankunft {self._format_time(info.arrival)}\n"
                "Tippen für Details →"
            )
            card = self._train_cards.get(row_id)
            if card is None:
                card = self.tk.Button(
                    self._train_cards_frame,
                    command=lambda train_id=train.trip.id: self.show_train_detail(train_id),
                    anchor="w",
                    justify="left",
                    font=("TkDefaultFont", 13, "bold"),
                    padx=12,
                    pady=8,
                    wraplength=410,
                    height=4,
                    relief="raised",
                    bd=2,
                    cursor="hand2",
                )
                self._train_cards[row_id] = card
            card.configure(
                text=text,
                background="#ffffff" if index % 2 == 0 else "#eaf1f6",
                foreground="#263238",
                activebackground="#dceaf2",
                activeforeground="#17212b",
            )
            order.append(row_id)

        for row_id in tuple(self._train_cards):
            if row_id not in order:
                self._train_cards.pop(row_id).destroy()
        if order != self._train_card_order:
            for card in self._train_cards.values():
                card.pack_forget()
            for row_id in order:
                self._train_cards[row_id].pack(fill="x", padx=4, pady=4)
            self._train_card_order = order

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
        content = self.tk.Frame(
            self.root,
            background="#f3f5f7",
            padx=12 if self.is_portrait else 18,
            pady=8 if self.is_portrait else 12,
        )
        content.pack(fill="both", expand=True)
        self._detail_labels = {}
        for key in ("journey", "times", "delay", "position", "direction"):
            label = self.tk.Label(
                content,
                background="#f3f5f7",
                font=(
                    "TkDefaultFont",
                    (18 if key in ("delay", "position") else 15)
                    if self.is_portrait
                    else (20 if key in ("delay", "position") else 17),
                ),
                anchor="w",
                justify="left",
                wraplength=440 if self.is_portrait else 740,
            )
            label.pack(fill="x", pady=6 if self.is_portrait else 8)
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
