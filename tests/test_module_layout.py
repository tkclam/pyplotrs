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

ROOT = pathlib.Path(__file__).resolve().parent.parent
PKG = ROOT / "python" / "pyplotrs"

#: No module in the drawing layer should get near the old figure.py again.
#: `axes.py` is the legitimately large one - it is the whole 2D mark surface -
#: and is capped well below where figure.py was.
SIZE_CAP = {"axes.py": 3200}
DEFAULT_CAP = 1200


def _modules():
    return sorted(p for p in PKG.glob("*.py") if p.name != "__init__.py")


@pytest.mark.parametrize("path", _modules(), ids=lambda p: p.name)
def test_no_module_is_a_god_module(path):
    n = len(path.read_text(encoding="utf-8").splitlines())
    cap = SIZE_CAP.get(path.name, DEFAULT_CAP)
    assert n <= cap, f"{path.name} is {n} lines (cap {cap})"


def test_figure_module_only_orchestrates():
    """`figure.py` should hold the Figure, the grid helpers and nothing else -
    no axes classes, no drawing primitives."""
    tree = ast.parse((PKG / "_figure.py").read_text(encoding="utf-8"))
    defined = {n.name for n in tree.body
               if isinstance(n, (ast.ClassDef, ast.FunctionDef))}
    assert "Figure" in defined
    for leaked in ("Axes", "Axes3D", "PolarAxes", "_AxesBase", "_draw_marker",
                   "_to_f64", "_measure_legend"):
        assert leaked not in defined, f"{leaked} moved back into figure.py"


@pytest.mark.parametrize("name,module", [
    ("Axes", "axes"), ("Axes3D", "axes3d"), ("PolarAxes", "polar"),
    ("Figure", "_figure"), ("GridSpec", "_figure"), ("Mappable", "mappable"),
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
    layer = {"_const": 0, "_util": 1, "_draw": 2, "_layout": 2, "mappable": 2,
             "axes": 3, "axes3d": 4, "polar": 4, "_figure": 5}
    for name, rank in layer.items():
        tree = ast.parse((PKG / f"{name}.py").read_text(encoding="utf-8"))
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
    tree = ast.parse((PKG / f"{name}.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "_figure":
            pytest.fail(f"{name}.py imports _figure.py")


# -- syntax the declared floor can actually parse ----------------------------

def test_no_source_file_uses_post_39_syntax():
    """`requires-python = ">=3.9"` has to be true of the *syntax*, not just the
    APIs.

    The `checks` job runs 3.11 and the wheel jobs run a prebuilt wheel, so a
    3.12-only construct in the source tree would only surface for a user
    building from an sdist on 3.9 - the platform with no wheel, i.e. the one
    least able to diagnose it.

    Caught here rather than by review because the failure is a `SyntaxError` at
    *import*, so a single one takes the whole module with it. This suite had
    one: an f-string whose expression contained a backslash, legal only from
    3.12 (PEP 701).
    """
    import re

    offenders = []
    roots = [PKG, ROOT / "tests", ROOT / "examples", ROOT / "tools", ROOT / "benchmarks"]
    for root in roots:
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*.py")):
            if "_vendor" in path.parts:
                continue
            for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if 'f"' not in line and "f'" not in line:
                    continue
                for expr in re.findall(r"\{([^{}]*)\}", line):
                    if "\\" in expr:
                        offenders.append(
                            f"{path.relative_to(ROOT)}:{lineno} - backslash in an "
                            f"f-string expression needs 3.12"
                        )
    assert not offenders, "\n".join(offenders)


def test_the_package_compiles_under_the_declared_floor():
    """Compile every shipped module with the oldest feature set we claim.

    `ast.parse(feature_version=...)` rejects syntax newer than the given minor
    version, so this catches match statements, `except*` and the f-string
    relaxations without needing a 3.9 interpreter on the machine. It covers the
    *package* only: tests and dev tools are run by the developer, not by a user
    on the floor version.
    """
    import ast

    floor = (3, 9)
    offenders = []
    for path in sorted(PKG.rglob("*.py")):
        if "_vendor" in path.parts:
            continue
        try:
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path), feature_version=floor)
        except SyntaxError as exc:
            offenders.append(
                f"{path.relative_to(ROOT)}:{exc.lineno} - {exc.msg} "
                f"(needs newer than {floor[0]}.{floor[1]})"
            )
    assert not offenders, (
        "pyproject declares requires-python >= 3.9:\n" + "\n".join(offenders)
    )


def test_annotations_are_never_evaluated_at_import_on_the_floor_version():
    """PEP 604 (`int | None`) is 3.10 syntax *when evaluated*.

    It parses fine on 3.9 - annotations are only a syntax error at runtime, when
    the interpreter builds the object - so `ast.parse` above cannot see this.
    What makes it safe is `from __future__ import annotations`, which turns every
    annotation into a string that is never evaluated.

    Every module in the package has that import except `__init__.py`, which is
    also the only one a user imports directly, so this checks the pairing rather
    than assuming it: a module either has the future import, or it uses no
    PEP 604 union anywhere.
    """
    import ast

    offenders = []
    for path in sorted(PKG.rglob("*.py")):
        if "_vendor" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        deferred = any(
            isinstance(node, ast.ImportFrom)
            and node.module == "__future__"
            and any(alias.name == "annotations" for alias in node.names)
            for node in tree.body
        )
        if deferred:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
                # A `|` between names/subscripts in an annotation position.
                if isinstance(node.left, (ast.Name, ast.Subscript, ast.Constant)):
                    offenders.append(
                        f"{path.relative_to(ROOT)}:{node.lineno} - PEP 604 union "
                        f"without `from __future__ import annotations` is a "
                        f"TypeError on Python 3.9"
                    )
    assert not offenders, "\n".join(offenders)
