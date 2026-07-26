#!/usr/bin/env python3
from rpi_ws281x import PixelStrip, Color
import time
import math
import signal
import sys

# === LED strip setup ===
LED_COUNT = 100        # LED quantity
LED_PIN = 18          # GPIO18
LED_FREQ_HZ = 800000  # signal frequency（Hz）
LED_DMA = 10          # DMA channel
LED_BRIGHTNESS = 150  # brightness（0-255）
LED_INVERT = False    # signal reverse
LED_CHANNEL = 0       # PWM channel

# format led strip
strip = PixelStrip(LED_COUNT, LED_PIN, LED_FREQ_HZ, LED_DMA, LED_INVERT, LED_BRIGHTNESS, LED_CHANNEL)
strip.begin()

# === color generation function ===
def wheel(pos):
    """change the value of 0-255 into rainbow color（red→green→blue recycle）"""
    pos = 255 - pos  # reverse color direction（optional）
    if pos < 85:
        return Color(pos * 3, 255 - pos * 3, 0)
    elif pos < 170:
        pos -= 85
        return Color(255 - pos * 3, 0, pos * 3)
    else:
        pos -= 170
        return Color(0, pos * 3, 255 - pos * 3)

def smooth_wheel(pos):
    """more smooth rainbow color transition（trigonometric function version）"""
    r = int(255 * (0.5 + 0.5 * math.sin(pos * 0.0245)))
    g = int(255 * (0.5 + 0.5 * math.sin(pos * 0.0245 + 2.094)))  # +120°
    b = int(255 * (0.5 + 0.5 * math.sin(pos * 0.0245 + 4.188)))  # +240°
    return Color(r, g, b)

# === main effect function ===
def rainbow_flow(speed_ms=20, smooth=True):
    """recycle full color running effect
    :param speed_ms: basic speed（ms）
    :param smooth: whether USE_SMOOTH_COLOR
    """
    step = 0
    try:
        while True:
            # dynamic_speed control（optional）
            dynamic_speed = speed_ms * (0.8 + 0.2 * math.sin(step * 0.01))

            for i in range(strip.numPixels()):
                # calculate color_phase（form flow effect）
                hue = int((i * 256 / strip.numPixels()) + step) % 256
                color = smooth_wheel(hue) if smooth else wheel(hue)
                strip.setPixelColor(i, color)

            strip.show()
            time.sleep(dynamic_speed / 1000.0)
            step += 1
    except KeyboardInterrupt:
        pass

# === escape safely ===
def signal_handler(sig, frame):
    print("\n close LED...")
    for i in range(strip.numPixels()):
        strip.setPixelColor(i, Color(0, 0, 0))
    strip.show()
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)

# === main program ===
if __name__ == '__main__':
    print("=== addressable LED strip full color flow effect ===")
    print("Ctrl+C close program")

    # parameter setup
    USE_SMOOTH_COLOR = True  # USE_SMOOTH_COLOR
    BASE_SPEED_MS = 15       # basic flow speed（ms）

    rainbow_flow(speed_ms=BASE_SPEED_MS, smooth=USE_SMOOTH_COLOR)