# Third-party assets bundled in figurs

## Fonts (embedded in the compiled extension)

- **Inter** — © 2020 The Inter Project Authors. SIL Open Font License 1.1.
  Source: https://github.com/rsms/inter
  License text: `assets/fonts/Inter-OFL.txt`
- **STIX Two Math** — © 2001–2021 The STIX Fonts Project Authors. SIL Open Font
  License 1.1. Source: https://github.com/stipub/stixfonts
  License text: `assets/fonts/STIXTwoMath-OFL.txt`

See `assets/fonts/NOTICE.md` for which file plays which role.

## Colormap data

- **viridis, plasma, inferno, magma, cividis** — the canonical perceptually-
  uniform colormaps created by Stefan van der Walt and Nathaniel Smith for
  matplotlib and dedicated to the **public domain (CC0)**. figurs ships the
  exact 256-entry RGB lookup tables in `python/figurs/_colormap_data.py`,
  generated from matplotlib's upstream `_cm_listed.py`.

`grays` and `coolwarm` are defined analytically in `python/figurs/colormaps.py`
and carry no third-party data.
