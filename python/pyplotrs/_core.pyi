# Stub for the compiled extension (crates/python). Keep in step with it.

from collections.abc import Sequence
from typing import Literal

from typing_extensions import Buffer

_RGBA = tuple[int, int, int, int]
_Floats = Sequence[float] | Buffer
_Bytes = bytes | bytearray | Buffer
_Cap = Literal["butt", "round", "square"]
_Join = Literal["miter", "round", "bevel"]

class Transform:
    def __init__(
        self,
        ax: float = 1.0,
        bx: float = 0.0,
        ay: float = 1.0,
        by: float = 0.0,
        xscale: str = "linear",
        yscale: str = "linear",
    ) -> None: ...
    def x(self, x: float) -> float: ...
    def y(self, y: float) -> float: ...

class Scene:
    def __init__(
        self,
        width: float,
        height: float,
        font_family: Sequence[str] = ...,
        math_fontset: Literal["sans", "stix"] = "sans",
    ) -> None: ...
    def path(
        self,
        xs: _Floats,
        ys: _Floats,
        tf: Transform | None = None,
        *,
        stroke: _RGBA | None = None,
        width: float = 1.0,
        fill: _RGBA | None = None,
        close: bool = False,
        dash: Sequence[float] | None = None,
        cap: _Cap = "butt",
        join: _Join = "round",
        simplify: float | None = None,
    ) -> None: ...
    def segments(
        self,
        x0: _Floats,
        y0: _Floats,
        x1: _Floats,
        y1: _Floats,
        tf: Transform | None = None,
        *,
        color: _RGBA,
        width: float = 1.0,
        dash: Sequence[float] | None = None,
        cap: _Cap = "butt",
    ) -> None: ...
    def rects(
        self,
        x0: _Floats,
        y0: _Floats,
        x1: _Floats,
        y1: _Floats,
        tf: Transform | None = None,
        *,
        fill: _RGBA | None = None,
        fills: _Bytes | None = None,
        stroke: _RGBA | None = None,
        width: float = 1.0,
    ) -> None: ...
    def polygons(
        self,
        xs: _Floats,
        ys: _Floats,
        counts: Sequence[int],
        tf: Transform | None = None,
        *,
        fill: _RGBA | None = None,
        fills: _Bytes | None = None,
        stroke: _RGBA | None = None,
        width: float = 1.0,
    ) -> None: ...
    def band(
        self,
        seq: _Floats,
        lo: _Floats,
        hi: _Floats,
        tf: Transform | None = None,
        *,
        fill: _RGBA,
        swap: bool = False,
    ) -> None: ...
    def markers(
        self,
        xs: _Floats,
        ys: _Floats,
        tf: Transform | None = None,
        *,
        marker: str = "o",
        size: float = 5.0,
        fill: _RGBA | None = None,
        fills: _Bytes | None = None,
        edge: _RGBA | None = None,
        edge_width: float = 1.0,
    ) -> None: ...
    def image(
        self,
        rgba: _Bytes,
        width: int,
        height: int,
        x: float,
        y: float,
        w: float,
        h: float,
        *,
        flip_x: bool = False,
        flip_y: bool = False,
    ) -> None: ...
    def colormapped_image(
        self,
        values: _Floats,
        width: int,
        height: int,
        lut: _Bytes,
        vmin: float,
        vmax: float,
        x: float,
        y: float,
        w: float,
        h: float,
        *,
        norm: str = "linear",
        origin_upper: bool = True,
        flip_x: bool = False,
    ) -> None: ...
    def text(
        self,
        x: float,
        y: float,
        s: str,
        size: float,
        color: _RGBA,
        *,
        bold: bool = False,
        italic: bool = False,
    ) -> None: ...
    def measure(
        self, s: str, size: float, *, bold: bool = False, italic: bool = False
    ) -> tuple[float, float, float]: ...
    def font_metrics(
        self, size: float, *, bold: bool = False, italic: bool = False
    ) -> tuple[float, float, float, float, float, float]: ...
    def unknown_commands(self, s: str, size: float) -> list[str]: ...
    def missing_glyphs(self, s: str) -> list[str]: ...
    def font_faces(self) -> list[tuple[str, str]]: ...
    def font_data(self) -> bytes: ...
    def begin_group(
        self,
        transform: tuple[float, float, float, float, float, float] = ...,
        *,
        clip: tuple[float, float, float, float] | None = None,
        clip_circle: tuple[float, float, float] | None = None,
        clip_path: tuple[_Floats, _Floats] | None = None,
        opacity: float = 1.0,
    ) -> None: ...
    def end_group(self) -> None: ...
    def to_pdf(
        self,
        *,
        dpi: float = 200.0,
        tagged: bool = False,
        title: str | None = None,
        alt: str | None = None,
    ) -> bytes: ...
    def to_svg(self, *, dpi: float = 200.0) -> str: ...
    def to_png(self, *, dpi: float = 200.0, transparent: bool = False) -> bytes: ...

def finite_range(values: _Floats, scale: str = "linear") -> tuple[float, float] | None: ...
def offset_range(
    values: _Floats, offsets: _Floats, two_sided: bool = True
) -> tuple[float, float] | None: ...
def histogram(
    values: _Floats, bins: int, range: tuple[float, float] | None = None, density: bool = False
) -> tuple[list[float], list[float]]: ...
def hist2d(
    xs: _Floats, ys: _Floats, nx: int, ny: int, xlo: float, xhi: float, ylo: float, yhi: float
) -> list[float]: ...
def gaussian_kde(samples: _Floats, grid: _Floats, bandwidth: float) -> list[float]: ...
def hexbin(
    xs: _Floats, ys: _Floats, gridsize: int, xlo: float, xhi: float, ylo: float, yhi: float
) -> tuple[list[tuple[float, float, float]], float, float]: ...
def contour_lines(
    values: _Floats, w: int, h: int, levels: _Floats
) -> list[tuple[int, bool, list[tuple[float, float]]]]: ...
def contourf_image(
    values: _Floats, w: int, h: int, edges: _Floats, band_lut: _Bytes, upsample: int
) -> tuple[bytes, int, int]: ...
def map_colors(
    values: _Floats, lut: _Bytes, vmin: float, vmax: float, norm: str = "linear"
) -> bytes: ...
def colormap_table(name: str) -> bytes | None: ...
def colormap_from_stops(
    stops: Sequence[tuple[float, tuple[int, int, int]]], space: str
) -> bytes: ...
def palette(name: str) -> list[tuple[int, int, int]] | None: ...
def colormap_names(category: str | None = None) -> list[str]: ...
def palette_names() -> list[str]: ...
def project3d(
    xs: _Floats, ys: _Floats, zs: _Floats, elev: float, azim: float, frame: tuple[float, ...]
) -> tuple[list[float], list[float], list[float]]: ...
def cube_bounds(elev: float, azim: float) -> tuple[float, float, float, float]: ...
def render_gif(
    scenes: Sequence[Scene], scale: float, delay_cs: int, loop_forever: bool = True
) -> bytes: ...
def render_apng(
    scenes: Sequence[Scene], dpi: float, delay_num: int, delay_den: int, loop_forever: bool = True
) -> bytes: ...
