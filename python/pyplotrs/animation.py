"""Animations: one figure per frame, encoded as GIF or APNG.

    def frame(i):
        fig, ax = pp.subplots()
        ax.line(x, [math.sin(v + 0.1 * i) for v in x])
        ax.set(ylim=(-1.1, 1.1))
        return fig

    pp.animate(frame, frames=60, fps=24).save("wave.gif")

``render`` is called with each frame index (or each item when ``frames`` is
an iterable). All frames must have the same size. In a notebook an animation
plays inline.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Iterable
from typing import Any

from . import _core
from .figure import Figure

__all__ = ["Animation", "animate"]

_INLINE_DPI = 100.0


class Animation:
    """A sequence of figures, encoded on `save` or `to_bytes`."""

    def __init__(
        self,
        render: Callable[[Any], Figure],
        frames: int | Iterable[Any],
        *,
        fps: float = 20.0,
        repeat: bool = True,
    ) -> None:
        if not callable(render):
            raise TypeError("render must be a function returning a Figure")
        self._items = list(range(frames)) if isinstance(frames, int) else list(frames)
        if not self._items:
            raise ValueError("an animation needs at least one frame")
        if not fps > 0:
            raise ValueError(f"fps must be positive, got {fps!r}")
        self._render, self.fps, self.repeat = render, float(fps), bool(repeat)

    def __len__(self) -> int:
        return len(self._items)

    def _scenes(self) -> list[_core.Scene]:
        scenes, size = [], None
        for item in self._items:
            fig = self._render(item)
            if not isinstance(fig, Figure):
                raise TypeError(f"render() must return a Figure, got {type(fig).__name__}")
            if size is not None and fig.size != size:
                raise ValueError(
                    f"every frame must have the same size; got {fig.size} after {size}"
                )
            size = fig.size
            scenes.append(fig._render().scene)
        return scenes

    def to_bytes(self, format: str = "gif", *, dpi: float = 100.0) -> bytes:
        """The encoded animation: ``"gif"`` (plays anywhere, 256 colors) or
        ``"apng"`` (full color)."""
        fmt = format.lower().lstrip(".")
        if fmt == "gif":
            return _core.render_gif(
                self._scenes(), dpi / 72.0, max(1, round(100 / self.fps)), self.repeat
            )
        if fmt in ("apng", "png"):
            return _core.render_apng(
                self._scenes(), dpi, max(1, round(1000 / self.fps)), 1000, self.repeat
            )
        raise ValueError(f"unknown animation format {format!r}; use 'gif' or 'apng'")

    def save(self, path: str | os.PathLike[str], *, dpi: float = 100.0) -> None:
        """Encode to ``path``; ``.gif`` or ``.apng``/``.png`` picks the format."""
        ext = os.path.splitext(os.fspath(path))[1]
        data = self.to_bytes(ext or "gif", dpi=dpi)
        with open(path, "wb") as f:
            f.write(data)

    def _repr_mimebundle_(self, include: Any = None, exclude: Any = None) -> dict[str, Any]:
        return {"image/gif": self.to_bytes("gif", dpi=_INLINE_DPI), "text/plain": repr(self)}

    def __repr__(self) -> str:
        return f"<Animation {len(self)} frames at {self.fps:g} fps>"


def animate(
    render: Callable[[Any], Figure],
    frames: int | Iterable[Any],
    *,
    fps: float = 20.0,
    repeat: bool = True,
) -> Animation:
    """An `Animation` drawing ``render(i)`` for each frame."""
    return Animation(render, frames, fps=fps, repeat=repeat)
