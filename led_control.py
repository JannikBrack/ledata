import time
from rpi_ws281x import PixelStrip, Color

# LED strip configuration
LED_COUNT = 100        # Number of LED pixels
LED_PIN = 18           # GPIO pin connected to the pixels (18 uses PWM!)
LED_FREQ_HZ = 800000   # LED signal frequency in hertz (usually 800khz)
LED_DMA = 10           # DMA channel to use for generating signal (try 10)
LED_BRIGHTNESS = 128   # Set to 0 for darkest and 255 for brightest
LED_INVERT = False     # True to invert the signal (when using NPN transistor level shift)
LED_CHANNEL = 0        # Set to '1' for GPIOs 13, 19, 41, 45 or 53

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

print("Test 1: Alle LEDs rot")
for i in range(strip.numPixels()):
    strip.setPixelColor(i, Color(255, 0, 0))
strip.show()
time.sleep(2)

print("Test 2: Alle LEDs grün")
for i in range(strip.numPixels()):
    strip.setPixelColor(i, Color(0, 255, 0))
strip.show()
time.sleep(2)

print("Test 3: Alle LEDs blau")
for i in range(strip.numPixels()):
    strip.setPixelColor(i, Color(0, 0, 255))
strip.show()
time.sleep(2)

print("Test 4: Alle LEDs aus")
for i in range(strip.numPixels()):
    strip.setPixelColor(i, Color(0, 0, 0))
strip.show()
time.sleep(1)

print("Test 5: LED für LED durchlaufen (checkt ob alle Pixel einzeln ansteuerbar sind)")
for i in range(strip.numPixels()):
    strip.setPixelColor(i, Color(0, 0, 0))
strip.show()
for i in range(strip.numPixels()):
    strip.setPixelColor(i, Color(255, 255, 255))
    strip.show()
    time.sleep(0.05)

print("Fertig!")