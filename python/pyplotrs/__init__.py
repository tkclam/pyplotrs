"""pyplotrs: fast, publication-quality figures, with a Rust rendering core.

    import pyplotrs as pp

    fig, ax = pp.subplots()
    ax.line([0, 1, 2, 3], [0, 1, 4, 9], label="$y = x^2$")
    ax.set(title="Hello", xlabel="x", ylabel="y")
    ax.legend()
    fig.save("hello.pdf")  # vector, with real selectable text

Every figure is an explicit object: there is no current-figure state. The
default style comes from the theme (see `set_theme`).
"""

from importlib.metadata import PackageNotFoundError, version

from . import colormaps, colors, norms, scales, ticker
from . import theme as themes
from ._canvas import MathTextWarning
from .animation import Animation, animate
from .artists import Artist
from .axes import Axes
from .colormaps import Colormap
from .figure import Figure, figure, subplot_mosaic, subplots
from .text import Span, bold, italic, mark, plain, rich, strike, underline
from .theme import Theme, get_theme, set_theme

try:
    __version__ = version("pyplotrs")
except PackageNotFoundError:  # pragma: no cover - source tree without metadata
    __version__ = "0.0.0"

__all__ = [
    "Animation",
    "Artist",
    "Axes",
    "Colormap",
    "Figure",
    "MathTextWarning",
    "Span",
    "Theme",
    "__version__",
    "animate",
    "bold",
    "colormaps",
    "colors",
    "figure",
    "get_theme",
    "italic",
    "mark",
    "norms",
    "plain",
    "rich",
    "scales",
    "set_theme",
    "strike",
    "subplot_mosaic",
    "subplots",
    "themes",
    "ticker",
    "underline",
]
