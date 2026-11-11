//! sRGB <-> linear <-> XYZ <-> Lab <-> Oklab/Oklch conversions on `[u8; 3]` /
//! `[f64; 3]` triples, built on the `palette` crate.

use palette::white_point::D65;
use palette::{FromColor, IntoColor, Lab, LinSrgb, Oklab, Oklch, Srgb, Xyz};

fn clamp01(x: f64) -> f64 {
    x.clamp(0.0, 1.0)
}

pub fn srgb_u8_to_f64(rgb: [u8; 3]) -> [f64; 3] {
    [
        rgb[0] as f64 / 255.0,
        rgb[1] as f64 / 255.0,
        rgb[2] as f64 / 255.0,
    ]
}

pub fn f64_to_srgb_u8(rgb: [f64; 3]) -> [u8; 3] {
    [
        (clamp01(rgb[0]) * 255.0).round() as u8,
        (clamp01(rgb[1]) * 255.0).round() as u8,
        (clamp01(rgb[2]) * 255.0).round() as u8,
    ]
}

fn to_srgb(rgb: [u8; 3]) -> Srgb<f64> {
    let [r, g, b] = srgb_u8_to_f64(rgb);
    Srgb::new(r, g, b)
}

fn from_srgb(c: Srgb<f64>) -> [u8; 3] {
    f64_to_srgb_u8([c.red, c.green, c.blue])
}

/// Encoded (gamma) sRGB -> linear-light sRGB.
pub fn srgb_to_linear(rgb: [u8; 3]) -> [f64; 3] {
    let lin: LinSrgb<f64> = to_srgb(rgb).into_color();
    [lin.red, lin.green, lin.blue]
}

/// Linear-light sRGB -> encoded (gamma) sRGB.
pub fn linear_to_srgb(rgb: [f64; 3]) -> [u8; 3] {
    let lin = LinSrgb::new(rgb[0], rgb[1], rgb[2]);
    from_srgb(Srgb::from_color(lin))
}

/// sRGB -> CIE 1931 XYZ (D65 white point).
pub fn srgb_to_xyz(rgb: [u8; 3]) -> [f64; 3] {
    let xyz: Xyz<D65, f64> = to_srgb(rgb).into_color();
    [xyz.x, xyz.y, xyz.z]
}

/// CIE 1931 XYZ (D65) -> sRGB.
pub fn xyz_to_srgb(xyz: [f64; 3]) -> [u8; 3] {
    let xyz = Xyz::<D65, f64>::new(xyz[0], xyz[1], xyz[2]);
    from_srgb(Srgb::from_color(xyz))
}

/// sRGB -> CIELAB (D65 white point), `L*` in `[0, 100]`.
pub fn srgb_to_lab(rgb: [u8; 3]) -> [f64; 3] {
    let lab: Lab<D65, f64> = to_srgb(rgb).into_color();
    [lab.l, lab.a, lab.b]
}

/// CIELAB (D65) -> sRGB.
pub fn lab_to_srgb(lab: [f64; 3]) -> [u8; 3] {
    let lab = Lab::<D65, f64>::new(lab[0], lab[1], lab[2]);
    from_srgb(Srgb::from_color(lab))
}

/// sRGB -> Oklab (Ottosson 2020). This is the interpolation space
/// [`crate::color::interp`] uses by default for custom colormaps.
pub fn srgb_to_oklab(rgb: [u8; 3]) -> [f64; 3] {
    let lab: Oklab<f64> = to_srgb(rgb).into_color();
    [lab.l, lab.a, lab.b]
}

/// Oklab -> sRGB.
pub fn oklab_to_srgb(lab: [f64; 3]) -> [u8; 3] {
    let lab = Oklab::new(lab[0], lab[1], lab[2]);
    from_srgb(Srgb::from_color(lab))
}

/// sRGB -> Oklch (Oklab in cylindrical lightness/chroma/hue form).
/// `hue` is degrees.
pub fn srgb_to_oklch(rgb: [u8; 3]) -> [f64; 3] {
    let lch: Oklch<f64> = to_srgb(rgb).into_color();
    [lch.l, lch.chroma, lch.hue.into_positive_degrees()]
}

/// Oklch -> sRGB.
pub fn oklch_to_srgb(lch: [f64; 3]) -> [u8; 3] {
    let lch = Oklch::new(lch[0], lch[1], lch[2]);
    from_srgb(Srgb::from_color(lch))
}

#[cfg(test)]
mod tests {
    use super::*;
    use approx::assert_relative_eq;

    #[test]
    fn srgb_oklab_round_trip() {
        for rgb in [[0, 0, 0], [255, 255, 255], [255, 0, 0], [12, 200, 90]] {
            let lab = srgb_to_oklab(rgb);
            let back = oklab_to_srgb(lab);
            for i in 0..3 {
                assert!(
                    (rgb[i] as i16 - back[i] as i16).abs() <= 1,
                    "{rgb:?} -> {lab:?} -> {back:?}"
                );
            }
        }
    }

    #[test]
    fn white_is_achromatic_in_oklab() {
        let [l, a, b] = srgb_to_oklab([255, 255, 255]);
        assert_relative_eq!(l, 1.0, epsilon = 1e-3);
        assert_relative_eq!(a, 0.0, epsilon = 1e-3);
        assert_relative_eq!(b, 0.0, epsilon = 1e-3);
    }

    #[test]
    fn black_is_zero_lightness_everywhere() {
        assert_relative_eq!(srgb_to_oklab([0, 0, 0])[0], 0.0, epsilon = 1e-6);
        assert_relative_eq!(srgb_to_lab([0, 0, 0])[0], 0.0, epsilon = 1e-6);
    }

    #[test]
    fn white_xyz_matches_d65_reference() {
        // CIE D65 reference white, Y normalized to 1.0.
        let [x, y, z] = srgb_to_xyz([255, 255, 255]);
        assert_relative_eq!(x, 0.9505, epsilon = 2e-3);
        assert_relative_eq!(y, 1.0000, epsilon = 2e-3);
        assert_relative_eq!(z, 1.0890, epsilon = 2e-3);
    }
}
