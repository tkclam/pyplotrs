//! Font resolution: which faces a figure's text is shaped in.
//!
//! A figure names its body font as a list of preferred families (the theme's
//! `font_family`). Each family is tried against the host's installed fonts;
//! the bundled Liberation Sans (metric-compatible with Arial) is the final
//! fallback, so rendering never depends on what the machine has installed.
//! Whatever is chosen gets embedded in the saved file.
//!
//! Resolution is cached per family list, so repeated figures cost one lookup.

use std::collections::HashMap;
use std::sync::{Arc, Mutex, OnceLock};

use fontdb::{Database, Family, Query, Stretch, Style, Weight};

use crate::math::{FaceStyle, FontSet, MathFonts};
use crate::scene::FontData;

macro_rules! bundled {
    ($file:literal) => {
        include_bytes!(concat!(env!("CARGO_MANIFEST_DIR"), "/fonts/", $file))
    };
}

pub const LIBERATION_REGULAR: &[u8] = bundled!("LiberationSans-Regular.ttf");
pub const LIBERATION_BOLD: &[u8] = bundled!("LiberationSans-Bold.ttf");
pub const LIBERATION_ITALIC: &[u8] = bundled!("LiberationSans-Italic.ttf");
pub const LIBERATION_BOLD_ITALIC: &[u8] = bundled!("LiberationSans-BoldItalic.ttf");
/// Serif OpenType math font; the whole math font under [`FontSet::Stix`].
pub const STIX_MATH: &[u8] = bundled!("STIXTwoMath-Regular.ttf");
/// Sans OpenType math font; the primary math font under [`FontSet::Sans`].
pub const FIRA_MATH: &[u8] = bundled!("FiraMath-Regular.otf");
/// DejaVu Sans subset to the math symbol blocks (see
/// `tools/build_math_symbol_font.py`). Fills symbols a text face lacks.
pub const MATH_SYMBOLS: &[u8] = bundled!("DejaVuSans-MathSymbols.ttf");

/// The four body faces, indexed by `FaceStyle` as `bold << 1 | italic`.
const FACES: [FaceStyle; 4] = [
    FaceStyle {
        bold: false,
        italic: false,
    },
    FaceStyle {
        bold: false,
        italic: true,
    },
    FaceStyle {
        bold: true,
        italic: false,
    },
    FaceStyle {
        bold: true,
        italic: true,
    },
];

fn face_index(face: FaceStyle) -> usize {
    (face.bold as usize) << 1 | face.italic as usize
}

fn bundled_face(face: FaceStyle) -> (&'static [u8], &'static str) {
    match (face.bold, face.italic) {
        (false, false) => (LIBERATION_REGULAR, "LiberationSans-Regular"),
        (false, true) => (LIBERATION_ITALIC, "LiberationSans-Italic"),
        (true, false) => (LIBERATION_BOLD, "LiberationSans-Bold"),
        (true, true) => (LIBERATION_BOLD_ITALIC, "LiberationSans-BoldItalic"),
    }
}

fn static_font(slot: &'static OnceLock<FontData>, bytes: &'static [u8]) -> &'static FontData {
    slot.get_or_init(|| FontData::from_bytes(bytes.to_vec(), 0))
}

fn stix_math() -> &'static FontData {
    static F: OnceLock<FontData> = OnceLock::new();
    static_font(&F, STIX_MATH)
}

fn fira_math() -> &'static FontData {
    static F: OnceLock<FontData> = OnceLock::new();
    static_font(&F, FIRA_MATH)
}

fn math_symbols() -> &'static FontData {
    static F: OnceLock<FontData> = OnceLock::new();
    static_font(&F, MATH_SYMBOLS)
}

/// The host font database plus the bundled body faces, built once.
fn database() -> &'static Database {
    static DB: OnceLock<Database> = OnceLock::new();
    DB.get_or_init(|| {
        let mut db = Database::new();
        db.load_system_fonts();
        for face in FACES {
            db.load_font_data(bundled_face(face).0.to_vec());
        }
        db
    })
}

