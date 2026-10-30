# WS2812B LED-Schiene

Die Modelle sind für einen 10 mm breiten und bis zu 5 mm hohen WS2812B-Streifen ausgelegt. Die Schiene hat einen 12 mm breiten LED-Kanal, seitliche Nuten für das längs einschiebbare Dach und lösbare Hakenverbinder an den Segmentenden.

## Druckdateien

- `ws2812b_rail_200mm.stl`: Schienensegment mit 200 mm Körperlänge
- `ws2812b_rail_100mm.stl`: kurzes Schienensegment mit 100 mm Körperlänge
- `ws2812b_roof_200mm.stl` und `ws2812b_roof_100mm.stl`: passende Dächer mit je 2 mm Spiel an beiden Enden

Die STL-Dateien liegen flach und sind für das 256 × 256 × 256 mm große Druckvolumen der Bambu-Lab-P1-Reihe ausgelegt. Die beiden `.scad`-Dateien sind die parametrisierbaren Quelldateien; für andere Längen `segment_length` beziehungsweise `rail_length` anpassen und neu exportieren.

Der Verbinder ist auf `print_clearance = 0.25` mm ausgelegt. Für die federnden Haken ist PETG empfehlenswert. Vor dem Druck mehrerer Segmente zuerst ein kurzes Testsegment drucken und die Passung prüfen.
