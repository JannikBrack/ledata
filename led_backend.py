"""LED-Backend: echter rpi_ws281x auf dem Pi, sonst ein Fake-Strip fuer den Mac.

classes.py importiert PixelStrip/Color ausschliesslich hieraus, damit das
Projekt auch ohne angeschlossene Hardware (und ohne rpi_ws281x) laeuft.
"""

HAVE_RPI = True
try:  # pragma: no cover - nur auf echter Hardware
    from rpi_ws281x import PixelStrip, Color
except Exception:  # ImportError auf Nicht-Pi-Rechnern
    HAVE_RPI = False

    def Color(red, green, blue):
        """Gleiche Semantik wie rpi_ws281x.Color: 0xRRGGBB als int."""
        return (int(red) << 16) | (int(green) << 8) | int(blue)


def _channels(color):
    return ((int(color) >> 16) & 0xFF, (int(color) >> 8) & 0xFF, int(color) & 0xFF)


def _color_char(color) -> str:
    """Ein Zeichen pro LED fuer die ASCII-Vorschau."""
    red, green, blue = _channels(color)
    if not (red or green or blue):
        return "."
    if red == green == blue:
        return "#" if red >= 200 else "+"
    if red and green and not blue:
        return "Y"
    if red and blue and not green:
        return "M"
    if green and blue and not red:
        return "C"
    if red and not green and not blue:
        return "R"
    if green and not red and not blue:
        return "G"
    if blue and not red and not green:
        return "B"
    return "+"


class FakeStrip:
    """Ersatz fuer PixelStrip: haelt die Pixel im Speicher und kann sie zeigen."""

    def __init__(self, num, *args, render=False, **kwargs) -> None:
        self._num = int(num)
        self._pixels = [0] * self._num
        self._render = bool(render)

    def begin(self):
        pass

    def numPixels(self) -> int:
        return self._num

    def setPixelColor(self, index, color):
        if 0 <= index < self._num:
            self._pixels[index] = int(color)

    def getPixelColor(self, index) -> int:
        return self._pixels[index]

    def show(self):
        if not self._render:
            return
        line = "".join(_color_char(color) for color in self._pixels)
        # Wagenruecklauf: jede Zeile ueberschreibt die vorherige
        print("\r" + line, end="", flush=True)

    def __str__(self) -> str:
        return f"FakeStrip(pixels={self._num}, render={self._render})"


if not HAVE_RPI:
    PixelStrip = FakeStrip
