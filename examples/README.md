# Examples

Each script here is self-contained and runnable, and doubles as the source for a
[documentation gallery](../docs/gallery/index.md) entry. Running a script writes
its figure as a PNG into the current directory:

```bash
python examples/line.py        # writes line.png in your cwd
```

To regenerate every gallery image into `docs/gallery/images/` (what the docs
site displays), run them with that directory as the working directory:

```bash
cd docs/gallery/images
for f in ../../../examples/*.py; do python "$f"; done
```

| Script | Shows |
|---|---|
| `line.py` | Line plot with multiple series and a legend |
| `scatter.py` | Scatter plot with marker styling |
| `bar.py` | Vertical bar chart |
| `histogram.py` | Histogram with density normalization |
| `fill_between.py` | Filled confidence band around a line |
| `errorbar.py` | Error bars with caps |
| `polar.py` | Polar projection: line + scatter with a legend |
| `heatmap.py` | `imshow` image with a colorbar |
| `colormaps.py` | Reference strip of the built-in colormaps |
| `surface3d.py` | 3D colormapped surface |
| `scatter3d.py` | 3D scatter cloud |
| `line3d.py` | 3D parametric curve |
| `themes.py` | The same plot in each built-in theme |
| `subplots.py` | Shared-axis small multiples + figure legend |
| `math_labels.py` | LaTeX `$...$` math in titles/labels/legend |
| `annotations.py` | Text and callout-arrow annotations |
| `animation_wave.py` | Animated GIF (traveling wave) |
