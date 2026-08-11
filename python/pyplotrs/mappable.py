"""The handle a colormapped mark hands back.

Its own module rather than a corner of `axes.py` for two reasons: it is public
API - it appears in the signature of `Figure.colorbar` and is the return type of
six `Axes` methods - and `axes.py` is under a hard line cap precisely so that
the 2D mark surface does not quietly reabsorb everything around it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # a type-only import, so `axes -> mappable` stays acyclic
    from .axes import Axes

__all__ = ["Mappable"]


class Mappable:
    """The colormapped-mark handle that ``Figure.colorbar`` takes.

    Returned by every mark that maps values through a colormap -
    ``Axes.imshow``, ``Axes.scatter`` with ``c=``,
    ``Axes.pcolormesh``, ``Axes.hexbin``, ``Axes.hist2d``,
    ``Axes.contourf`` - and carrying the colormap and value range the
    colorbar needs to draw a matching scale::

        im = ax.imshow(field, cmap="magma")
        fig.colorbar(im, label="intensity")

    You rarely construct one; you hold the value a mark hands back and pass it
    on. It is named in the signature of a public method, so it is public
    itself: it was spelled ``_Mappable`` until 0.1.0, which made
    ``Figure.colorbar``'s own annotation refer to a name no importer could
    resolve.
    """

    def __repr__(self) -> str:
        return (f"<Mappable cmap={self.cmap.name!r} "
                f"vmin={self.vmin:g} vmax={self.vmax:g}>")

    def __init__(self, ax: "Axes", cmap, vmin: float, vmax: float, norm=None) -> None:
        self.ax = ax
        self.cmap = cmap
        self.vmin = vmin
        self.vmax = vmax
        self.norm = norm  # None => linear; else a pyplotrs.norms.Normalize
