"""Type stubs for the compiled `_pyplotrs_core` extension module."""

from typing import Literal

_RGBA = tuple[int, int, int, int]

class Scene:
    def __init__(self, width: float, height: float) -> None: ...
    def add_path(
        self,
        points: list[tuple[float, float]],
        stroke_color: _RGBA | None = None,
        stroke_width: float = 1.0,
        fill_color: _RGBA | None = None,
        close: bool = False,
        dash: list[float] | None = None,
        cap: Literal["butt", "round", "square"] = "butt",
        join: Literal["miter", "round", "bevel"] = "round",
        fill_rule: Literal["nonzero", "evenodd"] = "nonzero",
    ) -> None: ...
    def add_line_xform(
        self,
        xs: list[float],
        ys: list[float],
        ax: float,
        bx: float,
        ay: float,
        by: float,
        stroke_color: _RGBA,
        stroke_width: float = 1.0,
        dash: list[float] | None = None,
        cap: Literal["butt", "round", "square"] = "round",
        join: Literal["miter", "round", "bevel"] = "round",
        simplify: bool = True,
        simplify_threshold: float = 0.1,
        x_scale: str = "linear",
        y_scale: str = "linear",
    ) -> None: ...
    def add_markers_xform(
        self,
        xs: list[float],
        ys: list[float],
        ax: float,
        bx: float,
        ay: float,
        by: float,
        marker: str,
        diameter: float,
        fill_color: _RGBA,
        edge_color: _RGBA | None = None,
        edge_width: float = 1.0,
        x_scale: str = "linear",
        y_scale: str = "linear",
    ) -> None: ...
    def add_markers_xform_colored(
        self,
        xs: list[float],
        ys: list[float],
        ax: float,
        bx: float,
        ay: float,
        by: float,
        marker: str,
        diameter: float,
        colors: list[_RGBA],
        edge_color: _RGBA | None = None,
        edge_width: float = 1.0,
        x_scale: str = "linear",
        y_scale: str = "linear",
    ) -> None: ...
    def add_colormapped_image(
        self,
        values: list[float],
        width: int,
        height: int,
        vmin: float,
        vmax: float,
        lut: bytes | list[int],
        origin_upper: bool,
        x: float,
        y: float,
        w: float,
        h: float,
        norm: str = "linear",
    ) -> None: ...
    def add_text(
        self,
        x: float,
        y: float,
        text: str,
        size: float,
        color: _RGBA = (0, 0, 0, 255),
        font: Literal["body", "math"] = "body",
    ) -> None: ...
    def add_math(
        self,
        x: float,
        y: float,
        text: str,
        size: float,
        color: _RGBA = (0, 0, 0, 255),
    ) -> None: ...
    def measure_math(self, text: str, size: float) -> tuple[float, float, float]: ...
    def add_image(
        self,
        rgba: bytes | list[int],
        width: int,
        height: int,
        x: float,
        y: float,
        w: float,
        h: float,
    ) -> None: ...
    def begin_group(
        self,
        a: float,
        b: float,
        c: float,
        d: float,
        e: float,
        f: float,
        clip: tuple[float, float, float, float] | None = None,
        opacity: float = 1.0,
    ) -> None: ...
    def end_group(self) -> None: ...
    def measure_text(
        self, text: str, size: float, font: Literal["body", "math"] = "body"
    ) -> float: ...
    def font_vmetrics(
        self, size: float, font: Literal["body", "math"] = "body"
    ) -> tuple[float, float, float]: ...
    def to_pdf(
        self, tagged: bool = False, title: str | None = None, alt: str | None = None
    ) -> bytes: ...
    def to_svg(self) -> str: ...
    def to_png(self, dpi: float = 200.0) -> bytes: ...

class Rect:
    x: float
    y: float
    w: float
    h: float
    @property
    def x1(self) -> float: ...
    @property
    def y1(self) -> float: ...

class AxesLayout:
    cell: Rect
    plot: Rect
    title: Rect
    xlabel: Rect
    ylabel: Rect
    x_tick: Rect
    y_tick: Rect
    cbar: Rect

class Layout:
    axes: list[AxesLayout]
    suptitle: Rect
    legend: Rect

def scenes_to_gif(
    scenes: list[Scene], scale: float, delay_cs: int, infinite: bool = True
) -> bytes: ...
def scenes_to_apng(
    scenes: list[Scene],
    dpi: float,
    delay_num: int,
    delay_den: int,
    infinite: bool = True,
) -> bytes: ...
def nice_ticks(vmin: float, vmax: float, max_ticks: int = 7) -> list[tuple[float, str]]: ...
def contour_lines(
    values: list[float], w: int, h: int, levels: list[float]
) -> list[tuple[int, float, float, float, float]]: ...
def contourf_image(
    values: list[float], w: int, h: int, edges: list[float],
    band_lut: bytes | list[int], upsample: int,
) -> tuple[bytes, int, int]: ...
def hist2d(
    xs: list[float], ys: list[float], nx: int, ny: int,
    xlo: float, xhi: float, ylo: float, yhi: float,
) -> list[float]: ...
def gaussian_kde(
    samples: list[float], grid: list[float], bandwidth: float
) -> list[float]: ...
def hexbin(
    xs: list[float], ys: list[float], gridsize: int,
    xlo: float, xhi: float, ylo: float, yhi: float,
) -> list[tuple[float, float, float]]: ...
def solve_layout(
    width: float,
    height: float,
    nrows: int,
    ncols: int,
    cells: list[tuple[float, float, float, float, float, float]],
    outer_margin: float = 5.0,
    hspace: float = 0.0,
    wspace: float = 0.0,
    suptitle_h: float = 0.0,
    legend_w: float = 0.0,
    spans: list[tuple[int, int, int, int]] | None = None,
) -> Layout: ...
