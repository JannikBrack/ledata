# WS2812B LED-Schiene

Die Modelle sind für einen 10 mm breiten und bis zu 5 mm hohen WS2812B-Streifen ausgelegt. Die Schiene hat einen 12 mm breiten LED-Kanal, seitliche Nuten für das längs einschiebbare Dach und lösbare Hakenverbinder an den Segmentenden.

## Druckdateien

- `ws2812b_rail_200mm.stl`: Schienensegment mit 200 mm Körperlänge
- `ws2812b_rail_100mm.stl`: kurzes Schienensegment mit 100 mm Körperlänge
- `ws2812b_roof_200mm.stl` und `ws2812b_roof_100mm.stl`: passende Dächer mit je 2 mm Spiel an beiden Enden
- `ws2812b_90deg_elbow.scad`: parametrisierbares 90°-Eckstück mit passender Schiene, Aufdrückdeckel und Verbindern
- `ws2812b_90deg_elbow_rail.stl`: 90°-Eckschiene
- `ws2812b_90deg_elbow_cap.stl`: von oben aufdrückbarer Deckel für das Eckstück

Die vorhandenen STL-Dateien liegen flach und sind für das 256 × 256 × 256 mm große Druckvolumen der Bambu-Lab-P1-Reihe ausgelegt. Die `.scad`-Dateien sind die parametrisierbaren Quelldateien; für andere Längen `segment_length` beziehungsweise `rail_length` anpassen und neu exportieren.

Der Verbinder ist auf `print_clearance = 0.25` mm ausgelegt. Für die federnden Haken ist PETG empfehlenswert. Vor dem Druck mehrerer Segmente zuerst ein kurzes Testsegment drucken und die Passung prüfen.

## 90°-Eckstück

`ws2812b_90deg_elbow.scad` übernimmt die Außenmaße und Verbinder der geraden Schiene. Standardmäßig sind 50 mm Einlauf, ein 30-mm-Mittellinienradius und ein 90°-Bogen eingestellt. Die Länge der Auslaufgeraden wird so berechnet, dass der Endpunkt der Mittellinie genau 100 mm Luftlinienabstand zum Anfang hat; mit den Standardwerten sind das 30 mm. Die Verbinder sind in diesem Abstand nicht mitgerechnet. Der 12-mm-LED-Kanal ist auf Wunsch vollständig aufgefüllt (`fill_led_channel = true`), daher passt dort kein LED-Streifen mehr hinein. Da sich das gerade Schiebedach nicht durch einen 90°-Bogen einschieben lässt, hat das Eckstück stattdessen einen eigenen, von oben aufdrückbaren Deckel mit seitlichen Rastnasen.

Die beiden STL-Dateien sind aus der Quelldatei exportiert. Für angepasste Maße in OpenSCAD `part` auf `"rail"`, `"cap"` oder `"assembly"` setzen und Schiene und Deckel separat exportieren. Der Deckel wird mit der Innenseite nach oben gedruckt und anschließend von oben auf die Schiene gedrückt; die Passung der Rastnasen sollte vor dem endgültigen Druck geprüft werden. Die Kurve ist in 64 Abschnitte unterteilt und kann über `bend_steps` weiter verfeinert werden.
