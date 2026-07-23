import time
from rpi_ws281x import PixelStrip, Color

# LED strip configuration
LED_COUNT = 30        # Number of LED pixels
LED_PIN = 18          # GPIO pin connected to the pixels (18 uses PWM!)
LED_FREQ_HZ = 800000  # LED signal frequency in hertz (usually 800khz)
LED_DMA = 10          # DMA channel to use for generating signal (try 10)
LED_BRIGHTNESS = 50  # Set to 0 for darkest and 255 for brightest
LED_INVERT = False    # True to invert the signal (when using NPN transistor level shift)
LED_CHANNEL = 0       # Set to '1' for GPIOs 13, 19, 41, 45 or 53


def all_on(strip, color=Color(0, 255, 0)):
    for pixel_index in range(strip.numPixels()):
        strip.setPixelColor(pixel_index, color)
    strip.show()


def all_off(strip):
    for pixel_index in range(strip.numPixels()):
        strip.setPixelColor(pixel_index, Color(0, 0, 0))
    strip.show()


if __name__ == "__main__":
    strip = PixelStrip(
        LED_COUNT,
        LED_PIN,
        LED_FREQ_HZ,
        LED_DMA,
        LED_INVERT,
        LED_BRIGHTNESS,
        LED_CHANNEL,
    )
    strip.begin()

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
