# ledata

## Bedienoberfläche auf dem Raspberry Pi

Auf einem Raspberry Pi, auf dem `rpi_ws281x` verfügbar ist, startet `main.py`
standardmäßig eine native Touchscreen-Oberfläche im Vollbild. Dafür muss eine
grafische Desktop-Sitzung laufen. Falls Tkinter auf dem System fehlt, kann es
unter Raspberry Pi OS mit `sudo apt install python3-tk` installiert werden.
Die Oberfläche erkennt Hoch- und Querformat automatisch. Die Display-Rotation
selbst wird in Raspberry Pi OS beziehungsweise in der Display-Konfiguration
eingestellt.

Die Linienauswahl wird aus `meta.json` aufgebaut. Nach der Linienwahl zeigt die
Bahnauswahl die Fahrten mit Herkunft, Ziel sowie Abfahrts- und Ankunftszeit.
Große Schaltflächen erleichtern die Bedienung auf kleinen Touchscreens; über
die Richtungsschaltflächen lässt sich nach der aktuellen Endhaltestelle filtern.
Die Verspätung je Bahn wird in der Liste und Detailansicht angezeigt. Sie
bezieht sich auf den aktuellen beziehungsweise zuletzt erreichten Halt;
pünktliche Bahnen werden entsprechend markiert. Die höheren Listeneinträge
zeigen mit „Tippen: Details →“ ihre Auswahlfunktion.
Die Detailansicht ergänzt die aktuelle Position; während sie geöffnet ist,
zeigt der LED-Streifen nur die ausgewählte Bahn. Zeiten werden in der lokalen
Zeitzone des Raspberry Pi angezeigt.

Mit `--terminal` bleibt der bisherige Terminalbetrieb verfügbar. Auf anderen
Systemen kann die grafische Oberfläche mit `--ui` explizit gestartet werden,
sofern eine Desktop-Anzeige vorhanden ist. `--dry-run` behält standardmäßig
den bisherigen Terminal-Simulationsmodus bei.

```bash
python3 main.py
python3 main.py --terminal --dry-run
python3 main.py --ui --source fahrplan
```