"""Repository consistency: version, stub, notices, examples."""

import ast
import pathlib
import runpy
import subprocess
import tomllib

import pytest

import pyplotrs as pp
from pyplotrs import _core

ROOT = pathlib.Path(__file__).resolve().parent.parent


def test_version_comes_from_cargo():
    cargo = tomllib.loads((ROOT / "Cargo.toml").read_text())
    assert pp.__version__ == cargo["workspace"]["package"]["version"]


def test_stub_matches_extension():
    tree = ast.parse((ROOT / "python/pyplotrs/_core.pyi").read_text())
    stubbed = {n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
    runtime = {n for n in dir(_core) if not n.startswith("_")}
    assert stubbed == runtime
    scene_stub = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "Scene")
    methods = {n.name for n in scene_stub.body if isinstance(n, ast.FunctionDef)} - {"__init__"}
    assert methods == {n for n in dir(_core.Scene) if not n.startswith("_")}


def test_public_names_exist():
    for name in pp.__all__:
        assert hasattr(pp, name), name


def test_third_party_notices_are_current():
    if subprocess.run(["cargo", "--version"], capture_output=True).returncode != 0:
        pytest.skip("needs cargo")
    before = (ROOT / "THIRD-PARTY-NOTICES.md").read_text()
    subprocess.run(
        ["python", "tools/gen_third_party_notices.py"], cwd=ROOT, check=True, capture_output=True
    )
    assert (ROOT / "THIRD-PARTY-NOTICES.md").read_text() == before


@pytest.mark.parametrize("script", sorted((ROOT / "examples").glob("*.py")), ids=lambda p: p.stem)
def test_examples_run(script, tmp_path, monkeypatch):
    monkeypatch.setenv("PYPLOTRS_EXAMPLES_OUT", str(tmp_path))
    runpy.run_path(str(script), run_name="__main__")
    assert any(tmp_path.iterdir())
