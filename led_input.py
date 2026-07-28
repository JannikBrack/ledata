#!/usr/bin/env python3

import argparse
import random
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
#COUNTS = [10, 6, 10, 7, 5, 4, 7, 6, 8, 12, 4, 5, 7, 7, 1] # Linie 5
COUNTS = [9, 7, 13, 5, 5, 8, 6, 14, 8, 8, 7, 7, 5, 3, 3, 4, 4, 4, 5, 4, 4] # Linie 1


def clear_strip(strip):
    for i in range(strip.numPixels()):
        strip.setPixelColor(i, Color(0, 0, 0))
    strip.show()


def apply_segments(strip, counts):
    """Setzt alle Segmente auf den Strip: erste LED weiß, Rest Segmentfarbe."""
    pos = 0
    prev_color = None
    for count in counts:
        color = (255, 0,   0)
        # Erste LED des Bereichs: weiß
        strip.setPixelColor(pos, Color(*WHITE))
        # Restliche LEDs des Bereichs: Segmentfarbe
        for i in range(pos + 1, pos + count):
            strip.setPixelColor(i, Color(*color))
        print(f'  Bereich LED {pos:>3} – {pos + count - 1:<3}  '
              f'(Anzahl: {count:>3})  '
              f'Farbe: RGB{color}  |  LED {pos} = weiß')
        pos += count
        prev_color = color
    strip.show()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='LED-Steuerung mit automatischer Farbwahl')
    parser.add_argument('-c', '--clear', action='store_true', help='LEDs beim Beenden ausschalten')
    args = parser.parse_args()

    strip = PixelStrip(LED_COUNT, LED_PIN, LED_FREQ_HZ, LED_DMA, LED_INVERT, LED_BRIGHTNESS, LED_CHANNEL)
    strip.begin()

    print('=== LED Automatische Farbsteuerung ===')
    print(f'Vordefinierte Bereiche: {COUNTS}  (Summe: {sum(COUNTS)} LEDs)')
    print('Eingabe: LED-Anzahlen der Bereiche, getrennt durch Leerzeichen')
    print('Einfach Enter druecken um die vordefinierten Bereiche zu verwenden.')
    print('Beenden mit Ctrl-C\n')

    try:
        while True:
            raw = input('LED-Anzahlen (Enter = Standard): ').strip()
            if not raw:
                counts = COUNTS
                print(f'  Verwende Standard: {counts}')
            else:
                try:
                    counts = [int(x) for x in raw.split()]
                except ValueError:
                    print('  Fehler: Bitte nur ganze Zahlen eingeben.\n')
                    continue

            if any(c <= 0 for c in counts):
                print('  Fehler: Alle Anzahlen muessen groesser als 0 sein.\n')
                continue

            total = sum(counts)
            if total > LED_COUNT:
                print(f'  Fehler: Summe aller Bereiche ({total}) ueberschreitet den Streifen ({LED_COUNT} LEDs).\n')
                continue

            print(f'\n{len(counts)} Bereiche, {total} LEDs gesamt:\n')
            clear_strip(strip)
            apply_segments(strip, counts)
            print(f'\nFertig. {total} von {LED_COUNT} LEDs belegt.\n')

    except KeyboardInterrupt:
        print('\nAbbruch.')

    finally:
        if args.clear:
            clear_strip(strip)
            print('LEDs ausgeschaltet.')
