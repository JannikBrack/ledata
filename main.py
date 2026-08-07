linie_1 = [9, 7, 13, 5, 5, 8, 6, 14, 8, 8, 7, 7, 5, 3, 3, 4, 4, 4, 5, 4, 4, 1] # Linie 1 bei landwasser angefangen
#linie_2 = [13, 4, 9, 4, 14, 9, 14, 8, 8, 7, 5, 5, 4, 4, 4, 4, 4, 3, 1] # Linie 2 Brühl anfang
#linie_3 = [7, 9, 8, 5, 8, 10, 6, 14, 8, 8, 7, 7, 7, 9, 5, 8, 3, 3, 3, 2, 3, 1] # Linie 3 Munzinger Straße Anfang
#linie_4 = [5, 5, 4, 5, 2, 9, 14, 8, 8, 7, 6, 5, 12, 13, 6, 5, 6, 7, 9, 1]   # Linie 4 Messe Anfang
#linie_5 = [10, 6, 10, 7, 5, 4, 7, 6, 8, 12, 4, 5, 7, 7, 1] # Linie 5 Rieselfeld anfang

from classes import Route, Train, Controller
from rpi_ws281x import PixelStrip


if __name__ == "__main__":
    LED_COUNT = 300
    LED_PIN = 18
    LED_FREQ_HZ = 800000
    LED_DMA = 10
    LED_BRIGHTNESS = 100
    LED_INVERT = False
    LED_CHANNEL = 0


    WHITE = (255, 255, 255)
    RED = (255, 0, 0)

    train = Train(0,1,0)
    route = Route(0, linie_1, [train], WHITE, 0)

    strip = PixelStrip(LED_COUNT, LED_PIN, LED_FREQ_HZ, LED_DMA, LED_INVERT, LED_BRIGHTNESS, LED_CHANNEL)


    controller = Controller([route], strip)
    controller.start()


# ----------
    # Tests
    assert route._end_of_route == route._stations[-1]._position
    assert route._end_of_route - route._start_of_route + 1 == route._max_led_count