#!/usr/bin/env python3

import argparse
from rpi_ws281x import PixelStrip, Color

# LED strip configuration (same as led_control.py)
LED_COUNT = 300
LED_PIN = 18
LED_FREQ_HZ = 800000
LED_DMA = 10
LED_BRIGHTNESS = 100
LED_INVERT = False
LED_CHANNEL = 0


WHITE = (255, 255, 255)

# Vordefinierte Bereichslängen
linie_1 = [9, 7, 13, 5, 5, 8, 6, 14, 8, 8, 7, 7, 5, 3, 3, 4, 4, 4, 5, 4, 4, 1] # Linie 1 bei landwasser angefangen
linie_2 = [13, 4, 9, 4, 14, 9, 14, 8, 8, 7, 5, 5, 4, 4, 4, 4, 4, 3, 1] # Linie 2 Brühl anfang
linie_3 = [7, 9, 8, 5, 8, 10, 6, 14, 8, 8, 7, 7, 7, 9, 5, 8, 3, 3, 3, 2, 3, 1] # Linie 3 Munzinger Straße Anfang
linie_4 = [5, 5, 4, 5, 2, 9, 14, 8, 8, 7, 6, 5, 12, 13, 6, 5, 6, 7, 9, 1]   # Linie 4 Messe Anfang
linie_5 = [10, 6, 10, 7, 5, 4, 7, 6, 8, 12, 4, 5, 7, 7, 1] # Linie 5 Rieselfeld anfang
LINIEN = {
    '1': ('Linie 1 (Landwasser)', linie_1),
    '2': ('Linie 2 (Brühl)',      linie_2),
    '3': ('Linie 3 (Munzinger Straße)', linie_3),
    '4': ('Linie 4 (Messe)',      linie_4),
    '5': ('Linie 5 (Rieselfeld)', linie_5),
}


def clear_strip(strip):
    for i in range(strip.numPixels()):
        strip.setPixelColor(i, Color(0, 0, 0))
    strip.show()


def apply_segments(strip, counts):
    """Setzt alle Segmente auf den Strip: erste LED weiß, Rest Segmentfarbe."""
    pos = 0
    for count in counts:
        color = (255, 0, 0)
        strip.setPixelColor(pos, Color(*WHITE))
        for i in range(pos + 1, pos + count):
            strip.setPixelColor(i, Color(*color))
        print(f'  Bereich LED {pos:>3} – {pos + count - 1:<3}  '
              f'(Anzahl: {count:>3})  '
              f'Farbe: RGB{color}  |  LED {pos} = weiß')
        pos += count
    strip.show()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='LED-Steuerung mit Linienauswahl')
    parser.add_argument('-c', '--clear', action='store_true', help='LEDs beim Beenden ausschalten')
    args = parser.parse_args()

    strip = PixelStrip(LED_COUNT, LED_PIN, LED_FREQ_HZ, LED_DMA, LED_INVERT, LED_BRIGHTNESS, LED_CHANNEL)
    strip.begin()

    print('=== LED Liniensteuerung ===')
    print('Verfügbare Linien:')
    for key, (name, _) in LINIEN.items():
        print(f'  {key} – {name}')
    print('Beenden mit Ctrl-C\n')

    try:
        while True:
            auswahl = input('Linie wählen (1–5): ').strip()
            if auswahl not in LINIEN:
                print('  Ungültige Eingabe. Bitte eine Zahl zwischen 1 und 5 eingeben.\n')
                continue

            name, counts = LINIEN[auswahl]
            total = sum(counts)
            print(f'\n{name} – {len(counts)} Bereiche, {total} LEDs gesamt:\n')
            clear_strip(strip)
            apply_segments(strip, counts)
            print(f'\nFertig. {total} von {LED_COUNT} LEDs belegt.\n')

    except KeyboardInterrupt:
        print('\nAbbruch.')

    finally:
        if args.clear:
            clear_strip(strip)
            print('LEDs ausgeschaltet.')
