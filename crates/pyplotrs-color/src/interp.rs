//! Builds a 256-entry RGB lookup table from a short list of `(position,
//! color)` stops, interpolating in a perceptually meaningful color space
//! instead of raw sRGB. This is what backs a user's
//! `Colormap(name, stops=[...])` and any bundled analytic (non-table)
//! colormap.
//!
//! Oklab (Ottosson, 2020) is the default: it is the space contemporary
//! colormap tools (e.g. the `cmap` Python package, `culori`) interpolate in,
//! because equal Euclidean steps there correspond closely to equal
//! perceived-lightness/color steps, unlike sRGB. Intermediate colors that
//! land outside the sRGB gamut are clipped per-channel on the way back
//! (the same simple strategy those tools use).

use crate::colorspace::{
    f64_to_srgb_u8, lab_to_srgb, linear_to_srgb, oklab_to_srgb, srgb_to_lab, srgb_to_linear,
    srgb_to_oklab, srgb_u8_to_f64,
};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum InterpSpace {
    /// Ottosson 2020 Oklab - the default, and the modern standard for this.
    Oklab,
    /// CIE 1976 L*a*b*.
    Lab,
    /// Linear-light RGB (no gamma) - better than gamma-space sRGB lerp, but
    /// not perceptually uniform.
    Linear,
    /// Gamma-encoded sRGB - naive lerp, kept only for back-compat with the
    /// original pre-Rust implementation's behavior.
    Srgb,
}

impl InterpSpace {
    pub fn parse(s: &str) -> Option<InterpSpace> {
        Some(match s {
            "oklab" => InterpSpace::Oklab,
            "lab" => InterpSpace::Lab,
            "linear" => InterpSpace::Linear,
            "srgb" => InterpSpace::Srgb,
            _ => return None,
        })
    }
}

fn to_space(rgb: [u8; 3], space: InterpSpace) -> [f64; 3] {
    match space {
        InterpSpace::Oklab => srgb_to_oklab(rgb),
        InterpSpace::Lab => srgb_to_lab(rgb),
        InterpSpace::Linear => srgb_to_linear(rgb),
        InterpSpace::Srgb => srgb_u8_to_f64(rgb),
    }
}

fn from_space(v: [f64; 3], space: InterpSpace) -> [u8; 3] {
    match space {
        InterpSpace::Oklab => oklab_to_srgb(v),
        InterpSpace::Lab => lab_to_srgb(v),
        InterpSpace::Linear => linear_to_srgb(v),
        InterpSpace::Srgb => f64_to_srgb_u8(v),
    }
}

fn lerp3(a: [f64; 3], b: [f64; 3], t: f64) -> [f64; 3] {
    [
        a[0] + (b[0] - a[0]) * t,
        a[1] + (b[1] - a[1]) * t,
        a[2] + (b[2] - a[2]) * t,
    ]
}

/// Sample the piecewise-linear ramp defined by `stops` (sorted by position,
/// positions need not span `[0, 1]` - values before/after clamp to the end
/// stops) at `t`.
fn sample_at(stops: &[(f64, [f64; 3])], t: f64) -> [f64; 3] {
    if t <= stops[0].0 {
        return stops[0].1;
    }
    let last = stops.len() - 1;
    if t >= stops[last].0 {
        return stops[last].1;
    }
    for w in stops.windows(2) {
        let (p0, c0) = w[0];
        let (p1, c1) = w[1];
        if t <= p1 {
            let f = if p1 > p0 { (t - p0) / (p1 - p0) } else { 0.0 };
            return lerp3(c0, c1, f);
        }
    }
    stops[last].1
}

/// Build a 256-entry RGB table from `stops` (at least one required;
/// duplicated/unsorted positions are handled by sorting first).
pub fn table_from_stops(stops: &[(f64, [u8; 3])], space: InterpSpace) -> [[u8; 3]; 256] {
    assert!(!stops.is_empty(), "table_from_stops needs at least one stop");
    let mut sorted: Vec<(f64, [u8; 3])> = stops.to_vec();
    sorted.sort_by(|a, b| a.0.partial_cmp(&b.0).unwrap());
    let converted: Vec<(f64, [f64; 3])> = sorted
        .into_iter()
        .map(|(p, c)| (p, to_space(c, space)))
        .collect();

    let mut table = [[0u8; 3]; 256];
    for (i, slot) in table.iter_mut().enumerate() {
        let t = i as f64 / 255.0;
        *slot = from_space(sample_at(&converted, t), space);
    }
    table
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn endpoints_match_input_colors() {
        let stops = [(0.0, [10u8, 20, 30]), (1.0, [240u8, 230, 220])];
        let table = table_from_stops(&stops, InterpSpace::Oklab);
        assert_eq!(table[0], [10, 20, 30]);
        assert_eq!(table[255], [240, 230, 220]);
    }

    #[test]
    fn single_stop_is_flat() {
        let stops = [(0.5, [100u8, 150, 200])];
        let table = table_from_stops(&stops, InterpSpace::Oklab);
        assert!(table.iter().all(|&c| c == [100, 150, 200]));
    }

    #[test]
    fn oklab_midpoint_of_black_and_white_is_mid_gray() {
        let stops = [(0.0, [0u8, 0, 0]), (1.0, [255u8, 255, 255])];
        let table = table_from_stops(&stops, InterpSpace::Oklab);
        let mid = table[128];
        // L=0.5 in Oklab is linear-light v=0.5^3=0.125, which gamma-encodes
        // to sRGB ~100 (Björn Ottosson's reference formulas confirm this by
        // hand) - well below the ~128 a naive gamma-space lerp would give,
        // and below CSS's nominal "50% gray" (128,128,128).
        assert!(
            (90..=110).contains(&(mid[0] as i32)),
            "midpoint {mid:?} is not a perceptual mid-gray"
        );
        assert_eq!(mid[0], mid[1]);
        assert_eq!(mid[1], mid[2]);
    }

    #[test]
    fn three_stops_interpolate_piecewise() {
        let stops = [(0.0, [0u8, 0, 0]), (0.5, [255u8, 0, 0]), (1.0, [255u8, 255, 255])];
        let table = table_from_stops(&stops, InterpSpace::Srgb);
        assert_eq!(table[0], [0, 0, 0]);
        assert_eq!(table[128], [255, 1, 1]); // t=128/255 ~= 0.502, just past the red stop
        assert_eq!(table[255], [255, 255, 255]);
    }
}
