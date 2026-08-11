# Animation

Because pyplotrs has no global "current figure", an animation is just a **render
callback** that returns a fully-built `Figure` for each frame. The frames are
rasterized and encoded to an animated **GIF** or **APNG**.

```python
--8<-- "examples/animation_wave.py"
```

![traveling wave](../gallery/images/animation_wave.gif){ width="420" }

## How it works

[`animate`][pyplotrs.animation.animate] (or the
[`Animation`][pyplotrs.animation.Animation] class) takes:

- `render` — a callback invoked once per frame as `render(value)`, returning a
  `Figure`;
- `frames` — an `int` (the callback receives `0 … frames-1`) or any iterable of
  values passed through in order;
- `fps` — frames per second (default 20);
- `repeat` — loop forever (default) or play once.

```python
import pyplotrs as plt

def render(i):
    fig, ax = plt.subplots(figsize=(360, 220))
    ax.line(xs, [f(x, i) for x in xs])
    ax.set(ylim=(-1.2, 1.2), title=f"frame {i}")
    return fig

anim = plt.animate(render, frames=60, fps=24)
anim.save("out.gif")     # 256-color, broadly viewable
anim.save("out.apng")    # full 8-bit color, higher fidelity
```

Building a whole figure per frame sounds expensive and is not: a figure is a
list of recorded marks until it is rendered, and the rendering is the same Rust
path a single `save` takes.

## Saving

`save` chooses the encoder from the extension — `.gif`, or `.apng`/`.png` for
APNG; anything else raises `ValueError`. Two options can be overridden at save
time:

```python
anim.save("out.gif", dpi=150, fps=12)
```

`dpi` sets the raster resolution (default 100, lower than `Figure.save`'s 200
because an animation is many frames), and `fps` overrides the rate given at
construction.

Every frame must share the same figure size — the animation canvas is fixed, and
a mismatch raises `ValueError` naming the frame size that differed.

!!! tip "Iterable frames"
    `frames` can be any iterable, so you can drive the animation from data
    rather than from an index:

    ```python
    plt.animate(render, frames=timestamps).save("series.gif")
    ```

!!! note "GIF vs APNG"
    GIF quantizes each frame to at most 256 colors — near-lossless for typical
    plots, which have few distinct colors — and plays anywhere. APNG keeps full
    8-bit-per-channel color and is the better choice for colormapped fields or
    anything with smooth gradients.
