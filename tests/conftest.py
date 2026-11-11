from __future__ import annotations

import struct
import zlib

import pytest

import pyplotrs as pp


@pytest.fixture(autouse=True)
def bundled_font():
    """Render with the bundled font so results do not depend on the host."""
    pp.set_theme(font_family=("Liberation Sans",))
    yield
    pp.set_theme()


def decode_png(data: bytes) -> tuple[int, int, list[bytes]]:
    """``(width, height, rows)`` of an 8-bit RGBA PNG; each row is RGBA bytes."""
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    pos, idat, width = 8, b"", 0
    while pos < len(data):
        (length,) = struct.unpack(">I", data[pos : pos + 4])
        kind = data[pos + 4 : pos + 8]
        body = data[pos + 8 : pos + 8 + length]
        if kind == b"IHDR":
            width, height, depth, color = struct.unpack(">IIBB", body[:10])
            assert (depth, color) == (8, 6), "expected 8-bit RGBA"
        elif kind == b"IDAT":
            idat += body
        pos += 12 + length
    raw = zlib.decompress(idat)
    stride = width * 4
    rows: list[bytes] = []
    prev = bytearray(stride)
    for y in range(height):
        f = raw[y * (stride + 1)]
        line = bytearray(raw[y * (stride + 1) + 1 : (y + 1) * (stride + 1)])
        for i in range(stride):
            a = line[i - 4] if i >= 4 else 0
            b = prev[i]
            c = prev[i - 4] if i >= 4 else 0
            if f == 1:
                line[i] = (line[i] + a) & 255
            elif f == 2:
                line[i] = (line[i] + b) & 255
            elif f == 3:
                line[i] = (line[i] + (a + b) // 2) & 255
            elif f == 4:
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                line[i] = (line[i] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
        rows.append(bytes(line))
        prev = line
    return width, height, rows


def pixel(rows: list[bytes], x: int, y: int) -> tuple[int, int, int, int]:
    r = rows[y]
    return r[4 * x], r[4 * x + 1], r[4 * x + 2], r[4 * x + 3]
