# Projektdokumentation

## LEData

**Tabelle 1: Beteiligung am Gesamtprojekt**

| Beteiligte Person | Beteiligung am Gesamtprojekt |
|---|---:|
| Lena Hackenjos | 25 % |
| Valentino Schreiner | 25 % |
| Raffael Langklotz | 25 % |
| Jannik Brack | 25 % |
| **Gesamt** | **100 %** |

<div style="page-break-after: always;"></div>

## Inhaltsverzeichnis

<mark> kommt noch </mark>

## 1 Projektauftrag
<mark> kommt noch </mark>

## 2 Teamsitzungsprotokolle

<mark> kommt noch </mark>

## 3 Organisatorischer Teil

### 3.1 Aufbauorganisation

Die Zuständigkeiten innerhalb des Teams werden den folgenden Arbeitsbereichen noch zugeordnet.

**Tabelle 4: Aufbauorganisation und Zuständigkeiten**

| Arbeitsbereich | Zuständige Person(en) |
|---|---|
| API | [wird ergänzt] |
| Verarbeitungslogik | [wird ergänzt] |
| Hardware | [wird ergänzt] |
| Software | [wird ergänzt] |

<mark>Aus protokolle extrahieren</mark>

### 3.2 Projektstrukturplan
<mark>APs protokolle extrahieren</mark>

### 3.3 Zeitplanung
<mark>Gant diagramm wenn APs fertig sind  aus Projekt-Protokoll extrahieren</mark>

### 3.4 Projektkosten

<mark>Aus Antrag + Tatsächlicher wert mit preiskorrektur ist soll vergleich</mark>

## 4 Inhaltlicher Teil
<mark>Aus Aktuellem Code extrahieren</mark>

<mark>Technische EPK falls notwendig</mark>

Die technische Darstellung basiert auf dem aktuellen Repository-Stand, insbesondere auf `main.py`, `live_feed.py`, `classes.py`, `ui.py` und `meta.json`. Ein genauer Versions- und Datumsnachweis wird im Quellenverzeichnis ergänzt.

### 4.1 Systemübersicht

LEData visualisiert Live-Daten einer Straßenbahn in Freiburg auf einem LED-Streifen und einem Touchdisplay. Die Anwendung besteht aus einer Python-Software, einer Datenanbindung an den Live-Dienst und einer Anzeigesteuerung für Touchdisplay und LEDs.

### 4.2 Live-Datenquelle

Im Live-Modus fragt LEData den in der Konfiguration hinterlegten TRIAS-Dienst ab. Die Anfragen verwenden die den Haltestellen und Linien zugeordneten Referenzen. Angefordert werden Echtzeitdaten zu Abfahrten und zugehörigen Haltestelleninformationen.

### 4.3 Datenverarbeitung

<mark>Meta.json anhängen<mark>

Die Anwendung liest Linien-, Haltestellen- und LED-Zuordnungen aus `meta.json`. Die TRIAS-Antworten werden aus XML in Fahrten und Haltestellenaufrufe umgewandelt; dabei werden unter anderem geplante und prognostizierte Zeiten sowie Verspätungen übernommen. Anschließend werden die aktiven Fahrten der jeweiligen Route zugeordnet und an den Controller übergeben. Live-Daten werden standardmäßig alle 30 Sekunden aktualisiert. Richtungs- und Baustellenauswahl beeinflussen, welche Fahrten und Streckenabschnitte angezeigt werden.

Bei vollständig fehlgeschlagenen TRIAS-Abfragen wird der Fehler protokolliert. Die zuletzt verfügbaren Zugdaten bleiben erhalten, bis neue Daten erfolgreich verarbeitet werden.

### 4.4 Touchdisplay und Bedienung

<mark>Screenshot von Anwednung 3 darstellungen Linien auswahl bahn auswahl und selektierte bahn</mark>

Die Touchscreen-Oberfläche ist mit Tkinter umgesetzt und ermöglicht die Auswahl einer Linie sowie – abhängig von der Ansicht – einer Fahrt oder Fahrtrichtung. Sie zeigt Informationen zu Fahrt, Haltestellen, Ziel und Verspätung. Im Live-Modus kann die Linienauswahl eine dynamische Vorschau der aktiven Bahnen anzeigen.

### 4.5 Hardware und LED-Anzeige

Die LED-Anzeige bildet die Streckenabschnitte und Haltestellen räumlich ab. Aktive Bahnen werden in der Linienfarbe dargestellt; Haltestellenpositionen können weiß markiert werden. Ein gesperrter Streckenabschnitt wird gelb markiert. Für die Projektkonfiguration sind 300 LEDs an GPIO 18 mit 800 kHz Signalrate und einem Helligkeitswert von 100 hinterlegt. Die LED-Ansteuerung nutzt `rpi_ws281x`; für Tests ohne Raspberry-Pi-Hardware gibt es ein Software-Backend.

Im Repository sind außerdem 3D-Modelle für eine modulare Schiene mit WS2812B-LED-Streifen dokumentiert. Die konkreten verwendeten Bauteile und Materialmengen werden im Materialverzeichnis ergänzt.

## 5 Abschlussbericht

### 5.1 Kontrolle

**Tabelle 5: Soll-Ist-Kontrolle**

