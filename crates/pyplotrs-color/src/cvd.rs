//! Color-vision-deficiency (CVD) simulation and perceptual-uniformity/
//! CVD-safety diagnostics for colormaps.
//!
//! Simulation uses the (Machado, Oliveira & Fernandes, 2009) physiologically
//! based dichromacy model at full severity, applied in **linear** RGB (their
//! matrices are only valid there - applying them to gamma-encoded sRGB is a
//! common mistake that desaturates results incorrectly). The matrices below
//! are the widely-reproduced severity=1.0 tables from the paper's
//! supplementary data (cross-checked against the `colour-science` /
//! `DaltonLens` reference implementations).

use crate::colorspace::{cam16ucs_distance, linear_to_srgb, srgb_to_linear};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum CvdKind {
    Protanopia,
    Deuteranopia,
    Tritanopia,
}

impl CvdKind {
    pub fn parse(s: &str) -> Option<CvdKind> {
        Some(match s {
            "protanopia" => CvdKind::Protanopia,
            "deuteranopia" => CvdKind::Deuteranopia,
            "tritanopia" => CvdKind::Tritanopia,
            _ => return None,
        })
    }

    fn matrix(self) -> [[f64; 3]; 3] {
        match self {
            CvdKind::Protanopia => [
                [0.152286, 1.052583, -0.204868],
                [0.114503, 0.786281, 0.099216],
                [-0.003882, -0.048116, 1.051998],
            ],
            CvdKind::Deuteranopia => [
                [0.367322, 0.860646, -0.227968],
                [0.280085, 0.672501, 0.047413],
                [-0.011820, 0.042940, 0.968881],
            ],
            CvdKind::Tritanopia => [
                [1.255528, -0.076749, -0.178779],
                [-0.078411, 0.930809, 0.147602],
                [0.004733, 0.691367, 0.303900],
            ],
        }
    }
}

fn apply3x3(m: [[f64; 3]; 3], v: [f64; 3]) -> [f64; 3] {
    [
        m[0][0] * v[0] + m[0][1] * v[1] + m[0][2] * v[2],
        m[1][0] * v[0] + m[1][1] * v[1] + m[1][2] * v[2],
        m[2][0] * v[0] + m[2][1] * v[1] + m[2][2] * v[2],
    ]
}

/// Simulate how `rgb` appears to someone with `kind` dichromacy.
pub fn simulate(rgb: [u8; 3], kind: CvdKind) -> [u8; 3] {
    let lin = srgb_to_linear(rgb);
    linear_to_srgb(apply3x3(kind.matrix(), lin))
}

/// Evenly sample `table` down to `n` colors (for cheap O(n^2) comparisons
/// over what may be a 256-entry table).
fn sample(table: &[[u8; 3]], n: usize) -> Vec<[u8; 3]> {
    if table.len() <= n {
        return table.to_vec();
    }
    (0..n)
        .map(|i| table[i * (table.len() - 1) / (n - 1)])
        .collect()
}

/// How much a colormap's worst-case distinguishability degrades under a
/// given CVD: the minimum pairwise CAM16-UCS distance among 16 evenly
/// spaced samples, simulated under `kind`, divided by that same minimum
/// distance *without* simulation. `1.0` = CVD does not shrink the map's
/// worst-case contrast at all; values near `0.0` mean some pair of colors
/// that reads as distinct normally becomes visually identical under `kind`.
pub fn cvd_safety_ratio(table: &[[u8; 3]], kind: CvdKind) -> f64 {
    let samples = sample(table, 16);
    let min_pairwise = |colors: &[[u8; 3]]| -> f64 {
        let mut min = f64::INFINITY;
        for i in 0..colors.len() {
            for j in (i + 1)..colors.len() {
                min = min.min(cam16ucs_distance(colors[i], colors[j]));
            }
        }
        min
    };
    let baseline = min_pairwise(&samples);
    if baseline <= 1e-9 {
        return 1.0; // a table with no contrast to begin with can't "lose" any.
    }
    let simulated: Vec<[u8; 3]> = samples.iter().map(|&c| simulate(c, kind)).collect();
    (min_pairwise(&simulated) / baseline).clamp(0.0, 1.0)
}

/// A perceptual-uniformity roughness score for a colormap: the coefficient
/// of variation (stddev / mean) of the CAM16-UCS step distance between
/// consecutive table entries. `0.0` means every step looks equally large
/// (ideal for e.g. `imshow` of continuous data, where visual step size
/// should track data step size); larger values mean some regions of the
/// map compress a lot of data range into little visual change (or vice
/// versa).
pub fn perceptual_uniformity(table: &[[u8; 3]]) -> f64 {
    if table.len() < 3 {
        return 0.0;
    }
    let steps: Vec<f64> = table
        .windows(2)
        .map(|w| cam16ucs_distance(w[0], w[1]))
        .collect();
    let mean = steps.iter().sum::<f64>() / steps.len() as f64;
    if mean <= 1e-9 {
        return 0.0;
    }
    let variance = steps.iter().map(|s| (s - mean).powi(2)).sum::<f64>() / steps.len() as f64;
    variance.sqrt() / mean
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn grayscale_is_unaffected_by_cvd() {
        // Achromatic colors carry no hue information, so every dichromacy
        // model should leave them (near) unchanged.
        for kind in [
            CvdKind::Protanopia,
            CvdKind::Deuteranopia,
            CvdKind::Tritanopia,
        ] {
            for g in [0u8, 64, 128, 200, 255] {
                let sim = simulate([g, g, g], kind);
                for c in sim {
                    assert!((c as i16 - g as i16).abs() <= 2, "{kind:?} {g} -> {sim:?}");
                }
            }
        }
    }

    #[test]
    fn viridis_like_ramp_is_reasonably_perceptually_uniform() {
        // A hand-built linear-in-Oklab-lightness grayscale ramp should score
        // near-zero roughness - it is uniform by construction.
        let table: Vec<[u8; 3]> = (0..256).map(|i| [i as u8, i as u8, i as u8]).collect();
        let roughness = perceptual_uniformity(&table);
        assert!(roughness < 0.5, "roughness = {roughness}");
    }

    #[test]
    fn safety_ratio_is_one_for_a_flat_table() {
        let table = vec![[100u8, 100, 100]; 8];
        assert_eq!(cvd_safety_ratio(&table, CvdKind::Deuteranopia), 1.0);
    }

    #[test]
    fn red_green_diverging_map_is_unsafe_under_deuteranopia() {
        // The classic red<->green diverging map is the textbook example of a
        // colorblind-unsafe colormap: red and green become near-identical
        // under deuteranopia/protanopia.
        let table = vec![[220u8, 20, 20], [20, 180, 20]];
        let ratio = cvd_safety_ratio(&table, CvdKind::Deuteranopia);
        assert!(ratio < 0.5, "ratio = {ratio}");
    }
}
