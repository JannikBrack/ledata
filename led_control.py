import time
import board
import neopixel

# LED strip configuration
LED_COUNT = 100       # Number of LED pixels
LED_PIN = board.D18   # GPIO pin connected to the pixels
LED_BRIGHTNESS = 0.2  # Set to 0.0 for darkest and 1.0 for brightest


def all_on(strip, color=(255, 255, 255)):
    strip.fill(color)
    strip.show()


def all_off(strip):
    strip.fill((0, 0, 0))
    strip.show()


if __name__ == "__main__":
    strip = neopixel.NeoPixel(
        LED_PIN,
        LED_COUNT,
        brightness=LED_BRIGHTNESS,
        auto_write=False,
    )

    print("Press Ctrl-C to quit.")
    try:
        while True:
            print("All LEDs on")
            all_on(strip)
            time.sleep(5)

            print("All LEDs off")
            all_off(strip)
            time.sleep(5)
    except KeyboardInterrupt:
        all_off(strip)
