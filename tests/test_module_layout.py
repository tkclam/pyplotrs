"""The shape of the package.

`figure.py` had grown to 5,300 lines and 65% of all Python in the project -
every helper, all three axes classes and the Figure itself in one file. It was
the weakest of the five project goals and the one thing "clean codebase" kept
pointing at.

The split is a pure refactor: it was gated on 78 rendered artifacts (PDF/SVG/PNG
across 26 figures covering every mark type, both colorbar orientations, 3D and
polar) coming out **byte-identical**. These tests pin the resulting structure so
it does not silently collapse back.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

PKG = pathlib.Path(__file__).resolve().parent.parent / "python" / "pyplotrs"

#: No module in the drawing layer should get near the old figure.py again.
#: `axes.py` is the legitimately large one - it is the whole 2D mark surface -
#: and is capped well below where figure.py was.
SIZE_CAP = {"axes.py": 3200}
DEFAULT_CAP = 1200


def _modules():
    return sorted(p for p in PKG.glob("*.py") if p.name != "__init__.py")


@pytest.mark.parametrize("path", _modules(), ids=lambda p: p.name)
def test_no_module_is_a_god_module(path):
    n = len(path.read_text().splitlines())
    cap = SIZE_CAP.get(path.name, DEFAULT_CAP)
    assert n <= cap, f"{path.name} is {n} lines (cap {cap})"


def test_figure_module_only_orchestrates():
    """`figure.py` should hold the Figure, the grid helpers and nothing else -
    no axes classes, no drawing primitives."""
    tree = ast.parse((PKG / "figure.py").read_text())
    defined = {n.name for n in tree.body
               if isinstance(n, (ast.ClassDef, ast.FunctionDef))}
    assert "Figure" in defined
    for leaked in ("Axes", "Axes3D", "PolarAxes", "_AxesBase", "_draw_marker",
                   "_to_f64", "_measure_legend"):
        assert leaked not in defined, f"{leaked} moved back into figure.py"


@pytest.mark.parametrize("name,module", [
    ("Axes", "axes"), ("Axes3D", "axes3d"), ("PolarAxes", "polar"),
    ("Figure", "figure"), ("GridSpec", "figure"),
])
def test_public_classes_live_in_their_own_module(name, module):
    mod = __import__(f"pyplotrs.{module}", fromlist=[name])
    assert hasattr(mod, name)


def test_public_api_is_reachable_from_the_package_root():
    import pyplotrs
    for name in pyplotrs.__all__:
        assert hasattr(pyplotrs, name), f"{name} is in __all__ but missing"


def test_the_layering_has_no_cycles():
    """`_const` -> `_util` -> `_draw` -> `_layout` -> axes kinds -> `figure`.
    A cycle here is what makes a god module feel unavoidable."""
    layer = {"_const": 0, "_util": 1, "_draw": 2, "_layout": 2,
             "axes": 3, "axes3d": 4, "polar": 4, "figure": 5}
    for name, rank in layer.items():
        tree = ast.parse((PKG / f"{name}.py").read_text())
        for node in tree.body:
            if not isinstance(node, ast.ImportFrom) or node.level != 1:
                continue
            dep = node.module
            if dep in layer:
                assert layer[dep] < rank or (layer[dep] == rank and dep == name), (
                    f"{name}.py imports {dep}.py, which is not below it"
                )


#: The drawing layer, in dependency order. Modules *above* figure.py (e.g.
#: `animation`, which composes figures into a GIF) are consumers and may of
#: course import it; these may not.
_BELOW_FIGURE = ["_const", "_util", "_draw", "_layout", "axes", "axes3d", "polar"]


@pytest.mark.parametrize("name", _BELOW_FIGURE)
def test_the_drawing_layer_never_imports_figure(name):
    """Nothing under the Figure may depend on it - that back-edge is what turns
    a layered package back into one file. The axes classes reach their figure
    through a duck-typed `_figure` attribute set by `Figure._adopt`, never an
    import."""
    tree = ast.parse((PKG / f"{name}.py").read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "figure":
            pytest.fail(f"{name}.py imports figure.py")
