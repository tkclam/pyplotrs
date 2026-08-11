# Security policy

## Reporting a vulnerability

Please report privately, not as a public issue: use
[GitHub Private Vulnerability Reporting](https://github.com/tkclam/pyplotrs/security/advisories/new),
or email <thomas.lam@epfl.ch>.

Expect an acknowledgement within a week. This is a small project, so a fix may
take longer than that — you will be told either way rather than left waiting.

## Supported versions

Only the latest release. Below 1.0 there are no backports; a fix ships in the
next version.

## What is in scope

pyplotrs turns data you supply into PDF, SVG, PNG and HTML files. It has no
network access, no plugin loading, and no `eval` of user input. The paths worth
reporting are:

- **Anything in the Rust core that reads out of bounds, or that a Python-level
  call can make panic.** A panic is not memory-unsafe, but it crosses the FFI
  boundary as a `BaseException` that ordinary handlers miss, so it is treated
  as a bug worth fixing on the same footing. The workspace contains **no
  `unsafe` code** and `unsafe_code = "forbid"` keeps it that way.
- **Unbounded allocation from an ordinary argument.** A dpi, bin count or
  upsample factor that makes the process abort rather than raise. Several of
  these have been fixed; more may exist.
- **Anything unexpected in a generated file** — an `.html` figure that reaches
  the network, an SVG or PDF that embeds more than the figure's own data.
  Generated pages are meant to be entirely self-contained.
- **Anything reachable by opening a file pyplotrs wrote in a viewer.**

Rendering a figure from **untrusted data** is a supported use. Rendering from
untrusted *code* is not: a `Theme`, a `Colormap` or a `FuncFormatter` holds
Python callables, and running those is the point.

## Third-party code

The wheels statically link ~110 Rust crates and bundle a copy of MathJax; see
[`THIRD-PARTY-NOTICES.md`](https://github.com/tkclam/pyplotrs/blob/main/THIRD-PARTY-NOTICES.md).

`vendor/krilla-0.8.2/` is a **patched fork** of the krilla PDF writer, so
advisories against upstream krilla do not reach this tree through Dependabot.
The divergence is documented in
[`vendor/krilla-0.8.2/PYPLOTRS_PATCH.md`](https://github.com/tkclam/pyplotrs/blob/main/vendor/krilla-0.8.2/PYPLOTRS_PATCH.md);
upstream advisories are tracked manually. If you find one that applies here,
report it through the channel above.
