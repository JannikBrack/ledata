"""Persistence for temporary closed route sections."""

from __future__ import annotations

import json
import os
from pathlib import Path
from threading import Lock


class ClosureStore:
    def __init__(self, path: str | Path, route_station_ids: dict[int, list[int]]):
        self.path = Path(path)
        self.route_station_ids = route_station_ids
        self._closures: dict[int, tuple[int, int]] = {}
        self._lock = Lock()

    def load(self) -> dict[int, tuple[int, int]]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            with self._lock:
                self._closures = {}
            return {}
        except json.JSONDecodeError as exc:
            raise ValueError(f"Ungültige Baustellendatei {self.path}: {exc}") from exc

        if not isinstance(data, dict) or not isinstance(data.get("closures"), dict):
            raise ValueError(
                f"Ungültiges Format in {self.path}; erwartet wird ein "
                "'closures'-Objekt."
            )

        closures = {}
        for route_key, station_ids in data["closures"].items():
            try:
                route_id = int(route_key)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"Ungültige Linien-ID in {self.path}: {route_key}") from exc
            closure = self._parse_station_ids(route_id, station_ids)
            if route_id in self.route_station_ids:
                self._validate(route_id, closure)
            closures[route_id] = closure

        with self._lock:
            self._closures = closures
            return dict(self._closures)

    def get(self, route_id: int) -> tuple[int, int] | None:
        with self._lock:
            return self._closures.get(route_id)

    def snapshot(self) -> dict[int, tuple[int, int]]:
        with self._lock:
            return dict(self._closures)

    def set(self, route_id: int, station_ids: tuple[int, int] | None) -> None:
        with self._lock:
            previous = dict(self._closures)
            if station_ids is None:
                self._closures.pop(route_id, None)
            else:
                closure = self._parse_station_ids(route_id, station_ids)
                self._validate(route_id, closure)
                self._closures[route_id] = closure

            data = {
                "closures": {
                    str(key): list(value)
                    for key, value in sorted(self._closures.items())
                }
            }
            temporary_path = self.path.with_name(self.path.name + ".tmp")
            try:
                temporary_path.write_text(
                    json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                os.replace(temporary_path, self.path)
            except OSError:
                self._closures = previous
                try:
                    temporary_path.unlink()
                except FileNotFoundError:
                    pass
                raise

    @staticmethod
    def _parse_station_ids(route_id, station_ids) -> tuple[int, int]:
        if (
            not isinstance(station_ids, (list, tuple))
            or len(station_ids) != 2
            or any(type(station_id) is not int for station_id in station_ids)
        ):
            raise ValueError(
                f"Baustelle für Linie {route_id} muss genau zwei Stations-IDs enthalten."
            )
        return station_ids[0], station_ids[1]

    def _validate(self, route_id: int, closure: tuple[int, int]) -> None:
        station_ids = self.route_station_ids.get(route_id)
        if station_ids is None:
            raise ValueError(f"Unbekannte Linie für Baustelle: {route_id}")
        try:
            first_index = station_ids.index(closure[0])
            second_index = station_ids.index(closure[1])
        except ValueError as exc:
            raise ValueError(
                f"Baustellen-Haltestelle gehört nicht zu Linie {route_id}."
            ) from exc
        if first_index == second_index:
            raise ValueError(
                f"Die Von- und Bis-Haltestelle auf Linie {route_id} "
                "müssen verschieden sein."
            )
