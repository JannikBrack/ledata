import time
import board
import neopixel

num_pixels = 100  # anpassen falls nötig: physische LEDs / 3

pixels = neopixel.NeoPixel(
    board.D18,
    num_pixels,
    brightness=0.5,
    auto_write=False,
    pixel_order=neopixel.RGB
)

print("Test 1: Alle LEDs rot")
pixels.fill((255, 0, 0))
pixels.show()
time.sleep(2)

print("Test 2: Alle LEDs grün")
pixels.fill((0, 255, 0))
pixels.show()
time.sleep(2)

print("Test 3: Alle LEDs blau")
pixels.fill((0, 0, 255))
pixels.show()
time.sleep(2)

print("Test 4: Alle LEDs aus")
pixels.fill((0, 0, 0))
pixels.show()
time.sleep(1)

print("Test 5: LED für LED durchlaufen (checkt ob alle Pixel einzeln ansteuerbar sind)")
pixels.fill((0, 0, 0))
pixels.show()
for i in range(num_pixels):
    pixels[i] = (255, 255, 255)
    pixels.show()
    time.sleep(0.05)

print("Fertig!")