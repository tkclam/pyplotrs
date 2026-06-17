# Animation

Because pyplotrs has no global "current figure", an animation is just a **render
callback** that returns a fully-built `Figure` for each frame. The frames are
rasterized and encoded to an animated **GIF** or **APNG**.

```python
--8<-- "examples/animation_wave.py"
```

![travelling wave](../gallery/images/animation_wave.gif){ width="420" }

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
anim.save("out.gif")     # 256-colour, broadly viewable
anim.save("out.apng")    # full 8-bit colour, higher fidelity
```

Every frame must share the same figure size (the animation canvas is fixed).
`save` chooses the encoder from the extension (`.gif` vs `.apng`/`.png`); `dpi`
sets the raster resolution and `fps` can be overridden at save time.

!!! tip "Iterable frames"
    `frames` can be any iterable, so you can drive the animation from data:

    ```python
    plt.animate(render, frames=timestamps).save("series.gif")
    ```
