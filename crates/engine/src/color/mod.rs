//! Built-in colormaps and palettes, and colormap construction from stops.

pub mod colorspace;
mod data;
pub mod interp;
pub mod registry;

pub use interp::InterpSpace;
pub use registry::{Category, Source};

/// A 256-entry RGB colormap table.
pub type Table = [[u8; 3]; 256];

/// Look up a built-in continuous colormap's exact table by name (a trailing
/// `_r` reverses it).
pub fn colormap_table(name: &str) -> Option<Table> {
    registry::continuous_table(name)
}

/// Build a 256-entry table from stops, interpolated in `space` (parsed via
/// [`InterpSpace::parse`]; unrecognized names fall back to Oklab).
pub fn colormap_table_from_stops(stops: &[(f64, [u8; 3])], space: &str) -> Table {
    let space = InterpSpace::parse(space).unwrap_or(InterpSpace::Oklab);
    interp::table_from_stops(stops, space)
}

/// A built-in categorical/qualitative palette's colors by name.
pub fn categorical_palette(name: &str) -> Option<&'static [[u8; 3]]> {
    registry::categorical_palette(name)
}

/// Names of built-in continuous colormaps, optionally filtered to one
/// category (`"sequential"`, `"diverging"`, `"cyclic"`,
/// `"perceptually_uniform"`, `"miscellaneous"`).
pub fn list_colormaps(category: Option<&str>) -> Vec<&'static str> {
    registry::list_continuous(category)
}

/// Names of built-in categorical/qualitative palettes.
pub fn list_palettes() -> Vec<&'static str> {
    registry::list_categorical()
}

/// A table as a 256x4 RGBA lookup buffer with uniform `alpha`.
pub fn rgba_lut(table: &Table, alpha: f64) -> [u8; 1024] {
    let a = (alpha.clamp(0.0, 1.0) * 255.0).round() as u8;
    let mut out = [0u8; 1024];
    for (i, [r, g, b]) in table.iter().enumerate() {
        let o = i * 4;
        out[o] = *r;
        out[o + 1] = *g;
        out[o + 2] = *b;
        out[o + 3] = a;
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn viridis_is_present_and_exact_at_known_points() {
        // Spot-check against matplotlib's well-known viridis endpoints
        // (regression guard on the extraction pipeline, not just palette).
        let table = colormap_table("viridis").expect("viridis registered");
        assert_eq!(table[0], [68, 1, 84]);
        assert_eq!(table[255], [253, 231, 37]);
    }

    #[test]
    fn reversed_suffix_reverses_the_table() {
        let fwd = colormap_table("viridis").unwrap();
        let rev = colormap_table("viridis_r").unwrap();
        assert_eq!(fwd[0], rev[255]);
        assert_eq!(fwd[255], rev[0]);
    }

    #[test]
    fn unknown_name_is_none() {
        assert!(colormap_table("not_a_real_colormap").is_none());
    }

    #[test]
    fn every_registered_name_round_trips_through_the_registry() {
        for name in list_colormaps(None) {
            assert!(colormap_table(name).is_some(), "{name} failed to load");
        }
        for name in list_palettes() {
            assert!(categorical_palette(name).is_some(), "{name} failed to load");
        }
    }

    #[test]
    fn category_filter_is_a_strict_subset() {
        let all = list_colormaps(None).len();
        let seq = list_colormaps(Some("sequential")).len();
        assert!(seq > 0 && seq < all);
    }

    #[test]
    fn cet_and_cmo_prefixes_are_present() {
        assert!(list_colormaps(None).contains(&"cet_fire"));
        assert!(list_colormaps(None).contains(&"cmo_thermal"));
    }

    #[test]
    fn tab10_matches_matplotlib_exactly() {
        let tab10 = categorical_palette("tab10").expect("tab10 registered");
        assert_eq!(tab10.len(), 10);
        assert_eq!(tab10[0], [31, 119, 180]); // matplotlib's tab:blue
    }

    #[test]
    fn rgba_lut_scales_alpha() {
        let table = colormap_table("viridis").unwrap();
        let full = rgba_lut(&table, 1.0);
        let half = rgba_lut(&table, 0.5);
        assert_eq!(full[3], 255);
        assert_eq!(half[3], 128);
        assert_eq!(full[0], table[0][0]);
    }

    #[test]
    fn from_stops_round_trips_endpoints() {
        let stops = [(0.0, [0u8, 0, 0]), (1.0, [255u8, 128, 0])];
        let table = colormap_table_from_stops(&stops, "oklab");
        assert_eq!(table[0], [0, 0, 0]);
        assert_eq!(table[255], [255, 128, 0]);
    }
}
