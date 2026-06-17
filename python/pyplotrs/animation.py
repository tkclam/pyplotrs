"""pyplotrs.animation: multi-frame / animated export.

pyplotrs has no global "current figure" state, so an animation is just a *render
callback* that returns a fully-built :class:`pyplotrs.Figure` for each frame. The
frames are rasterized and encoded to an animated **GIF** (broadly viewable,
256-colour per frame) or **APNG** (full 8-bit colour, higher fidelity), chosen
by the output file extension::

    import pyplotrs, math

    xs = [i * 0.1 for i in range(100)]

    def frame(i):
        fig, ax = pyplotrs.subplots(figsize=(360, 216))
        ax.line(xs, [math.sin(x + i * 0.15) for x in xs])
        ax.set(ylim=(-1.1, 1.1), title=f"t = {i}")
        return fig

    pyplotrs.animate(frame, frames=60, fps=24).save("wave.gif")

The callback is invoked once per frame with the frame *value* - an ``int`` index
when ``frames`` is an ``int``, otherwise each item of the iterable. Every
returned figure must share the same size (the animation canvas is fixed).
"""

from __future__ import annotations

from typing import Callable, Iterable, Optional, Union

from . import _pyplotrs_core as _core
from .figure import Figure


class Animation:
    """A sequence of figures encoded as an animated image.

    Parameters
    ----------
    render:
        Called once per frame as ``render(value)``; must return a
        :class:`pyplotrs.Figure`.
    frames:
        Either an ``int`` (the callback receives ``0 .. frames-1``) or an
        iterable of values passed to the callback in order.
    fps:
        Frames per second (default 20).
    repeat:
        Loop forever (default) or play through once.
    """

    def __init__(self, render: Callable[..., Figure],
                 frames: Union[int, Iterable], *,
                 fps: float = 20.0, repeat: bool = True) -> None:
        if not callable(render):
            raise TypeError("render must be callable: render(value) -> pyplotrs.Figure")
        if isinstance(frames, int):
            if frames <= 0:
                raise ValueError("frames must be a positive int")
            self._items: list = list(range(frames))
        else:
            self._items = list(frames)
            if not self._items:
                raise ValueError("frames iterable is empty")
        self._render = render
        self.fps = float(fps)
        if self.fps <= 0:
            raise ValueError("fps must be positive")
        self.repeat = bool(repeat)

    def __len__(self) -> int:
        return len(self._items)

    def _scenes(self) -> list:
        """Build every frame's figure and collect its Scene, enforcing a
        consistent canvas size."""
        scenes = []
        size = None
        for item in self._items:
            fig = self._render(item)
            if not (hasattr(fig, "_build_scene") and hasattr(fig, "size_pt")):
                raise TypeError(
                    "render(value) must return a pyplotrs.Figure, got "
                    f"{type(fig).__name__}")
            if size is None:
                size = tuple(fig.size_pt)
            elif tuple(fig.size_pt) != size:
                raise ValueError(
                    "every animation frame must have the same size; got "
                    f"{tuple(fig.size_pt)} after {size}")
            scenes.append(fig._build_scene())
        return scenes

    def save(self, path: str, *, dpi: float = 100.0,
             fps: Optional[float] = None) -> None:
        """Render every frame and encode to ``path``.

        The format is taken from the extension: ``.gif`` (256-colour, broadly
        viewable) or ``.apng`` / ``.png`` (full-colour). ``dpi`` sets the raster
        resolution; ``fps`` overrides the construction-time frame rate.
        """
        rate = self.fps if fps is None else float(fps)
        if rate <= 0:
            raise ValueError("fps must be positive")
        ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
        scenes = self._scenes()
        if ext == "gif":
            delay_cs = max(1, round(100.0 / rate))  # GIF delay unit is 10 ms
            data = _core.scenes_to_gif(scenes, dpi / 72.0, delay_cs, self.repeat)
        elif ext in ("apng", "png"):
            delay_num = max(1, round(1000.0 / rate))  # delay = num/1000 s
            data = _core.scenes_to_apng(scenes, dpi, delay_num, 1000, self.repeat)
        else:
            raise ValueError(
                f"unsupported animation format {ext!r}; use .gif or .apng")
        with open(path, "wb") as fh:
            fh.write(data)


def animate(render: Callable[..., Figure], frames: Union[int, Iterable], *,
            fps: float = 20.0, repeat: bool = True) -> Animation:
    """Convenience constructor for :class:`Animation` (see its docstring)."""
    return Animation(render, frames, fps=fps, repeat=repeat)


__all__ = ["Animation", "animate"]
