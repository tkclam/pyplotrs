"""Shared fixtures and helpers for the pyplotrs test suite.

Two things make the suite reproducible on any machine:

* **The font is pinned** to the bundled Liberation Sans (see :func:`pin_font`).
  Body text otherwise resolves to the host's Arial/Helvetica if installed, which
  would change every glyph advance and so every laid-out box. Liberation Sans is
  compiled into the extension via ``include_bytes!``, so it is byte-identical
  everywhere.
* **Rendering is deterministic** once the font is fixed - the same figure saves
  to the same PNG bytes run after run. The golden tests still compare with a
  tolerance rather than by hash, to absorb any last-bit float differences
  between architectures.
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

import pyplotrs as pp
import pytest

GOLDEN_DIR = Path(__file__).parent / "golden"


@pytest.fixture(autouse=True, scope="session")
def pin_font():
    """Force the bundled font for every test in the session.

    ``autouse`` so no test can accidentally depend on the host's font set.
    """
    pp.set_font_family("Liberation Sans")
    assert pp.resolved_font_name() == "Liberation Sans", (
        "the bundled Liberation Sans should always resolve; got "
        f"{pp.resolved_font_name()!r}"
    )
    yield
    pp.set_font_family()  # restore the default preference order


@pytest.fixture
def figure_factory():
    """Build a small figure with a pinned size, for cheap renders."""

    def make(nrows: int = 1, ncols: int = 1, **kwargs):
        kwargs.setdefault("figsize", (240, 180))
        return pp.subplots(nrows, ncols, **kwargs)

    return make


# -- PNG decoding (dependency-free) ------------------------------------------


def read_png(path: Path | str) -> tuple[int, int, bytes]:
    """Decode an 8-bit RGBA PNG to ``(width, height, rgba_bytes)``.

    pyplotrs writes straight (non-interlaced) RGBA8, so a minimal reader is
    enough and keeps the test suite free of an image dependency - matching the
    package's own zero-runtime-dependency stance.
    """
    data = Path(path).read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n", "not a PNG"

    width = height = 0
    idat = bytearray()
    pos = 8
    while pos < len(data):
        (length,) = struct.unpack(">I", data[pos:pos + 4])
        ctype = data[pos + 4:pos + 8]
        body = data[pos + 8:pos + 8 + length]
        if ctype == b"IHDR":
            width, height, depth, color = struct.unpack(">IIBB", body[:10])
            assert depth == 8, f"expected 8-bit channels, got {depth}"
            assert color == 6, f"expected RGBA (color type 6), got {color}"
            assert body[12] == 0, "interlaced PNG is not supported by this reader"
        elif ctype == b"IDAT":
            idat += body
        elif ctype == b"IEND":
            break
        pos += 12 + length  # length + type + data + crc

    raw = zlib.decompress(bytes(idat))
    stride = width * 4
    out = bytearray(height * stride)
    prev = bytearray(stride)
    src = 0
    for y in range(height):
        ftype = raw[src]
        src += 1
        line = bytearray(raw[src:src + stride])
        src += stride
        # Undo the per-scanline filter (PNG spec 9.2). bpp is 4 for RGBA8.
        if ftype == 1:  # Sub
            for i in range(4, stride):
                line[i] = (line[i] + line[i - 4]) & 0xFF
        elif ftype == 2:  # Up
            for i in range(stride):
                line[i] = (line[i] + prev[i]) & 0xFF
        elif ftype == 3:  # Average
            for i in range(stride):
                left = line[i - 4] if i >= 4 else 0
                line[i] = (line[i] + ((left + prev[i]) >> 1)) & 0xFF
        elif ftype == 4:  # Paeth
            for i in range(stride):
                a = line[i - 4] if i >= 4 else 0
                b = prev[i]
                c = prev[i - 4] if i >= 4 else 0
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                pred = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                line[i] = (line[i] + pred) & 0xFF
        elif ftype != 0:
            raise AssertionError(f"unknown PNG filter type {ftype}")
        out[y * stride:(y + 1) * stride] = line
        prev = line

    return width, height, bytes(out)


def image_diff(a: bytes, b: bytes) -> tuple[float, float, int]:
    """Compare two RGBA buffers, returning ``(mean, frac_over_4, max)``.

    ``mean`` alone is a poor metric for a plot: the canvas is mostly background,
    so it dilutes toward zero and hides real changes. ``frac_over_4`` - the
    fraction of channel samples differing by more than 4 levels - is the
    sensitive one, because it counts only pixels that genuinely moved rather
    than antialiasing jitter.
    """
    assert len(a) == len(b), f"size mismatch: {len(a)} vs {len(b)}"
    total = 0
    over = 0
    worst = 0
    for x, y in zip(a, b):
        d = x - y if x > y else y - x
        total += d
        if d > 4:
            over += 1
        if d > worst:
            worst = d
    n = len(a)
    return total / n, over / n, worst


# Calibrated empirically: an identical render scores (0, 0, 0) - output is
# byte-deterministic once the font is pinned - while a 0.01 pt line-width nudge,
# about the smallest change worth catching, scores (0.0075, 0.00045, 64). The
# thresholds sit an order of magnitude below that, leaving room only for
# last-bit rasterization differences between architectures.
GOLDEN_MEAN_TOL = 0.002
GOLDEN_FRAC_TOL = 1e-4


def assert_matches_golden(png_path: Path, name: str,
                          mean_tol: float = GOLDEN_MEAN_TOL,
                          frac_tol: float = GOLDEN_FRAC_TOL) -> None:
    """Compare a rendered PNG against ``tests/golden/<name>.png``.

    Set ``PYPLOTRS_UPDATE_GOLDEN=1`` to (re)write the reference instead of
    comparing - use after an intentional visual change, and eyeball the diff in
    the commit.
    """
    import os

    ref = GOLDEN_DIR / f"{name}.png"
    if os.environ.get("PYPLOTRS_UPDATE_GOLDEN"):
        GOLDEN_DIR.mkdir(exist_ok=True)
        ref.write_bytes(Path(png_path).read_bytes())
        pytest.skip(f"golden {name} updated")

    assert ref.exists(), (
        f"missing golden reference {ref}; regenerate with "
        f"PYPLOTRS_UPDATE_GOLDEN=1 pytest tests/test_golden.py"
    )
    gw, gh, gold = read_png(ref)
    rw, rh, got = read_png(png_path)
    assert (rw, rh) == (gw, gh), f"size changed: {(rw, rh)} vs golden {(gw, gh)}"

    mean, frac, worst = image_diff(gold, got)
    assert mean <= mean_tol and frac <= frac_tol, (
        f"{name}: render differs from golden - mean {mean:.5f} (limit {mean_tol}), "
        f"{frac * 100:.4f}% of channels off by >4 (limit {frac_tol * 100:.4f}%), "
        f"worst {worst}. If intentional, regenerate with PYPLOTRS_UPDATE_GOLDEN=1."
    )
