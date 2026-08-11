<!-- What changes for a user of the library, and why. -->

## Checklist

- [ ] `cargo fmt --all -- --check`, `cargo clippy --workspace --all-targets --locked -- -D warnings`, `cargo test --workspace --locked`
- [ ] `ruff check .` and `pytest -q --strict-markers`
- [ ] `mkdocs build --strict` if any docstring or page changed
- [ ] A bug fix has a test that fails without it
- [ ] A new public `Axes` method is registered in `_MARK_CALLS` or listed in `_NOT_MARKS` with a reason
- [ ] A golden image that moved was inspected, not just regenerated
- [ ] A new dependency or bundled asset: `python tools/gen_third_party_notices.py` re-run and committed
