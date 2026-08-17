# Gallery

A tour of what pyplotrs can draw. Every entry below is a **complete, runnable
script** — copy it, run it, and you get the figure shown. (Scripts live in
[`examples/`](https://github.com/tkclam/pyplotrs/tree/main/examples) and save a
PNG into the current directory.)

<div class="grid cards" markdown>

- [![line](images/line.png)](#line-plot) **Line**
- [![scatter](images/scatter.png)](#scatter) **Scatter**
- [![bar](images/bar.png)](#bar-chart) **Bar**
- [![histogram](images/histogram.png)](#histogram) **Histogram**
- [![statistical](images/statistical.png)](#box-violin-and-pie) **Box / violin / pie**
- [![fill](images/fill_between.png)](#fill-between) **Fill between**
- [![errorbar](images/errorbar.png)](#error-bars) **Error bars**
- [![heatmap](images/heatmap.png)](#heatmap) **Heatmap**
- [![fields](images/fields.png)](#vector-and-matrix-fields) **Fields**
- [![colormaps](images/colormaps.png)](#colormaps) **Colormaps**
- [![polar](images/polar.png)](#polar) **Polar**
- [![surface](images/surface3d.png)](#3d-surface) **3D surface**
- [![scatter3d](images/scatter3d.png)](#3d-scatter) **3D scatter**
- [![line3d](images/line3d.png)](#3d-line) **3D line**
- [![subplots](images/subplots.png)](#subplots) **Subplots**
- [![layout](images/layout.png)](#mosaic-twin-axis-and-inset) **Mosaic & insets**
- [![scales](images/scales.png)](#axis-scales) **Axis scales**
- [![math](images/math_labels.png)](#latex-math) **LaTeX math**
- [![annotations](images/annotations.png)](#annotations) **Annotations**
- [![anim](images/animation_wave.gif)](#animation) **Animation**

</div>

---

## Basic plots

### Line plot

![line](images/line.png){ width="340" }

```python
--8<-- "examples/line.py"
```

### Scatter

![scatter](images/scatter.png){ width="340" }

```python
--8<-- "examples/scatter.py"
```

### Bar chart

![bar](images/bar.png){ width="340" }

```python
--8<-- "examples/bar.py"
```

---

## Distributions

### Histogram

![histogram](images/histogram.png){ width="340" }

```python
--8<-- "examples/histogram.py"
```

### Box, violin and pie

![box, violin and pie](images/statistical.png){ width="660" }

```python
--8<-- "examples/statistical.py"
```

### Fill between

![fill between](images/fill_between.png){ width="340" }

```python
--8<-- "examples/fill_between.py"
```

### Error bars

![error bars](images/errorbar.png){ width="340" }

```python
--8<-- "examples/errorbar.py"
```

---

## Images & colormaps

### Heatmap

![heatmap](images/heatmap.png){ width="340" }

```python
--8<-- "examples/heatmap.py"
```

### Vector and matrix fields

![fields](images/fields.png){ width="640" }

```python
--8<-- "examples/fields.py"
```

### Colormaps

![colormaps](images/colormaps.png){ width="500" }

```python
--8<-- "examples/colormaps.py"
```

---

## Polar

### Polar

![polar](images/polar.png){ width="380" }

```python
--8<-- "examples/polar.py"
```

---

## 3D

### 3D surface

![3D surface](images/surface3d.png){ width="500" }

```python
--8<-- "examples/surface3d.py"
```

### 3D scatter

![3D scatter](images/scatter3d.png){ width="500" }

```python
--8<-- "examples/scatter3d.py"
```

### 3D line

![3D line](images/line3d.png){ width="500" }

```python
--8<-- "examples/line3d.py"
```

---

## Layout & styling

### Subplots

![subplots](images/subplots.png){ width="640" }

```python
--8<-- "examples/subplots.py"
```

### Mosaic, twin axis and inset

![layout](images/layout.png){ width="560" }

```python
--8<-- "examples/layout.py"
```

### Axis scales

![scales](images/scales.png){ width="620" }

```python
--8<-- "examples/scales.py"
```

### Themes

<div class="grid" markdown>
![default](images/theme_default.png)
![grayscale](images/theme_grayscale.png)
![dark](images/theme_dark.png)
</div>

```python
--8<-- "examples/themes.py"
```

---

## Math & annotations

### LaTeX math

![math](images/math_labels.png){ width="340" }

```python
--8<-- "examples/math_labels.py"
```

### Annotations

![annotations](images/annotations.png){ width="340" }

```python
--8<-- "examples/annotations.py"
```

---

## Animation

### Animation

![traveling wave](images/animation_wave.gif){ width="420" }

```python
--8<-- "examples/animation_wave.py"
```