fn query(family: &str, face: FaceStyle) -> Option<ResolvedFace> {
    let db = database();
    let id = db.query(&Query {
        families: &[Family::Name(family)],
        weight: if face.bold {
            Weight::BOLD
        } else {
            Weight::NORMAL
        },
        stretch: Stretch::Normal,
        style: if face.italic {
            Style::Italic
        } else {
            Style::Normal
        },
    })?;
    let data = db.with_face_data(id, |bytes, index| {
        FontData::from_bytes(bytes.to_vec(), index)
    })?;
    let info = db.face(id)?;
    Some(ResolvedFace {
        family: info
            .families
            .first()
            .map_or_else(|| family.to_string(), |(n, _)| n.clone()),
        postscript: info.post_script_name.clone(),
        data,
    })
}

/// Faces tried, in order, for characters the body font cannot draw.
fn text_fallbacks() -> &'static [FontData] {
    static FALLBACKS: OnceLock<Vec<FontData>> = OnceLock::new();
    FALLBACKS.get_or_init(|| {
        let mut out = vec![
            fira_math().clone(),
            math_symbols().clone(),
            stix_math().clone(),
        ];
        for family in [
            "DejaVu Sans",
            "Noto Sans Symbols 2",
            "Noto Sans Symbols",
            "Noto Sans Math",
            "Segoe UI Symbol",
            "Symbola",
            "Noto Sans CJK JP",
            "Noto Sans",
            "Arial Unicode MS",
        ] {
            if let Some(found) = query(family, FaceStyle::default()) {
                out.push(found.data);
            }
        }
        out
    })
}

/// One resolved body face.
#[derive(Clone, Debug)]
pub struct ResolvedFace {
    /// The family as the font names itself (a "Helvetica" query may land on
    /// "Nimbus Sans").
    pub family: String,
    /// Distinguishes faces of one family, e.g. `ArialMT` vs `Arial-BoldMT`.
    pub postscript: String,
    pub data: FontData,
}

/// Every font a figure's text may be drawn with.
#[derive(Debug)]
pub struct Fonts {
    body: [ResolvedFace; 4],
    math_set: FontSet,
}

impl Fonts {
    /// Resolve (or fetch from cache) the fonts for a family preference list.
    pub fn resolve(families: &[String], math_set: FontSet) -> Arc<Fonts> {
        type Cache = HashMap<(Vec<String>, FontSet), Arc<Fonts>>;
        static CACHE: OnceLock<Mutex<Cache>> = OnceLock::new();
        let key = (families.to_vec(), math_set);
        let cache = CACHE.get_or_init(Default::default);
        if let Some(hit) = cache.lock().unwrap_or_else(|e| e.into_inner()).get(&key) {
            return hit.clone();
        }
        let body = FACES.map(|face| {
            families
                .iter()
                .find_map(|f| query(f, face))
                .unwrap_or_else(|| {
                    let (bytes, postscript) = bundled_face(face);
                    ResolvedFace {
                        family: "Liberation Sans".into(),
                        postscript: postscript.into(),
                        data: FontData::from_bytes(bytes.to_vec(), 0),
                    }
                })
        });
        let fonts = Arc::new(Fonts { body, math_set });
        cache
            .lock()
            .unwrap_or_else(|e| e.into_inner())
            .insert(key, fonts.clone());
        fonts
    }

    pub fn face(&self, face: FaceStyle) -> &ResolvedFace {
        &self.body[face_index(face)]
    }

    pub fn text_fallbacks(&self) -> &'static [FontData] {
        text_fallbacks()
    }

    /// The fonts a `$...$`-aware label is laid out with, `ambient` being the
    /// face its plain text and upright atoms use.
    pub fn math(&self, ambient: FaceStyle) -> MathFonts<'_> {
        let f = |bold, italic| &self.face(FaceStyle { bold, italic }).data;
        let primary = match self.math_set {
            FontSet::Sans => fira_math(),
            FontSet::Stix => stix_math(),
        };
        let fonts = MathFonts::new(
            primary,
            f(false, false),
            f(true, false),
            f(false, true),
            f(true, true),
        )
        .with_symbols(math_symbols())
        .with_ambient(ambient)
        .with_fontset(self.math_set)
        .with_text_fallbacks(text_fallbacks());
        match self.math_set {
            // STIX backs the sans math font for the alphabets it lacks.
            FontSet::Sans => fonts.with_math_fallback(stix_math()),
            FontSet::Stix => fonts,
        }
    }
}
