#!/home/ledata/Desktop/ledata/venv/bin/python

import time
from rpi_ws281x import PixelStrip, Color

# LED strip configuration
# RGB+CCT: 2x WS2811 IC pro LED-Gruppe (IC1=RGB, IC2=CW/WW)
LED_COUNT = 100        # Anzahl ICs gesamt (= 2 × physische LED-Gruppen)
LED_PIN = 21
LED_FREQ_HZ = 400000
LED_DMA = 10
LED_BRIGHTNESS = 128
LED_INVERT = False
LED_CHANNEL = 0

strip = PixelStrip(LED_COUNT, LED_PIN, LED_FREQ_HZ, LED_DMA, LED_INVERT, LED_BRIGHTNESS, LED_CHANNEL)
strip.begin()

NUM_GROUPS = LED_COUNT // 3  # 150 physische LED-Gruppen

def set_all(r, g, b):
    for i in range(NUM_GROUPS):
        strip.setPixelColor(i * 2,     Color(r, g, b))    # IC1: RGB
    strip.show()

print("Test 1: Alle LEDs rot")
set_all(255, 0, 0)
time.sleep(2)

print("Test 2: Alle LEDs grün")
set_all(0, 255, 0)
time.sleep(2)

print("Test 3: Alle LEDs blau")
set_all(0, 0, 255)
time.sleep(2)

print("Test 6: Alle LEDs aus")
set_all(0, 0, 0)
time.sleep(1)

print("Test 7: LED für LED durchlaufen")
for i in range(NUM_GROUPS):
    strip.setPixelColor(i * 2, Color(255, 255, 255))
    strip.show()
    time.sleep(0.05)
set_all(0, 0, 0)

print("Fertig!")