| Prüfkriterium/Ziel | Soll | Ist | Abweichung/Bewertung |
|---|---|---|---|
| Straßenbahnlinenen-Darstellung | Komplettes Straßenbahn netz von Freiburg abbilden | Netz wurde linear dargestellt Straßenbahnlinie muss dur bildschir gewechselt werden. | Die Umsetztung des Gesammten netzes ist nicht im ramen der Zeit und des Budgets |
| Straßenbahnenfilter funktion | der User soll nach Richtung und einzehlnen bahnen Filtern können | genau so wie beschrieben | Umsetzung hat geklappt |
| [Kriterium] | [Sollwert] | [Ergebnis] | [Bewertung] |
| [Kriterium] | [Sollwert] | [Ergebnis] | [Bewertung] |
| [Kriterium] | [Sollwert] | [Ergebnis] | [Bewertung] |
| [Kriterium] | [Sollwert] | [Ergebnis] | [Bewertung] |
| [Kriterium] | [Sollwert] | [Ergebnis] | [Bewertung] |
| [Kriterium] | [Sollwert] | [Ergebnis] | [Bewertung] |
| [Kriterium] | [Sollwert] | [Ergebnis] | [Bewertung] |
<mark> tabelle mit 5.2 ersetzten </mark>

### 5.2 Ergebnisse

- **Umgesetzte Ergebnisse:** [ergänzen]
- **Nicht oder teilweise umgesetzte Ziele:** [ergänzen]
- **Ergebnis der Präsentation/Erprobung:** [ergänzen]

<mark> auf protokoll ergänzen </mark>

### 5.3 Reflexion der Gruppenarbeit

- **Was lief in der Zusammenarbeit gut?** Keiner Wurde zurück gelassen. Wissens stände wurden durch gute Kommunikation bei allen auf gleichem level gehalten. Abstimmung alle waren sich einig. Aufgabenverteilung. Anwesenheiten. Selbst bei überschätzung des umfangs schnelle und einfachere alternativen gefunden ohne die idee des projekts zu beschädigen 
- **Welche Schwierigkeiten gab es?** Projektumfang überschätzt.
- **Wie wurden Aufgaben und Entscheidungen abgestimmt?** Gemeinschaftliche Ideenfindeung, arbeitsverteilung, planung. Raum für diskusionen war gegeben.
- **Was würden wir beim nächsten Projekt anders machen?** Genscheit planen sind zusammen eher halsüberkopf in die umsetzung gegangen

### 5.4 Resultat mit stand Aufbau

## 6 Quellenverzeichnis und KI-Prompts

Im Text werden Quellen einheitlich mit Kurzbelegen nach dem Muster **(Autor/Organisation, Jahr)** angegeben. Jede zitierte Quelle wird vollständig im Verzeichnis aufgeführt. Für Internetquellen werden zusätzlich die URL und das Abrufdatum angegeben.

### Literatur

**Muster:**<br>
Nachname, Vorname (Jahr): *Titel*. Verlag, Erscheinungsort.

- [Quelle nach dem Muster ergänzen]

### Internetquellen

**Muster:**<br>
Autor/Organisation (Jahr oder o. J.): *Titel der Seite/des Dokuments*. URL: [vollständige URL], abgerufen am [TT.MM.JJJJ].

- [Quelle nach dem Muster ergänzen]

### Interne Projektunterlagen

**Muster:**<br>
Projektteam LEData (Jahr): *Quellcode/Projektunterlage*, Dateiname oder Version, unveröffentlichte Projektunterlage.

- [verwendete interne Unterlage ergänzen]

### KI-Nutzung und verwendete Prompts

Für jede verwendete KI-Unterstützung werden Werkzeug/Modell, Datum und der vollständige Prompt dokumentiert. Zusätzlich wird festgehalten, welche Ausgabe übernommen oder wie sie überarbeitet wurde.

**Tabelle 6: Dokumentation der KI-Nutzung und verwendeter Prompts**

| KI-Werkzeug/Modell | Datum | Zweck | Vollständiger Prompt | Verwendete/überarbeitete Ausgabe |
|---|---|---|---|---|
| [eintragen] | [TT.MM.JJJJ] | [eintragen] | [vollständigen Prompt einfügen] | [eintragen] |

## 7 Abbildungsverzeichnis

**Tabelle 7: Abbildungsverzeichnis**

| Abbildung | Titel | Seite |
|---|---|---:|
| 1 | Technischer Live-Datenfluss von LEData | nach Export |

## 8 Materialverzeichnis

**Tabelle 8: Materialverzeichnis**

| Material/Komponente | Menge | Verwendung | Bezugsquelle |
|---|---:|---|---|
| [eintragen] | [eintragen] | [eintragen] | [Händler/URL/Bezugsweg] |

## Anhang A: Formatcheck für den Export

- DIN A4
- Seitenränder links und rechts jeweils 30 mm
- Schriftgröße 12 pt in einer gut lesbaren serifenlosen Proportionalschrift
- 1,5-facher Zeilenabstand
- Abbildungen und Tabellen fortlaufend nummerieren und beschriften
- Höchstens zehn Seiten reiner Inhalt; Deckblatt, Inhaltsverzeichnis, Abbildungs- und Quellenverzeichnis sowie Anhang zählen laut Vorgabe nicht dazu
- Inhaltsverzeichnis-Seitenzahlen nach dem Seitenlayout in Word/PDF aktualisieren
