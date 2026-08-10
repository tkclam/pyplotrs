"""Color-space conversions and colorblindness diagnostics.

State-of-the-art color science, exposed directly rather than buried in the
colormap machinery: sRGB <-> linear-light RGB <-> CIE XYZ <-> CIELAB <->
Oklab/Oklch <-> CAM16-UCS, plus color-vision-deficiency (CVD) simulation and
two colormap-quality diagnostics. Everything runs in Rust
(:mod:`pyplotrs._pyplotrs_core`, backed by the ``pyplotrs-color`` crate,
itself built on the `palette <https://github.com/Ogeon/palette>`_ crate).

Oklab (Ottosson, 2020) is what :class:`pyplotrs.colormaps.Colormap` uses to
interpolate custom ``stops=`` by default - it is the practical, contemporary
choice for perceptually smooth gradients. CAM16-UCS is the more rigorous (and
more expensive) full color-appearance model; it backs :func:`distance` and
the two diagnostics below rather than everyday interpolation::

    from pyplotrs import color, colormaps

    color.to_oklab((255, 0, 0))              # (0.628, 0.225, 0.126)
    color.simulate_cvd((220, 20, 20), "deuteranopia")  # (141, 125, 0)

    cm = colormaps.get_cmap("coolwarm")
    color.cvd_safe_report(cm)      # {"protanopia": 0.77, "deuteranopia": 0.77, "tritanopia": 0.94}
    color.perceptual_uniformity(cm)  # 0.25 - lower is more uniform
"""

from __future__ import annotations

from typing import Literal

from . import _pyplotrs_core as _core
from .colormaps import Colormap, get_cmap

_RGB = tuple[int, int, int]
_Triple = tuple[float, float, float]
CvdKind = Literal["protanopia", "deuteranopia", "tritanopia"]

_CVD_KINDS: tuple[CvdKind, ...] = ("protanopia", "deuteranopia", "tritanopia")


def to_oklab(rgb: _RGB) -> _Triple:
    """sRGB -> Oklab (`L` in ``[0, 1]``; `a`/`b` roughly ``[-0.4, 0.4]``)."""
    return _core.srgb_to_oklab(rgb)


def from_oklab(lab: _Triple) -> _RGB:
    """Oklab -> sRGB (out-of-gamut input is clipped per channel)."""
    return _core.oklab_to_srgb(lab)


def to_oklch(rgb: _RGB) -> _Triple:
    """sRGB -> Oklch (`L` in ``[0, 1]``, `chroma` >= 0, `hue` in degrees)."""
    return _core.srgb_to_oklch(rgb)


def from_oklch(lch: _Triple) -> _RGB:
    """Oklch -> sRGB."""
    return _core.oklch_to_srgb(lch)


def to_lab(rgb: _RGB) -> _Triple:
    """sRGB -> CIELAB (D65 white point; `L*` in ``[0, 100]``)."""
    return _core.srgb_to_lab(rgb)


def from_lab(lab: _Triple) -> _RGB:
    """CIELAB (D65) -> sRGB."""
    return _core.lab_to_srgb(lab)


def to_xyz(rgb: _RGB) -> _Triple:
    """sRGB -> CIE 1931 XYZ (D65 white point, `Y` in ``[0, 1]``)."""
    return _core.srgb_to_xyz(rgb)


def from_xyz(xyz: _Triple) -> _RGB:
    """CIE 1931 XYZ (D65) -> sRGB."""
    return _core.xyz_to_srgb(xyz)


def to_linear(rgb: _RGB) -> _Triple:
    """Encoded (gamma) sRGB -> linear-light RGB (each component ``[0, 1]``)."""
    return _core.srgb_to_linear(rgb)


def from_linear(rgb: _Triple) -> _RGB:
    """Linear-light RGB -> encoded (gamma) sRGB."""
    return _core.linear_to_srgb(rgb)


def to_cam16ucs(rgb: _RGB) -> _Triple:
    """sRGB -> CAM16-UCS (Jmh form: lightness, colorfulness, hue-degrees),
    under pyplotrs' fixed viewing conditions (a static D65 white point,
    40 cd/m^2 adapting luminance - CAM16 is an *appearance* model, so results
    are only meaningful relative to one consistent choice of conditions)."""
    return _core.srgb_to_cam16ucs(rgb)


def from_cam16ucs(ucs: _Triple) -> _RGB:
    """CAM16-UCS (Jmh form) -> sRGB."""
    return _core.cam16ucs_to_srgb(ucs)


def distance(a: _RGB, b: _RGB) -> float:
    """Perceptual (CAM16-UCS) distance between two sRGB colors - a "how
    different do these look" metric, more reliable than Euclidean RGB or even
    CIE76 Lab distance."""
    return _core.cam16ucs_distance(a, b)


def simulate_cvd(rgb: _RGB, kind: CvdKind) -> _RGB:
    """How `rgb` appears to someone with `kind` dichromacy (the
    Machado/Oliveira/Fernandes 2009 model)."""
    return _core.simulate_cvd(rgb, kind)


def cvd_safe_report(cmap) -> dict[CvdKind, float]:
    """Worst-case distinguishability of a colormap under each CVD kind.

    ``cmap`` is anything :func:`pyplotrs.colormaps.get_cmap` accepts (a name
    or a :class:`~pyplotrs.colormaps.Colormap`). Each value is `1.0` (CVD
    doesn't shrink the map's worst-case contrast at all) down to `0.0` (some
    pair of colors that reads as distinct normally becomes visually identical
    under that CVD). Below ~0.5 is worth treating as a real accessibility
    concern for that deficiency.
    """
    table = get_cmap(cmap)._table
    return {kind: _core.cvd_safety_ratio(table, kind) for kind in _CVD_KINDS}


def perceptual_uniformity(cmap) -> float:
    """Perceptual-uniformity roughness of a colormap (`cmap`: a name or a
    :class:`~pyplotrs.colormaps.Colormap`): the coefficient of variation of
    the CAM16-UCS step size between consecutive table entries. `0.0` means
    every step looks equally large (ideal for mapping continuous data, where
    visual step size should track data step size); larger values mean some
    regions of the map compress more data range into less visual change than
    others."""
    return _core.perceptual_uniformity(get_cmap(cmap)._table)
