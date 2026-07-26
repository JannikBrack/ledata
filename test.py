import time
import board
import neopixel_spi as neopixel

NUM_PIXELS = 50
PIXEL_ORDER = neopixel.GRB
COLORS = (0xFF0000, 0xFFFF00, 0x00FF00, 0x00FFFF, 0x0000FF, 0xFF00FF)
DELAY = 0.2

spi = board.SPI()

pixels = neopixel.NeoPixel_SPI(spi,
                                NUM_PIXELS,
                                pixel_order=PIXEL_ORDER,
                                auto_write=False)

while True:
    for color in COLORS:
        for i in range(NUM_PIXELS):
            pixels[i] = color
            pixels.show()
            time.sleep(DELAY)
            pixels.fill(0)