# ledata

## Bedienoberfläche auf dem Raspberry Pi

Auf einem Raspberry Pi, auf dem `rpi_ws281x` verfügbar ist, startet `main.py`
standardmäßig eine native Touchscreen-Oberfläche im Vollbild. Dafür muss eine
grafische Desktop-Sitzung laufen. Falls Tkinter auf dem System fehlt, kann es
unter Raspberry Pi OS mit `sudo apt install python3-tk` installiert werden.

Die Linienauswahl wird aus `meta.json` aufgebaut. Nach der Linienwahl zeigt die
Bahnauswahl die Fahrten mit Herkunft, Ziel sowie Abfahrts- und Ankunftszeit.
Große Schaltflächen erleichtern die Bedienung auf kleinen Touchscreens; über
die Richtungsschaltflächen lässt sich nach der aktuellen Endhaltestelle filtern.
Im Live-Modus (`--source live`) kann über „Baustelle eintragen“ pro Linie ein
gesperrter Abschnitt mit Von- und Bis-Haltestelle festgelegt werden; alle
Streckenabschnitte dazwischen gelten als gesperrt.
Die Fahrplan-Simulation (`--source fahrplan`) zeigt keine Baustellensteuerung.
Die Linienauswahl markiert die betroffene Linie mit einem Warnsymbol. In der
Fahrtübersicht enden die Live-Fahrten an den beiden Sperrhaltestellen; die
Richtungsfilter folgen diesen neuen Zielen und zeigen den Fußweg zur
Haltestelle auf der anderen Seite der Baustelle an. Der gesperrte
Streckenabschnitt wird auf dem LED-Streifen orange markiert.

Die Baustelleneinstellung wird lokal in `baustellen.json` gespeichert. Beim
nächsten Live-Start fragt die Anwendung, ob die gespeicherte Baustelle noch
besteht. In der UI wird sie mit „Ja“ übernommen und mit „Nein“ entfernt;
im Terminal wird entsprechend `j` oder `n` eingegeben. Die Datei enthält
Laufzeitstatus und wird deshalb nicht von Git erfasst.
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