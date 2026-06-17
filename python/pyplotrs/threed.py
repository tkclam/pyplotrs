"""3D camera and projection helpers.

pyplotrs' 3D support is a *projection layer*, not a separate renderer: an
orthographic camera turns 3D primitives into ordinary 2D paths/text (with
painter's-algorithm depth sorting), which then flow through the same Scene IR
and the same PDF/SVG/raster backends as everything else. From the renderer's
point of view a 3D axes is indistinguishable from a 2D one.

The camera is a simple orthonormal eye basis derived from ``elev``/``azim``
(matching matplotlib's mplot3d angle convention). ``view`` returns screen
``(x, y)`` plus an eye-space depth used only for back-to-front sorting.
"""

from __future__ import annotations

import math

Vec3 = tuple[float, float, float]


def sub(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def dot(a: Vec3, b: Vec3) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def cross(a: Vec3, b: Vec3) -> Vec3:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def normalize(v: Vec3) -> Vec3:
    n = math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])
    if n < 1e-12:
        return (0.0, 0.0, 0.0)
    return (v[0] / n, v[1] / n, v[2] / n)


class Camera3D:
    """An orthographic camera looking at the origin from ``(elev, azim)``.

    ``elev`` is the angle above the x-y plane and ``azim`` the rotation about
    the vertical (z) axis, both in degrees. ``view(p)`` projects a world point
    to ``(screen_x, screen_y, depth)`` where larger ``depth`` is nearer the
    camera (so back-to-front order is ascending depth).
    """

    def __init__(self, elev: float = 30.0, azim: float = -60.0) -> None:
        self.elev = elev
        self.azim = azim
        e = math.radians(elev)
        a = math.radians(azim)
        # Unit vector from the origin toward the camera.
        self.dir = normalize((math.cos(e) * math.cos(a), math.cos(e) * math.sin(a), math.sin(e)))
        world_up: Vec3 = (0.0, 0.0, 1.0)
        right = cross(world_up, self.dir)
        if right[0] ** 2 + right[1] ** 2 + right[2] ** 2 < 1e-12:
            right = (1.0, 0.0, 0.0)  # looking straight down/up: pick an arbitrary right
        self.right = normalize(right)
        self.up = cross(self.dir, self.right)  # already unit (orthonormal basis)

    def view(self, p: Vec3) -> tuple[float, float, float]:
        return (dot(p, self.right), dot(p, self.up), dot(p, self.dir))


# The 8 corners of the normalized unit cube [-0.5, 0.5]^3.
CUBE_CORNERS: list[Vec3] = [
    (sx, sy, sz)
    for sx in (-0.5, 0.5)
    for sy in (-0.5, 0.5)
    for sz in (-0.5, 0.5)
]
