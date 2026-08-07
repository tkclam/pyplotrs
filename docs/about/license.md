# License

pyplotrs is released under the
**MIT license** ([LICENSE](https://github.com/tkclam/pyplotrs/blob/main/LICENSE)).

Unless you explicitly state otherwise, any contribution intentionally submitted
for inclusion in the work by you shall be licensed as above, without any
additional terms or conditions.

## Bundled third-party assets

pyplotrs embeds a small number of third-party assets, each under a permissive
license.

### Fonts (embedded in the compiled extension)

- **Liberation Sans** — © 2012 Red Hat, Inc. (digitized data © 2010 Google
  Corp.). SIL Open Font License 1.1. The bundled, permissive, Arial-metric-
  compatible fallback for body text.
  Source: <https://github.com/liberationfonts>.
  License text: [`assets/fonts/LiberationSans-OFL.txt`](https://github.com/tkclam/pyplotrs/blob/main/assets/fonts/LiberationSans-OFL.txt).
- **STIX Two Math** — © 2001–2021 The STIX Fonts Project Authors. SIL Open Font
  License 1.1. Used for `$...$` math.
  Source: <https://github.com/stipub/stixfonts>.
  License text: [`assets/fonts/STIXTwoMath-OFL.txt`](https://github.com/tkclam/pyplotrs/blob/main/assets/fonts/STIXTwoMath-OFL.txt).

Arial and Helvetica are **not** bundled (they are proprietary). pyplotrs prefers
host Arial/Helvetica for body text when installed, else the bundled Liberation
Sans; the chosen font is embedded into every saved figure. See
[`assets/fonts/NOTICE.md`](https://github.com/tkclam/pyplotrs/blob/main/assets/fonts/NOTICE.md)
for which file plays which role.

### Colormap data

The `viridis`, `plasma`, `inferno`, `magma` and `cividis` lookup tables are the
canonical perceptually-uniform colormaps created for matplotlib by Stefan van der
Walt and Nathaniel Smith, dedicated to the **public domain (CC0)**. pyplotrs ships
the exact 256-entry RGB lookup tables in `python/pyplotrs/_colormap_data.py`,
generated from matplotlib's upstream `_cm_listed.py`.

`grays` and `coolwarm` are defined analytically in `python/pyplotrs/colormaps.py`
and carry no third-party data.
