"""Shared fixtures and helpers for the pyplotrs test suite.

Two things make the suite reproducible on any machine:

* **The font is pinned** to Liberation Sans (see :func:`pin_font`). Body text
  otherwise resolves to the host's Arial/Helvetica if installed, which would
  change every glyph advance and so every laid-out box. Note that pinning is by
  family *name*, and a host that ships its own Liberation Sans wins over the
  copy compiled into the extension - see :func:`body_font_is_the_bundled_one`,
  which the pixel-comparison tests use to skip rather than fail there.
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


BUNDLED_BODY = Path(__file__).parent.parent / "assets" / "fonts" / "LiberationSans-Regular.ttf"


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


def body_font_is_the_bundled_one() -> bool:
    """Whether the pinned body font is the *bundled* file, byte for byte.

    Pinning is by family **name**, and name resolution walks the host's font
    database before it reaches the bundled fallback (``resolve_from_host`` in
    ``crates/pyplotrs-py``). So on a machine that ships its own Liberation Sans
    - most Linux distributions do - ``set_font_family("Liberation Sans")``
    selects *that* file, not the one compiled into the extension. The docstring
    above this module used to say the pinned font is "byte-identical
    everywhere"; it is byte-identical only where the host has no Liberation Sans
    of its own, or happens to ship the same build of it.

    That is invisible for every test except the ones comparing rendered pixels
    against a committed image: a different build of the same family moves glyph
    outlines slightly, which lands as a handful of channels off by 60-200 at
    glyph edges - far more than the golden tolerances allow, and correctly so,
    since that tolerance exists to catch changes smaller than this.

    The `linux (ubuntu-22.04, x86_64)` CI leg is exactly this case: it runs on
    the host rather than in a container, ubuntu-22.04 ships a Liberation Sans
    that is not the bundled one, and every image test on that leg failed while
    the same tests passed on macOS, Windows, Alpine and every emulated arch -
    none of which have a competing copy.
    """
    if not BUNDLED_BODY.is_file():
        return False
    from pyplotrs import _pyplotrs_core as _core

    return _core.body_font_bytes() == BUNDLED_BODY.read_bytes()


@pytest.fixture
def needs_bundled_body_font():
    """Skip a pixel comparison when the host's own Liberation Sans won."""
    if not body_font_is_the_bundled_one():
        pytest.skip(
            "the pinned 'Liberation Sans' resolved to the host's copy rather "
            "than the bundled one, so committed images cannot match glyph for "
            "glyph; see conftest.body_font_is_the_bundled_one"
        )


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
