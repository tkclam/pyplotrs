"""pyplotrs - publication-quality static figures, with a Rust rendering core.

Every figure is an explicit object; there is no current-figure state and no
``pyplot`` module-level drawing surface, so two figures (or two threads) never
interfere::

    import pyplotrs as pp

    fig, ax = pp.subplots()
    ax.line([0, 1, 2, 3], [0, 1, 4, 9], label="y = x^2")
    ax.set(title="Hello", xlabel="x", ylabel="y")
    ax.legend()
    fig.save("hello.pdf")   # editable, selectable text

Saving picks the backend from the extension: ``.pdf`` (embedded, subset fonts -
the text stays real), ``.svg``, ``.png`` (at ``dpi=``), ``.html``
(self-contained). In a notebook a ``Figure`` renders itself inline.

Start at ``subplots``; ``Axes`` carries the marks, ``Figure`` the
layout and output. [`themes`][pyplotrs.themes], [`colormaps`][pyplotrs.colormaps],
[`scales`][pyplotrs.scales], [`ticker`][pyplotrs.ticker] and [`norms`][pyplotrs.norms]
hold the styling and axis vocabulary.

Full documentation: https://tkclam.github.io/pyplotrs/
"""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version

from . import _pyplotrs_core as _core
from . import color, colormaps, norms, palettes, scales, ticker
from . import theme as themes
from ._const import DEFAULT_FIGSIZE
from ._figure import (
    Axes,
    Axes3D,
    Figure,
    GridSpec,
    Mappable,
    PolarAxes,
    subplot_mosaic,
    subplots,
)
from .animation import Animation, animate
from .colormaps import Colormap, get_cmap
from .theme import Theme

try:
    #: The installed version, read from the distribution metadata rather than
    #: hardcoded, so it cannot drift from what was actually built. The single
    #: source is `[workspace.package].version` in Cargo.toml; maturin copies it
    #: into the wheel metadata, and this reads it back.
    __version__ = _pkg_version("pyplotrs")
except PackageNotFoundError:  # pragma: no cover - running from a source tree
    __version__ = "0.0.0+unknown"


def figure(figsize: tuple[float, float] = DEFAULT_FIGSIZE, *, theme=None,
           units: str = "pt") -> Figure:
    """Create an empty ``Figure`` (no axes). Use
    ``Figure.add_gridspec`` + ``Figure.add_subplot`` to place spanning
    axes, or ``subplots`` / ``subplot_mosaic`` for the common cases."""
    fig = Figure(figsize=figsize, nrows=1, ncols=1, theme=theme, units=units)
    fig.axes = []
    fig._spans = []
    return fig


def set_font_family(*families) -> None:
    """Set the preferred sans-serif family names for body text, tried in order.

    pyplotrs' analog of matplotlib's ``rcParams["font.sans-serif"]``. The
    default is ``Arial``, ``Helvetica``, ``Liberation Sans``: the host's Arial
    is used if installed, else Helvetica, else the bundled Liberation Sans
    (Arial-metric-compatible). Whichever is chosen is **embedded into every
    saved figure** (PDF/SVG/PNG/HTML), so a saved file always looks identical
    when viewed on another machine.

    Accepts either a single iterable or positional names::

        pyplotrs.set_font_family("Calibri", "Arial")
        pyplotrs.set_font_family(["Calibri", "Arial"])

    Call with no arguments to restore the default. Arial and Helvetica are
    proprietary and never shipped with pyplotrs; they are only used if already
    present on the machine.
    """
    if len(families) == 1 and not isinstance(families[0], str):
        families = tuple(families[0])
    _core.set_sans_serif([str(f) for f in families])


def get_font_family() -> list[str]:
    """The preferred sans-serif family names, in order. Defaults to
    ``["Arial", "Helvetica", "Liberation Sans"]``."""
    return _core.get_sans_serif()


def set_unicode_minus(on: bool = True) -> None:
    """Whether negative numeric labels are signed with U+2212 MINUS SIGN.

    pyplotrs' analog of matplotlib's ``rcParams["axes.unicode_minus"]``, and
    on by default for the same reason: the minus is drawn on the math axis at
    the width of a ``+``, where the ASCII hyphen-minus is a short, low
    word-joiner that leaves a tick column looking ragged.

    Turn it off with ``set_unicode_minus(False)`` if labels must survive being
    copied out of a saved SVG/PDF and parsed back as numbers, or if a font you
    have set lacks the glyph::

        pyplotrs.set_unicode_minus(False)

    This governs labels pyplotrs formats from a number - axis and colorbar
    ticks, and the numeric [`ticker`][pyplotrs.ticker] formatters. Text you supply
    yourself is never rewritten, and ``$...$`` math always uses a real minus.
    """
    ticker._UNICODE_MINUS = bool(on)


def get_unicode_minus() -> bool:
    """Whether negative numeric labels use U+2212 (see
    ``set_unicode_minus``). Defaults to ``True``."""
    return ticker._UNICODE_MINUS


def resolved_font_name() -> str:
    """The family name body text actually resolves to on this host right now
    (e.g. ``"Arial"`` if installed, otherwise ``"Liberation Sans"``)."""
    return _core.resolved_font_name()


def resolved_font_variants() -> list[tuple[str, str]]:
    """What each body face resolves to here, as ``[(selector, font name), ...]``
    for ``body``, ``body-bold``, ``body-italic`` and ``body-bolditalic``.

    Font matching is approximate: a family with no italic face resolves to its
    regular one, so asking for italic can quietly give you upright text. This
    makes that visible - two selectors reporting the same name means the host
    has no distinct face for one of them::

        pyplotrs.resolved_font_variants()
        # [('body', 'ArialMT'), ('body-bold', 'Arial-BoldMT'), ...]
    """
    return _core.resolved_font_variants()


__all__ = [
    "__version__",
    "Axes", "Axes3D", "Figure", "GridSpec", "Mappable", "PolarAxes",
    "subplots", "subplot_mosaic", "figure",
    "colormaps", "Colormap", "get_cmap", "palettes", "color",
    "themes", "Theme", "norms", "scales", "ticker",
    "Animation", "animate",
    "set_font_family", "get_font_family", "resolved_font_name",
    "resolved_font_variants",
    "set_unicode_minus", "get_unicode_minus",
]
