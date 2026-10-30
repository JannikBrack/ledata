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
Der LED-Streifen zeigt dann nur Bahnen dieser Richtung; Haltestellen und eine
etwaige Baustellenmarkierung bleiben sichtbar.
Konfiguriert sind die Linien 1 bis 4. Linie 3 folgt regulär der Strecke
Munzinger Straße → Gundelfinger Straße; die Haltestellenfolge der Rückrichtung
wird für Live-Fahrten ebenfalls berücksichtigt. Linie 4 ist mit der Grundrichtung
Messe Freiburg → Innsbrucker Straße konfiguriert; Europa-Park Stadion wird gemäß
VAG-Fahrplan in der Richtung Messe → Vauban berücksichtigt. Live-Fahrten beider
Richtungen nutzen die verifizierten TRIAS-Referenzen. Quellen: [VAG-Linienfahrplan
Linie 4](https://www.vag-freiburg.de/fileadmin/vag_freiburg_media/downloads/linienplaene/Linie_4_ab_19_10.pdf)
und [MobiData BW TRIAS](https://mobidata-bw.de/dataset/trias).
Im Live-Modus werden in der Touchscreen-Oberfläche nur Daten der ausgewählten
Linie abgefragt. Auf der Linienauswahlseite bleibt der LED-Streifen aus und es
werden keine Live-Abfragen ausgeführt. In der Linienübersicht leuchten alle
aktiven Bahnen der gewählten Linie; in der Detailansicht nur die ausgewählte
Bahn. Im Terminalbetrieb werden weiterhin Prozess- und Live-Daten protokolliert,
der LED-Streifen wird dort jedoch nicht angesteuert.
Im Live-Modus (`--source live`) kann über „Baustelle eintragen“ pro Linie ein
gesperrter Abschnitt mit Von- und Bis-Haltestelle festgelegt werden; alle
Streckenabschnitte dazwischen gelten als gesperrt.
Die Fahrplan-Simulation (`--source fahrplan`) zeigt keine Baustellensteuerung.
Die Linienauswahl und der Kopf des Bahnplans markieren die betroffene Linie mit
„⚠ Baustelle“ direkt neben dem Liniennamen. In der Fahrtübersicht gibt es kein
separates Warnsymbol; Fußwegtexte werden dort nicht angezeigt. Die regulären
Endstationen und Richtungsfilter bleiben erhalten.
Die beiden zugänglichen Teilfahrten werden zu einer Verbindung zwischen den
regulären Endstationen zusammengeführt, wenn der Anschluss nach mindestens
fünf Minuten Fußweg passt. Nicht passende Einzelteile erscheinen dort nicht
als vollständige Verbindung; die echten Teilfahrten bleiben auf den LEDs
getrennt sichtbar. Der gesperrte Streckenabschnitt wird auf dem LED-Streifen
gelb markiert; Linie 3 leuchtet orange.

Die Baustelleneinstellung wird lokal in `baustellen.json` gespeichert. Beim
nächsten Live-Start fragt die Anwendung im Terminal, ob die gespeicherte
Baustelle noch besteht. Mit `j` wird sie übernommen, mit `n` entfernt. Danach
startet die Touchscreen-UI im Vollbild. Der `--terminal`-Betrieb fragt nur die
Baustellen ab und protokolliert den Prozess. Die Datei enthält Laufzeitstatus
und wird deshalb nicht von Git erfasst.
Die Verspätung je Bahn wird in der Liste und Detailansicht angezeigt. Sie
bezieht sich auf den aktuellen beziehungsweise zuletzt erreichten Halt;
pünktliche Bahnen werden entsprechend markiert. Die höheren Listeneinträge
zeigen mit „Tippen: Details →“ ihre Auswahlfunktion.
Die Detailansicht zeigt Fahrtrichtung, Abfahrt, Ankunft, Verspätung, aktuellen
Halt und nächstes Ziel; eine separate Weiterfahrt-Zeit entfällt. Während sie
geöffnet ist, zeigt der LED-Streifen nur die ausgewählte Bahn. Zeiten werden in
der lokalen Zeitzone des Raspberry Pi angezeigt. In der Haltestellenliste
stehen kommende Halte oberhalb und vergangene Halte unterhalb des aktuellen,
grün markierten Halts. Kommende und vergangene Halte sind zunächst eingeklappt
und lassen sich antippen. Aufgeklappte Einträge zeigen Ankunfts- und
Abfahrtszeit. Beim Erreichen eines neuen Halts aktualisiert sich die Ansicht.
Bei einer Baustellen-Verbindung ist der Baustellenhinweis oberhalb der Liste
sichtbar und erscheint zusätzlich an seiner Stelle in der Haltefolge; während
des Fußwegs wird der Umstieg als aktuelle Position markiert.

Mit `--terminal` wird keine LED-Anzeige gestartet; der Prozess wird im Terminal
protokolliert und gespeicherte Baustellen werden abgefragt. Auf anderen Systemen
kann die grafische Oberfläche mit `--ui` explizit gestartet werden, sofern eine
Desktop-Anzeige vorhanden ist. `--dry-run` startet ohne LED-Hardware.

```bash
python3 main.py
python3 main.py --terminal --dry-run
python3 main.py --ui --source fahrplan
```