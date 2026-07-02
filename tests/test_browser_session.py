import struct

from src.browser.session import BrowserSession


def test_png_dimensions_are_parsed_from_header():
    png_header = b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + struct.pack(">II", 1440, 1000)

    assert BrowserSession._png_dimensions(png_header) == (1440, 1000)
