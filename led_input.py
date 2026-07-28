#!/usr/bin/env python3

import argparse
from rpi_ws281x import PixelStrip, Color

# LED strip configuration (same as led_control.py)
LED_COUNT = 300
LED_PIN = 18
LED_FREQ_HZ = 800000
LED_DMA = 10
LED_BRIGHTNESS = 255
LED_INVERT = False
LED_CHANNEL = 0


def clear_strip(strip):
    for i in range(strip.numPixels()):
        strip.setPixelColor(i, Color(0, 0, 0))
    strip.show()


def parse_rgb(rgb_input):
    """Parse 'R G B' or 'R,G,B' string into (r, g, b) tuple. Returns None on error."""
    parts = rgb_input.replace(',', ' ').split()
    if len(parts) != 3:
        return None
    try:
        r, g, b = int(parts[0]), int(parts[1]), int(parts[2])
    except ValueError:
        return None
    if not all(0 <= v <= 255 for v in (r, g, b)):
        return None
    return r, g, b


def light_segment(strip, start, count, r, g, b):
    for i in range(start, start + count):
        strip.setPixelColor(i, Color(r, g, b))
    strip.show()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Interaktive LED-Steuerung mit kumulativem Streifen')
    parser.add_argument('-c', '--clear', action='store_true', help='LEDs beim Beenden ausschalten')
    args = parser.parse_args()

    strip = PixelStrip(LED_COUNT, LED_PIN, LED_FREQ_HZ, LED_DMA, LED_INVERT, LED_BRIGHTNESS, LED_CHANNEL)
    strip.begin()

    current_position = 0

    print('=== LED Interaktiv-Steuerung ===')
    print('Eingabe pro Runde: Anzahl LEDs und Farbe als R G B (z.B. "255 0 0")')
    print('Beenden mit Ctrl-C\n')

    try:
        while True:
            remaining = LED_COUNT - current_position

            if remaining == 0:
                print(f'\nAlle {LED_COUNT} LEDs sind belegt.')
                answer = input('Reset (alle LEDs aus, von vorne beginnen)? [j/n]: ').strip().lower()
                if answer == 'j':
                    clear_strip(strip)
                    current_position = 0
                    print('Strip zurückgesetzt.\n')
                    continue
                else:
                    print('Programm beendet.')
                    break

            print(f'Position {current_position}/{LED_COUNT}  (noch {remaining} LEDs frei)')

            # --- Anzahl ---
            raw_count = input('Anzahl LEDs: ').strip()
            try:
                count = int(raw_count)
            except ValueError:
                print('  Fehler: Bitte eine ganze Zahl eingeben.\n')
                continue
            if count <= 0:
                print('  Fehler: Anzahl muss groesser als 0 sein.\n')
                continue
            if count > remaining:
                print(f'  Hinweis: Nur noch {remaining} LEDs frei – verwende {remaining} statt {count}.')
                count = remaining

            # --- Farbe ---
            raw_color = input('Farbe (R G B): ').strip()
            rgb = parse_rgb(raw_color)
            if rgb is None:
                print('  Fehler: Bitte drei Werte 0-255 eingeben, z.B. "255 128 0".\n')
                continue

            r, g, b = rgb
            light_segment(strip, current_position, count, r, g, b)
            current_position += count

            print(f'  -> LEDs {current_position - count} bis {current_position - 1} leuchten in RGB({r}, {g}, {b})\n')

    except KeyboardInterrupt:
        print('\nAbbruch.')

    finally:
        if args.clear:
            clear_strip(strip)
            print('LEDs ausgeschaltet.')
