# Releasing

The version is set once, in `Cargo.toml` (`[workspace.package].version`); the
Python package reads it from there.

1. Bump the version in `Cargo.toml` and `CITATION.cff`, run `cargo check` to
   update `Cargo.lock`, and add a section to `docs/changelog.md`.
2. If dependencies changed: `uv run python tools/gen_third_party_notices.py`.
3. Push to `main` and wait for CI and the docs deploy.
4. Tag and push: `git tag v0.2.0 && git push origin v0.2.0`. The `release` job
   checks the tag matches the version, then publishes the wheels and sdist to
   PyPI through trusted publishing (environment `pypi`).
5. Check `pip install pyplotrs` in a clean environment gets a wheel.

A wrong upload cannot be replaced on PyPI: yank it and release the next patch.
