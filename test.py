#!/usr/bin/env python3
from rpi_ws281x import PixelStrip, Color
import time

LED_COUNT = 100
LED_PIN = 18
LED_FREQ_HZ = 800000
LED_DMA = 10
LED_BRIGHTNESS = 150
LED_INVERT = False
LED_CHANNEL = 0

strip = PixelStrip(LED_COUNT, LED_PIN, LED_FREQ_HZ, LED_DMA, LED_INVERT, LED_BRIGHTNESS, LED_CHANNEL)
strip.begin()

# Alle LEDs weiß einschalten
for i in range(strip.numPixels()):
    strip.setPixelColor(i, Color(255, 255, 255))
strip.show()

time.sleep(200)

# Alle LEDs ausschalten
for i in range(strip.numPixels()):
    strip.setPixelColor(i, Color(0, 0, 0))
strip.show()