from . import _pyplotrs_core as _core
from . import color
from . import colormaps
from . import norms
from . import palettes
from . import scales
from . import ticker
from . import theme as themes
from .animation import Animation, animate
from .colormaps import Colormap, get_cmap
from .figure import Axes, Axes3D, Figure, GridSpec, PolarAxes, subplots, subplot_mosaic
from .theme import Theme


def figure(figsize: tuple[float, float] = (480, 360), *, theme=None,
           units: str = "pt") -> Figure:
    """Create an empty :class:`Figure` (no axes). Use
    :meth:`Figure.add_gridspec` + :meth:`Figure.add_subplot` to place spanning
    axes, or :func:`subplots` / :func:`subplot_mosaic` for the common cases."""
    fig = Figure(figsize=figsize, nrows=1, ncols=1, theme=theme, units=units)
    fig.axes = []
    fig._spans = []
    return fig


def set_font_family(*families) -> None:
    """Set the preferred sans-serif family names for body text, tried in order.

    pyplotrs' analogue of matplotlib's ``rcParams["font.sans-serif"]``. The
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


def resolved_font_name() -> str:
    """The family name body text actually resolves to on this host right now
    (e.g. ``"Arial"`` if installed, otherwise ``"Liberation Sans"``)."""
    return _core.resolved_font_name()


__all__ = [
    "Axes", "Axes3D", "Figure", "GridSpec", "PolarAxes", "subplots", "subplot_mosaic", "figure",
    "colormaps", "Colormap", "get_cmap", "palettes", "color",
    "themes", "Theme", "norms", "scales", "ticker",
    "Animation", "animate",
    "set_font_family", "get_font_family", "resolved_font_name",
]
