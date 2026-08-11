"""What the built artifacts have to contain.

Two things nothing else in the suite can see, because both are properties of
the *distribution* rather than of the library: the source distribution has to
be buildable, and every redistributed asset has to carry its license.

## The sdist

`139179d` vendored a patched krilla and wired it in with
``[patch.crates-io] krilla = { path = "vendor/krilla-0.8.2" }``, but did not add
``vendor/`` to ``[tool.maturin].include``. maturin does not follow patch paths
when collecting an sdist, so the resulting tarball carried the patch stanza and
none of the code it pointed at: ``cargo metadata`` on it died with ``failed to
load source for dependency krilla``. Wheels were fine - they build from the git
checkout, where ``vendor/`` is tracked - so nothing caught it. CI's ``sdist``
job only *built* the sdist and never built *from* it, and the sdist is exactly
what PyPI hands to any platform without a matching wheel.

Two tests, deliberately at different costs:

* :func:`test_patch_paths_are_included_in_sdist` is static and instant, so it
  runs in the normal suite and fails the moment a new ``[patch.crates-io]``
  path is added without an ``include`` entry.
* :func:`test_sdist_resolves` actually builds the tarball and resolves it with
  cargo. It needs maturin and a network-warm cargo registry, so it is marked
  ``packaging`` and deselected by default; CI runs it explicitly.

## The licenses

The wheels redistribute two font families, ~150 colormap tables, a 2.2 MB
MathJax bundle and ~110 statically linked Rust crates. Several of those
licenses require the notice to travel with the binary. Listing a file in
``[project] license-files`` is what puts it in ``dist-info/licenses/``, and
nothing tied that list to the files actually present - which is how the
MathJax bundle came to ship with no license text anywhere in the wheel, the
sdist, or the generated ``.html`` pages that inline it.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest

# `tomllib` is 3.11+, and this package supports 3.9. A bare `import tomllib`
# here is a *collection* error on 3.9/3.10, which fails the whole run rather
# than skipping a file - and 3.9 is exactly the interpreter the linux and macOS
# wheel jobs use, so the entire suite aborted there.
try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - 3.9/3.10 only
    try:
        import tomli as tomllib  # type: ignore[no-redef]
    except ModuleNotFoundError:
        tomllib = None  # type: ignore[assignment]

requires_toml = pytest.mark.skipif(
    tomllib is None,
    reason="needs tomllib (3.11+) or tomli; `pip install pyplotrs[test]` provides one",
)

ROOT = Path(__file__).resolve().parent.parent


def _patch_paths() -> list[str]:
    """Local paths the root workspace patches crates.io with."""
    if tomllib is None:  # pragma: no cover - collection-time on 3.9/3.10
        return []
    cargo = tomllib.loads((ROOT / "Cargo.toml").read_text())
    patched = cargo.get("patch", {}).get("crates-io", {})
    return [spec["path"] for spec in patched.values() if "path" in spec]


def _pyproject() -> dict:
    return tomllib.loads((ROOT / "pyproject.toml").read_text())


def _sdist_include_globs() -> list[str]:
    include = _pyproject().get("tool", {}).get("maturin", {}).get("include", [])
    return [e["path"] for e in include
            if isinstance(e, dict) and e.get("format") in (None, "sdist")]


@requires_toml
def test_there_is_something_to_check():
    """Guard the guard: if the krilla patch is ever dropped, these tests would
    silently pass while asserting nothing."""
    assert _patch_paths(), "expected at least one [patch.crates-io] path entry"


@requires_toml
@pytest.mark.parametrize("patch_path", _patch_paths() or ["vendor/krilla-0.8.2"])
def test_patch_paths_are_included_in_sdist(patch_path):
    """Every patched path must have its sources swept into the sdist.

    Checked by expanding the include globs for real rather than by comparing
    strings, so a glob that looks right but matches nothing still fails.
    """
    covered = {p.relative_to(ROOT) for glob in _sdist_include_globs()
               for p in ROOT.glob(glob) if p.is_file()}

    # The crate cannot be resolved without its manifest, nor built without its
    # sources; if both are in, the glob is sweeping the tree rather than a
    # single stray file.
    manifest = Path(patch_path) / "Cargo.toml"
    assert manifest in covered, (
        f"{manifest} is missing from the sdist: '{patch_path}' is a "
        f"[patch.crates-io] target, so cargo cannot resolve the dependency "
        f"graph without it. Add it to [tool.maturin].include in pyproject.toml."
    )
    sources = [p for p in covered
               if p.is_relative_to(Path(patch_path) / "src") and p.suffix == ".rs"]
    assert sources, f"no .rs sources from {patch_path}/src are in the sdist"


@pytest.mark.packaging
def test_sdist_resolves(tmp_path):
    """Build the sdist and resolve it with cargo, the way a from-source install
    does. This is the check whose absence let the broken sdist ship."""
    if shutil.which("cargo") is None:
        pytest.skip("cargo not available")

    out = tmp_path / "dist"
    build = subprocess.run(
        [sys.executable, "-m", "maturin", "sdist", "-o", str(out)],
        cwd=ROOT, capture_output=True, text=True,
    )
    if build.returncode != 0:
        if "No module named maturin" in build.stderr:
            pytest.skip("maturin not available")
        pytest.fail(f"maturin sdist failed:\n{build.stderr}")

    tarballs = list(out.glob("*.tar.gz"))
    assert len(tarballs) == 1, f"expected one sdist, got {tarballs}"

    extracted = tmp_path / "src"
    with tarfile.open(tarballs[0]) as tar:
        tar.extractall(extracted, filter="data")
    (pkg,) = list(extracted.iterdir())

    resolved = subprocess.run(
        ["cargo", "metadata", "--format-version", "1",
         "--manifest-path", str(pkg / "Cargo.toml")],
        capture_output=True, text=True,
    )
    assert resolved.returncode == 0, (
        "the sdist does not resolve - a from-source `pip install` would fail "
        f"here:\n{resolved.stderr}"
    )


# -- what actually reaches the user ------------------------------------------
#
# The distribution redistributes fonts, colormap tables, a MathJax bundle and
# ~110 Rust crates. Several of those licenses require the notice to travel with
# the artifact. Listing a file in `[project] license-files` is what puts it in
# `dist-info/licenses/`; these tests check the list has not drifted from the
# files on disk, which is how the MathJax bundle came to ship for months with
# no license text anywhere.

@requires_toml
def test_every_declared_license_file_exists():
    missing = [rel for rel in _pyproject()["project"]["license-files"]
               if not (ROOT / rel).is_file()]
    assert not missing, (
        f"declared in license-files but not on disk: {missing}. The build "
        f"fails on this, so it would not reach a wheel."
    )


@requires_toml
@pytest.mark.parametrize("asset,notice", [
    ("python/pyplotrs/_vendor/mathjax-tex-svg-full.min.js",
     "python/pyplotrs/_vendor/MATHJAX-LICENSE.txt"),
    ("assets/fonts/LiberationSans-Regular.ttf",
     "assets/fonts/LiberationSans-OFL.txt"),
    ("assets/fonts/STIXTwoMath-Regular.ttf",
     "assets/fonts/STIXTwoMath-OFL.txt"),
])
def test_every_redistributed_asset_ships_its_license(asset, notice):
    """If the asset is here, so is its license, and the license is declared."""
    if not (ROOT / asset).is_file():
        pytest.skip(f"{asset} is not present in this checkout")
    assert (ROOT / notice).is_file(), f"{asset} ships without {notice}"
    assert notice in _pyproject()["project"]["license-files"], (
        f"{notice} exists but is not in license-files, so it never reaches "
        f"dist-info/licenses/ and a wheel user cannot see it"
    )


def test_the_mathjax_version_is_recorded_where_it_is_claimed():
    """The banner, the notice file and the bundle must agree, so an upgrade
    cannot leave the attribution describing the previous release."""
    from pyplotrs import _htmlmath

    version = _htmlmath.MATHJAX_VERSION
    assert f'VERSION="{version}"' in _htmlmath._BUNDLE_PATH.read_text(encoding="utf-8"), (
        f"MATHJAX_VERSION is {version!r} but the bundle does not declare it"
    )
    assert version in _htmlmath._MATHJAX_BANNER
    notice = (ROOT / "python/pyplotrs/_vendor/MATHJAX-NOTICE.md").read_text(encoding="utf-8")
    assert version in notice


def test_generated_html_carries_the_mathjax_attribution():
    """Inlining the bundle makes each `.html` figure its own redistribution,
    so the notice has to be in the file itself, not only in the wheel."""
    import pyplotrs as plt

    fig, ax = plt.subplots(figsize=(200, 150))
    ax.set(title=r"$\alpha + \beta$")
    page = fig.to_html() if hasattr(fig, "to_html") else None
    if page is None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "f.html"
            fig.save(str(out))
            page = out.read_text(encoding="utf-8")
    assert "MathJax" in page and "Apache-2.0" in page, (
        "a generated math page must carry the MathJax attribution banner"
    )


@requires_toml
def test_third_party_notices_are_up_to_date():
    """`THIRD-PARTY-NOTICES.md` is generated from the resolved Cargo graph, so
    adding or bumping a dependency must regenerate it."""
    if shutil.which("cargo") is None:
        pytest.skip("cargo not available")
    committed = (ROOT / "THIRD-PARTY-NOTICES.md").read_text(encoding="utf-8")
    result = subprocess.run(
        [sys.executable, "tools/gen_third_party_notices.py"],
        cwd=ROOT, capture_output=True, text=True,
    )
    assert result.returncode == 0, (
        f"the notice generator failed - a dependency may carry a license "
        f"outside the allowed set:\n{result.stdout}\n{result.stderr}"
    )
    assert (ROOT / "THIRD-PARTY-NOTICES.md").read_text(encoding="utf-8") == committed, (
        "THIRD-PARTY-NOTICES.md is stale; run "
        "`python tools/gen_third_party_notices.py` and commit the result"
    )


@requires_toml
def test_the_typing_classifier_is_backed_by_a_py_typed_marker():
    """PEP 561: without the marker, a type checker discards every annotation in
    the package and the shipped `_pyplotrs_core.pyi` stub, and reports
    `module is installed, but missing library stubs or py.typed marker`. The
    classifier claimed otherwise in immutable published metadata."""
    classifiers = _pyproject()["project"]["classifiers"]
    marker = ROOT / "python" / "pyplotrs" / "py.typed"
    if "Typing :: Typed" in classifiers:
        assert marker.is_file(), (
            "pyproject declares `Typing :: Typed` but python/pyplotrs/py.typed "
            "does not exist, so the claim is false for every consumer"
        )
    else:
        assert not marker.is_file(), (
            "py.typed is present but the `Typing :: Typed` classifier was "
            "removed, so consumers cannot discover the typing support"
        )


def test_py_typed_is_next_to_the_installed_package():
    """The marker has to reach the *installed* package, not merely the repo:
    maturin's `python-source` sweep is what carries it, and a stray
    `[tool.maturin] include` or exclude could drop it."""
    import pyplotrs

    installed = Path(pyplotrs.__file__).parent
    assert (installed / "py.typed").is_file(), (
        f"py.typed is missing from the installed package at {installed}"
    )


# -- version identity --------------------------------------------------------

def test_the_package_reports_a_version():
    import pyplotrs

    assert hasattr(pyplotrs, "__version__"), "pyplotrs.__version__ must exist"
    assert pyplotrs.__version__ != "0.0.0+unknown", (
        "the version fell back to the source-tree placeholder, which means the "
        "distribution metadata was not found - the package is not installed"
    )
    assert "__version__" in pyplotrs.__all__


@requires_toml
def test_the_python_version_comes_from_cargo():
    """One source of truth. `pyproject.toml` used to carry an independent
    literal with nothing comparing the two, so they could silently disagree and
    the release job's tag check would validate only one of them."""
    import pyplotrs

    cargo = tomllib.loads((ROOT / "Cargo.toml").read_text())
    workspace_version = cargo["workspace"]["package"]["version"]
    assert pyplotrs.__version__ == workspace_version, (
        f"pyplotrs.__version__ is {pyplotrs.__version__!r} but "
        f"Cargo.toml says {workspace_version!r}"
    )
    assert "version" in _pyproject()["project"].get("dynamic", []), (
        "pyproject must take `version` from Cargo, not restate it"
    )
    assert "version" not in _pyproject()["project"], (
        "a static `version` in [project] shadows the dynamic one"
    )


