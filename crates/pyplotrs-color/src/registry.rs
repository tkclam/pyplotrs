//! Lookup over the embedded colormap/palette data (see [`crate::data`]).

use crate::data::{categorical_gen::CATEGORICAL, registry_gen::CONTINUOUS, CONTINUOUS_BLOB};

/// Where a colormap/palette's data was sourced from.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Source {
    Matplotlib,
    Colorcet,
    Cmocean,
    Seaborn,
}

/// The perceptual/structural family a *continuous* colormap belongs to.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Category {
    PerceptuallyUniform,
    Sequential,
    Diverging,
    Cyclic,
    Miscellaneous,
}

impl Category {
    pub fn as_str(self) -> &'static str {
        match self {
            Category::PerceptuallyUniform => "perceptually_uniform",
            Category::Sequential => "sequential",
            Category::Diverging => "diverging",
            Category::Cyclic => "cyclic",
            Category::Miscellaneous => "miscellaneous",
        }
    }

    fn parse(s: &str) -> Option<Category> {
        Some(match s {
            "perceptually_uniform" => Category::PerceptuallyUniform,
            "sequential" => Category::Sequential,
            "diverging" => Category::Diverging,
            "cyclic" => Category::Cyclic,
            "miscellaneous" => Category::Miscellaneous,
            _ => return None,
        })
    }
}

pub struct ContinuousEntry {
    pub name: &'static str,
    pub offset: usize,
    pub category: Category,
    pub source: Source,
}

pub struct CategoricalEntry {
    pub name: &'static str,
    pub colors: &'static [[u8; 3]],
    pub source: Source,
}

fn find_continuous(name: &str) -> Option<&'static ContinuousEntry> {
    CONTINUOUS.iter().find(|e| e.name == name)
}

/// Read a continuous colormap's exact 256-entry RGB table, honoring a
/// trailing `_r` (reversed) suffix the way every named map in pyplotrs
/// supports it.
pub fn continuous_table(name: &str) -> Option<[[u8; 3]; 256]> {
    if let Some(entry) = find_continuous(name) {
        return Some(read_table(entry.offset));
    }
    let base = name.strip_suffix("_r")?;
    let entry = find_continuous(base)?;
    let mut table = read_table(entry.offset);
    table.reverse();
    Some(table)
}

fn read_table(offset: usize) -> [[u8; 3]; 256] {
    let bytes = &CONTINUOUS_BLOB[offset..offset + 256 * 3];
    let mut table = [[0u8; 3]; 256];
    for (i, chunk) in bytes.chunks_exact(3).enumerate() {
        table[i] = [chunk[0], chunk[1], chunk[2]];
    }
    table
}

/// `(category, source)` for a continuous colormap name (ignoring any `_r`
/// suffix - a reversed map has the same category/source as its base).
pub fn continuous_meta(name: &str) -> Option<(Category, Source)> {
    let base = name.strip_suffix("_r").unwrap_or(name);
    find_continuous(base).map(|e| (e.category, e.source))
}

/// Names of every built-in continuous colormap (no `_r` variants listed -
/// every name here also works with `_r` appended), optionally filtered to
/// one category.
pub fn list_continuous(category: Option<&str>) -> Vec<&'static str> {
    let want = category.map(Category::parse);
    CONTINUOUS
        .iter()
        .filter(|e| match want {
            Some(Some(c)) => e.category == c,
            Some(None) => false, // unrecognized category name -> no matches
            None => true,
        })
        .map(|e| e.name)
        .collect()
}

/// A categorical/qualitative palette's colors by name.
pub fn categorical_palette(name: &str) -> Option<&'static [[u8; 3]]> {
    CATEGORICAL.iter().find(|e| e.name == name).map(|e| e.colors)
}

/// Names of every built-in categorical/qualitative palette.
pub fn list_categorical() -> Vec<&'static str> {
    CATEGORICAL.iter().map(|e| e.name).collect()
}
