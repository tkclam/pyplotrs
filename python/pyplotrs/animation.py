"""pyplotrs.animation: multi-frame / animated export.

pyplotrs has no global "current figure" state, so an animation is just a *render
callback* that returns a fully-built [`pyplotrs.Figure`][pyplotrs.Figure] for each frame. The
frames are rasterized and encoded to an animated **GIF** (broadly viewable,
256-color per frame) or **APNG** (full 8-bit color, higher fidelity), chosen
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

In a notebook, a bare ``animation`` in a cell plays inline, the way a bare
``fig`` renders as a PNG; [`Animation.to_bytes`][pyplotrs.animation.Animation.to_bytes]
returns the encoded animation when the destination is not a file.
"""

from __future__ import annotations

import os
from typing import Callable, Iterable, Optional, Union

from . import _pyplotrs_core as _core
from ._const import _INLINE_ANIM_DPI
from ._figure import Figure

#: Extensions [`Animation.save`][pyplotrs.animation.Animation.save] accepts, and
#: the encoder each selects. ``.png`` maps to APNG because a multi-frame PNG
#: *is* an APNG; a viewer that does not know the format shows frame 0.
_FORMATS = {"gif": "gif", "apng": "apng", "png": "apng"}

#: Ceiling (bytes) on an animation rendered for inline notebook display. An
#: animation costs its frame count times a still figure, base64-encoded into the
#: `.ipynb`, so an incautious `dpi` can write tens of megabytes into a file meant
#: to be committed. matplotlib caps the same way (`animation.embed_limit`) but
#: logs a warning and silently drops the remaining frames, which yields a
#: truncated animation and no exception; this raises instead.
_INLINE_MAX_BYTES = 20 * 1024 * 1024


class Animation:
    """A sequence of figures encoded as an animated image.

    Parameters
    ----------
    render:
        Called once per frame as ``render(value)``; must return a
        [`pyplotrs.Figure`][pyplotrs.Figure].
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

    def to_bytes(self, format: str = "gif", *, dpi: float = 100.0,
                 fps: Optional[float] = None) -> bytes:
        """Render every frame and return the encoded animation.

        ``format`` is ``"gif"`` (256-color, plays anywhere) or ``"apng"``
        (full 8-bit color); a leading dot and any capitalization are accepted,
        so a file extension can be handed straight through. ``dpi`` sets the
        raster resolution and ``fps`` overrides the construction-time frame
        rate, both as in [`save`][pyplotrs.animation.Animation.save].

        This is the primitive [`save`][pyplotrs.animation.Animation.save] is
        built on. Reach for it when the destination is not a path - an HTTP
        response, a zip member, a ``BytesIO`` - and use ``save`` otherwise,
        since it does not hold the encoded animation and the file at once.
        """
        rate = self.fps if fps is None else float(fps)
        if rate <= 0:
            raise ValueError("fps must be positive")
        key = format.lstrip(".").lower()
        try:
            encoder = _FORMATS[key]
        except KeyError:
            raise ValueError(
                f"unsupported animation format {format!r}; "
                f"use {' or '.join(sorted(set(_FORMATS.values())))}") from None
        scenes = self._scenes()
        if encoder == "gif":
            delay_cs = max(1, round(100.0 / rate))  # GIF delay unit is 10 ms
            return _core.scenes_to_gif(scenes, dpi / 72.0, delay_cs, self.repeat)
        delay_num = max(1, round(1000.0 / rate))  # delay = num/1000 s
        return _core.scenes_to_apng(scenes, dpi, delay_num, 1000, self.repeat)

    def save(self, path: Union[str, os.PathLike], *, dpi: float = 100.0,
             fps: Optional[float] = None,
             format: Optional[str] = None) -> None:
        """Render every frame and encode to ``path``.

        The format is taken from the extension: ``.gif`` (256-color, broadly
        viewable) or ``.apng`` / ``.png`` (full-color). ``dpi`` sets the raster
        resolution; ``fps`` overrides the construction-time frame rate;
        ``format`` overrides the extension, for a path that does not carry one.

        ``render`` is called once per frame *per save*, so writing two formats
        from one ``Animation`` builds every figure twice - and a callback that
        draws on random numbers would not even build the same one twice. Encode
        once with [`to_bytes`][pyplotrs.animation.Animation.to_bytes] and write
        the bytes yourself when that matters.
        """
        path_str = str(path)
        if format is None:
            format = path_str.rsplit(".", 1)[-1] if "." in path_str else ""
        with open(path_str, "wb") as fh:
            fh.write(self.to_bytes(format, dpi=dpi, fps=fps))

    def _repr_mimebundle_(self, include=None, exclude=None) -> dict:
        """Rich inline display in Jupyter/IPython: a bare ``anim`` in a notebook
        cell plays as an animated GIF, the way a bare ``fig`` renders as a PNG.

        GIF rather than APNG because ``image/gif`` is the one animated format
        every notebook frontend plays; an APNG would arrive as ``image/png`` and
        show as a still frame wherever the decoder is older than the format.
        APNG is a ``save`` away when the frames need full color.

        Displaying an animation calls ``render`` once per frame, exactly as
        ``save`` does, so a callback with side effects runs again on every echo.
        """
        data = self.to_bytes("gif", dpi=_INLINE_ANIM_DPI)
        if len(data) > _INLINE_MAX_BYTES:
            raise ValueError(
                f"this animation is {len(data) / 1e6:.1f} MB at "
                f"{_INLINE_ANIM_DPI:g} dpi, over the {_INLINE_MAX_BYTES / 1e6:.0f} MB "
                f"inline limit; it has {len(self)} frames. Save it with "
                "`save(...)` and display the file, or use fewer frames.")
        bundle = {"image/gif": data, "text/plain": repr(self)}
        if include:
            bundle = {k: v for k, v in bundle.items() if k in include}
        if exclude:
            bundle = {k: v for k, v in bundle.items() if k not in exclude}
        return bundle

    def __repr__(self) -> str:
        return (f"<Animation {len(self)} frames @ {self.fps:g} fps"
                f"{'' if self.repeat else ', once'}>")


def animate(render: Callable[..., Figure], frames: Union[int, Iterable], *,
            fps: float = 20.0, repeat: bool = True) -> Animation:
    """Convenience constructor for ``Animation`` (see its docstring)."""
    return Animation(render, frames, fps=fps, repeat=repeat)


__all__ = ["Animation", "animate"]