@requires_toml
def test_every_crate_inherits_the_workspace_msrv():
    """A `rust-version` no crate inherits is inert: `cargo metadata` reports
    null for all ten and cargo enforces nothing, which is how the declaration
    came to be wrong by twelve minor versions without anyone noticing."""
    declared = tomllib.loads(
        (ROOT / "Cargo.toml").read_text())["workspace"]["package"]["rust-version"]
    missing = []
    for manifest in sorted((ROOT / "crates").glob("*/Cargo.toml")):
        text = manifest.read_text()
        if "rust-version.workspace = true" not in text:
            missing.append(manifest.parent.name)
    assert not missing, (
        f"these crates do not inherit rust-version = {declared!r}: {missing}"
    )


@requires_toml
def test_the_documented_msrv_matches_the_declared_one():
    declared = tomllib.loads(
        (ROOT / "Cargo.toml").read_text())["workspace"]["package"]["rust-version"]
    install_doc = (ROOT / "docs" / "installation.md").read_text()
    assert declared in install_doc, (
        f"docs/installation.md does not mention the declared MSRV {declared!r}"
    )


@requires_toml
def test_no_crate_can_be_published_to_crates_io():
    """They depend on each other by path and the root patches crates.io with a
    vendored krilla, so a published copy could not resolve for anyone."""
    for manifest in sorted((ROOT / "crates").glob("*/Cargo.toml")):
        assert "publish = false" in manifest.read_text(), (
            f"{manifest.parent.name} is missing `publish = false`"
        )
