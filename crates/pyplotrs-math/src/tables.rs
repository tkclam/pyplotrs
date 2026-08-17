//! LaTeX command tables, ported from the original `python/pyplotrs/mathtext.py`
//! and annotated with TeX math atom *classes* (the thing the old engine
//! lacked) so the layout pass can insert correct inter-atom spacing.
//!
//! This module also decides, for every character of a span, *which face draws
//! it* — see [`place_char`].

use crate::{FaceStyle, FontSet};

/// TeX math atom class. Determines inter-atom spacing (see `spacing.rs`).
#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub enum Class {
    Ord,
    Op,
    Bin,
    Rel,
    Open,
    Close,
    Punct,
    Inner,
}

/// A math alphabet style introduced by `\mathbf`, `\mathbb`, ... `None` means
/// the default (single letters become math-italic).
#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub enum Style {
    Default,
    Rm,
    Bf,
    It,
    BfIt,
    Bb,
    Cal,
    Frak,
    Sf,
    SfBf,
    Tt,
}

/// Map a LaTeX `\name` to its Unicode character and atom class.
/// Lowercase Greek returned here is the *upright* codepoint; the caller
/// applies math-italic mapping per the default convention.
pub fn symbol(name: &str) -> Option<(char, Class)> {
    use Class::*;
    let v = match name {
        // lowercase Greek (Ord)
        "alpha" => ('α', Ord),
        "beta" => ('β', Ord),
        "gamma" => ('γ', Ord),
        "delta" => ('δ', Ord),
        "epsilon" => ('ε', Ord),
        "varepsilon" => ('ε', Ord),
        "zeta" => ('ζ', Ord),
        "eta" => ('η', Ord),
        "theta" => ('θ', Ord),
        "vartheta" => ('ϑ', Ord),
        "iota" => ('ι', Ord),
        "kappa" => ('κ', Ord),
        "lambda" => ('λ', Ord),
        "mu" => ('μ', Ord),
        "nu" => ('ν', Ord),
        "xi" => ('ξ', Ord),
        "omicron" => ('ο', Ord),
        "pi" => ('π', Ord),
        "varpi" => ('ϖ', Ord),
        "rho" => ('ρ', Ord),
        "varrho" => ('ϱ', Ord),
        "sigma" => ('σ', Ord),
        "varsigma" => ('ς', Ord),
        "tau" => ('τ', Ord),
        "upsilon" => ('υ', Ord),
        "phi" => ('φ', Ord),
        "varphi" => ('ϕ', Ord),
        "chi" => ('χ', Ord),
        "psi" => ('ψ', Ord),
        "omega" => ('ω', Ord),
        // uppercase Greek (Ord, upright)
        "Gamma" => ('Γ', Ord),
        "Delta" => ('Δ', Ord),
        "Theta" => ('Θ', Ord),
        "Lambda" => ('Λ', Ord),
        "Xi" => ('Ξ', Ord),
        "Pi" => ('Π', Ord),
        "Sigma" => ('Σ', Ord),
        "Upsilon" => ('Υ', Ord),
        "Phi" => ('Φ', Ord),
        "Psi" => ('Ψ', Ord),
        "Omega" => ('Ω', Ord),
        // binary operators
        "times" => ('×', Bin),
        "cdot" => ('⋅', Bin),
        "div" => ('÷', Bin),
        "pm" => ('±', Bin),
        "mp" => ('∓', Bin),
        "ast" => ('∗', Bin),
        "star" => ('⋆', Bin),
        "bullet" => ('∙', Bin),
        "circ" => ('∘', Bin),
        "oplus" => ('⊕', Bin),
        "ominus" => ('⊖', Bin),
        "otimes" => ('⊗', Bin),
        "oslash" => ('⊘', Bin),
        "odot" => ('⊙', Bin),
        "cup" => ('∪', Bin),
        "cap" => ('∩', Bin),
        "uplus" => ('⊎', Bin),
        "sqcup" => ('⊔', Bin),
        "sqcap" => ('⊓', Bin),
        "wedge" => ('∧', Bin),
        "land" => ('∧', Bin),
        "vee" => ('∨', Bin),
        "lor" => ('∨', Bin),
        "setminus" => ('∖', Bin),
        "wr" => ('≀', Bin),
        "diamond" => ('⋄', Bin),
        "bigtriangleup" => ('△', Bin),
        "bigtriangledown" => ('▽', Bin),
        "triangleleft" => ('◁', Bin),
        "triangleright" => ('▷', Bin),
        "dagger" => ('†', Bin),
        "ddagger" => ('‡', Bin),
        "amalg" => ('⨿', Bin),
        // relations
        "leq" => ('≤', Rel),
        "le" => ('≤', Rel),
        "geq" => ('≥', Rel),
        "ge" => ('≥', Rel),
        "neq" => ('≠', Rel),
        "ne" => ('≠', Rel),
        "equiv" => ('≡', Rel),
        "approx" => ('≈', Rel),
        "simeq" => ('≃', Rel),
        "cong" => ('≅', Rel),
        "asymp" => ('≍', Rel),
        "ll" => ('≪', Rel),
        "gg" => ('≫', Rel),
        "propto" => ('∝', Rel),
        "sim" => ('∼', Rel),
        "prec" => ('≺', Rel),
        "succ" => ('≻', Rel),
        "preceq" => ('⪯', Rel),
        "succeq" => ('⪰', Rel),
        "subset" => ('⊂', Rel),
        "supset" => ('⊃', Rel),
        "subseteq" => ('⊆', Rel),
        "supseteq" => ('⊇', Rel),
        "sqsubseteq" => ('⊑', Rel),
        "sqsupseteq" => ('⊒', Rel),
        "in" => ('∈', Rel),
        "notin" => ('∉', Rel),
        "ni" => ('∋', Rel),
        "owns" => ('∋', Rel),
        "perp" => ('⊥', Rel),
        "parallel" => ('∥', Rel),
        "mid" => ('∣', Rel),
        "models" => ('⊨', Rel),
        "vdash" => ('⊢', Rel),
        "dashv" => ('⊣', Rel),
        "doteq" => ('≐', Rel),
        "bowtie" => ('⋈', Rel),
        // arrows (relations)
        "rightarrow" => ('→', Rel),
        "to" => ('→', Rel),
        "gets" => ('←', Rel),
        "leftarrow" => ('←', Rel),
        "leftrightarrow" => ('↔', Rel),
        "mapsto" => ('↦', Rel),
        "Rightarrow" => ('⇒', Rel),
        "Leftarrow" => ('⇐', Rel),
        "Leftrightarrow" => ('⇔', Rel),
        "uparrow" => ('↑', Rel),
        "downarrow" => ('↓', Rel),
        "updownarrow" => ('↕', Rel),
        "nearrow" => ('↗', Rel),
        "searrow" => ('↘', Rel),
        "swarrow" => ('↙', Rel),
        "nwarrow" => ('↖', Rel),
        "hookrightarrow" => ('↪', Rel),
        "hookleftarrow" => ('↩', Rel),
        "longrightarrow" => ('⟶', Rel),
        "longleftarrow" => ('⟵', Rel),
        "Longrightarrow" => ('⟹', Rel),
        // big operators
        "sum" => ('∑', Op),
        "prod" => ('∏', Op),
        "coprod" => ('∐', Op),
        "int" => ('∫', Op),
        "oint" => ('∮', Op),
        "iint" => ('∬', Op),
        "iiint" => ('∭', Op),
        "bigcup" => ('⋃', Op),
        "bigcap" => ('⋂', Op),
        "bigoplus" => ('⨁', Op),
        "bigotimes" => ('⨂', Op),
        "bigodot" => ('⨀', Op),
        "bigvee" => ('⋁', Op),
        "bigwedge" => ('⋀', Op),
        "biguplus" => ('⨄', Op),
        "bigsqcup" => ('⨆', Op),
        // open / close delimiters
        "langle" => ('⟨', Open),
        "rangle" => ('⟩', Close),
        "lfloor" => ('⌊', Open),
        "rfloor" => ('⌋', Close),
        "lceil" => ('⌈', Open),
        "rceil" => ('⌉', Close),
        // punctuation
        "ldots" => ('…', Punct),
        "dots" => ('…', Inner),
        "cdots" => ('⋯', Inner),
        "vdots" => ('⋮', Inner),
        "ddots" => ('⋱', Inner),
        // ordinary symbols
        "infty" => ('∞', Ord),
        "partial" => ('∂', Ord),
        "nabla" => ('∇', Ord),
        "forall" => ('∀', Ord),
        "exists" => ('∃', Ord),
        "nexists" => ('∄', Ord),
        "neg" => ('¬', Ord),
        "lnot" => ('¬', Ord),
        "emptyset" => ('∅', Ord),
        "varnothing" => ('∅', Ord),
        "hbar" => ('ℏ', Ord),
        "hslash" => ('ℏ', Ord),
        "ell" => ('ℓ', Ord),
        "Re" => ('ℜ', Ord),
        "Im" => ('ℑ', Ord),
        "aleph" => ('ℵ', Ord),
        "beth" => ('ℶ', Ord),
        "wp" => ('℘', Ord),
        "angle" => ('∠', Ord),
        "measuredangle" => ('∡', Ord),
        "degree" => ('°', Ord),
        "prime" => ('′', Ord),
        "surd" => ('√', Ord),
        "top" => ('⊤', Ord),
        "bot" => ('⊥', Ord),
        "flat" => ('♭', Ord),
        "natural" => ('♮', Ord),
        "sharp" => ('♯', Ord),
        "clubsuit" => ('♣', Ord),
        "diamondsuit" => ('♢', Ord),
        "heartsuit" => ('♡', Ord),
        "spadesuit" => ('♠', Ord),
        "Box" => ('□', Ord),
        "triangle" => ('△', Ord),
        "checkmark" => ('✓', Ord),
        _ => return None,
    };
    Some(v)
}

/// Spacing command (`\,` `\:` `\;` `\!` `\quad` `\qquad` and literal space) →
/// width as a fraction of the font size (em). Negative for `\!`.
pub fn space_em(name: &str) -> Option<f32> {
    Some(match name {
        "," => 0.16667,
        ":" => 0.22222,
        ";" => 0.27778,
        "!" => -0.16667,
        " " => 0.25,
        "quad" => 1.0,
        "qquad" => 2.0,
        _ => return None,
    })
}

/// Function names that render upright (and behave as `\mathop`): `\sin`, ...
pub fn is_function_name(name: &str) -> bool {
    matches!(
        name,
        "sin"
            | "cos"
            | "tan"
            | "cot"
            | "sec"
            | "csc"
            | "sinh"
            | "cosh"
            | "tanh"
            | "coth"
            | "log"
            | "ln"
            | "lg"
            | "exp"
            | "lim"
            | "limsup"
            | "liminf"
            | "max"
            | "min"
            | "sup"
            | "inf"
            | "det"
            | "gcd"
            | "deg"
            | "dim"
            | "hom"
            | "ker"
            | "arg"
            | "Pr"
            | "arcsin"
            | "arccos"
            | "arctan"
            | "argmax"
            | "argmin"
    )
}

/// Accent command → (kind, stretches-to-width). Drawn as small vector marks.
pub fn accent(name: &str) -> Option<(&'static str, bool)> {
    let wide = matches!(name, "bar" | "overline" | "vec" | "widehat" | "widetilde");
    let kind = match name {
        "hat" | "widehat" => "hat",
        "check" => "check",
        "tilde" | "widetilde" => "tilde",
        "acute" => "acute",
        "grave" => "grave",
        "dot" => "dot",
        "ddot" => "ddot",
        "breve" => "breve",
        "bar" | "overline" => "bar",
        "vec" => "vec",
        _ => return None,
    };
    Some((kind, wide))
}

/// Delimiter token after `\left`/`\right`. `.` means "no delimiter".
pub fn delimiter(tok: &str) -> Option<char> {
    Some(match tok {
        "(" => '(',
        ")" => ')',
        "[" => '[',
        "]" => ']',
        "|" => '|',
        "/" => '/',
        "." => '.',
        "{" | "lbrace" => '{',
        "}" | "rbrace" => '}',
        "langle" => '⟨',
        "rangle" => '⟩',
        "lfloor" => '⌊',
        "rfloor" => '⌋',
        "lceil" => '⌈',
        "rceil" => '⌉',
        "vert" => '|',
        "Vert" => '‖',
        "backslash" => '\\',
        "uparrow" => '↑',
        "downarrow" => '↓',
        _ => return None,
    })
}

/// Map a Latin or Greek letter to its Mathematical-Italic codepoint, matching
/// the matplotlib/LaTeX default (variables look like italic math). Digits,
/// operators, punctuation and uppercase Greek pass through upright.
pub fn math_italic(c: char) -> char {
    let o = c as u32;
    match o {
        0x41..=0x5A => char::from_u32(0x1D434 + (o - 0x41)).unwrap(), // A-Z
        0x68 => 'ℎ',                                                  // italic h (U+210E)
        0x61..=0x7A => char::from_u32(0x1D44E + (o - 0x61)).unwrap(), // a-z
        0x3B1..=0x3C9 => char::from_u32(0x1D6FC + (o - 0x3B1)).unwrap(), // α-ω
        _ => c,
    }
}

// Letterlike-block "holes" in the Mathematical Alphanumeric Symbols ranges.
fn bb_exc(c: char) -> Option<char> {
    Some(match c {
        'C' => 'ℂ',
        'H' => 'ℍ',
        'N' => 'ℕ',
        'P' => 'ℙ',
        'Q' => 'ℚ',
        'R' => 'ℝ',
        'Z' => 'ℤ',
        _ => return None,
    })
}
fn script_exc(c: char) -> Option<char> {
    Some(match c {
        'B' => 'ℬ',
        'E' => 'ℰ',
        'F' => 'ℱ',
        'H' => 'ℋ',
        'I' => 'ℐ',
        'L' => 'ℒ',
        'M' => 'ℳ',
        'R' => 'ℛ',
        'e' => 'ℯ',
        'g' => 'ℊ',
        'o' => 'ℴ',
        _ => return None,
    })
}
fn fraktur_exc(c: char) -> Option<char> {
    Some(match c {
        'C' => 'ℭ',
        'H' => 'ℌ',
        'I' => 'ℑ',
        'R' => 'ℜ',
        'Z' => 'ℨ',
        _ => return None,
    })
}

/// A math alphabet's mapping: the Unicode base codepoints for uppercase,
/// lowercase and digits (0 when the style has no digit block), plus a lookup for
/// the characters Unicode placed outside the contiguous block (the "holes" in
/// e.g. Script and Fraktur).
type AlphabetMap = (u32, u32, u32, fn(char) -> Option<char>);

/// Map one character to its codepoint under the active math alphabet style.
pub fn styled_char(c: char, style: Style) -> char {
    let (up, lo, dig, exc): AlphabetMap = match style {
        Style::Default | Style::It => return math_italic(c),
        Style::Rm => return c,
        Style::Bf => (0x1D400, 0x1D41A, 0x1D7CE, |_| None),
        Style::BfIt => (0x1D468, 0x1D482, 0, |_| None),
        Style::Bb => (0x1D538, 0x1D552, 0x1D7D8, bb_exc),
        Style::Cal => (0x1D49C, 0x1D4B6, 0, script_exc),
        Style::Frak => (0x1D504, 0x1D51E, 0, fraktur_exc),
        Style::Sf => (0x1D5A0, 0x1D5BA, 0x1D7E2, |_| None),
        Style::SfBf => (0x1D5D4, 0x1D5EE, 0x1D7EC, |_| None),
        Style::Tt => (0x1D670, 0x1D68A, 0x1D7F6, |_| None),
    };
    if let Some(e) = exc(c) {
        return e;
    }
    let o = c as u32;
    match o {
        0x41..=0x5A => char::from_u32(up + (o - 0x41)).unwrap(),
        0x61..=0x7A => char::from_u32(lo + (o - 0x61)).unwrap(),
        0x30..=0x39 if dig != 0 => char::from_u32(dig + (o - 0x30)).unwrap(),
        _ => c,
    }
}

/// Math alphabet command (`\mathbf`, ...) → style. `\operatorname` maps to Rm.
pub fn alphabet_style(name: &str) -> Option<Style> {
    Some(match name {
        "mathrm" | "operatorname" | "text" => Style::Rm,
        "mathbf" => Style::Bf,
        "mathit" => Style::It,
        "mathbfit" => Style::BfIt,
        "mathbb" => Style::Bb,
        "mathcal" | "mathscr" => Style::Cal,
        "mathfrak" => Style::Frak,
        "mathsf" => Style::Sf,
        "mathsfbf" => Style::SfBf,
        "mathtt" => Style::Tt,
        _ => return None,
    })
}

/// The substitution every literal math character gets before anything else:
/// ASCII `-` is a real minus sign, `*` a real asterisk operator. Both are
/// typographic, not stylistic, so they happen whatever face ends up drawing.
pub fn literal_char(c: char) -> char {
    match c {
        '-' => '−', // U+2212 MINUS SIGN
        '*' => '∗', // U+2217 ASTERISK OPERATOR
        _ => c,
    }
}

/// Which face a character is drawn from, and as which codepoint.
///
/// The two travel together because they are one decision: a variable set in the
/// body face is the plain letter `x` in an italic face, and the *same* variable
/// set in the math font is U+1D465 in an upright one. Picking a codepoint first
/// and a face afterwards is what made `$E = mc^2$` mix serif letters with sans
/// digits.
#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub enum Placement {
    /// Draw `ch` from the body face `face`. The caller must check that the face
    /// actually has the glyph and fall back to [`Placement::Math`] if not.
    Body { ch: char, face: FaceStyle },
    /// Draw `ch` from a math face.
    ///
    /// `symbol` is true when `ch` is a standalone mark — an operator, relation,
    /// arrow or letterlike sign — whose design should match the text around it,
    /// so the sans symbol face may draw it before the math font is asked. It is
    /// false for a letter of a math alphabet (`\mathbb`, `\mathfrak`, the
    /// Mathematical-Italic variables), where the distinct design *is* the point
    /// and only the math font has it.
    Math { ch: char, symbol: bool },
}

/// Whether `c` is a letter that stands for a variable - Latin or Greek. These
/// are the characters whose *shape* a reader reads as belonging to the
/// surrounding text, which is why they follow the body family when it has them.
fn is_variable_letter(c: char) -> bool {
    matches!(c,
        'A'..='Z' | 'a'..='z'
            | '\u{0391}'..='\u{03A9}'   // Α-Ω
            | '\u{03B1}'..='\u{03C9}'   // α-ω
            | '\u{03D1}' | '\u{03D5}' | '\u{03D6}'  // ϑ ϕ ϖ
            | '\u{03F0}' | '\u{03F1}' | '\u{03F5}'  // ϰ ϱ ϵ
    )
}

/// Whether a *non-letter* math atom can be set in the body face.
///
/// A reader compares a math label against the plain ones beside it, not against
/// itself: a tick reading `10^{-3}` sits in a column with ticks reading `50` and
/// `100`, and the digits must not change typeface between them. The bundled
/// math font is STIX Two Math, a serif, so every digit that reached it used to
/// come out Times-like next to sans labels.
///
/// Listed here are the characters a text face reliably carries *and* that gain
/// nothing from math shaping. Big operators, radicals and fences are absent on
/// purpose even though a text font has `∑ ∫ √`: those are grown through the
/// MATH table's variant and assembly chains, which only the math font has, so a
/// text copy of them would be a fixed-size glyph that cannot stretch. The
/// arrows, relations and letterlike symbols here are drawn at one size and
/// stretch nothing, so the body face's are as good and match their neighbors.
///
/// The list stays *short* on purpose. Anything not here that the body family
/// happens to carry is drawn by the sans symbol face instead, which has the
/// whole block — and one font per symbol family reads better than a body-face
/// `≤` beside a symbol-face `≪`. What earns a place here is being a character
/// of ordinary text as much as of math, common enough that matching the label's
/// own typeface exactly is worth more than matching the rarer relation two
/// symbols along.
///
/// Coverage is still verified against the resolved face before use, so a body
/// family missing any of these moves down the chain rather than drawing
/// `.notdef`.
#[rustfmt::skip]
fn body_face_symbol(c: char) -> bool {
    matches!(c,
        '0'..='9'
            | '.' | ',' | ':' | ';' | '!' | '?' | '\'' | '\\'
            | '+' | '−' | '±' | '×' | '·' | '÷' | '/' | '%' | '¬'
            | '=' | '<' | '>' | '≤' | '≥' | '≠' | '≈' | '≡'
            | '(' | ')' | '[' | ']' | '|'
            | '∂' | '∞' | '°' | '′' | '″' | '…'
            | '→' | '←' | '↔'
    )
}

/// The body face a span sets `style` in, given its ambient face - or `None`
/// when the style names an alphabet only the math font has (blackboard, script,
/// Fraktur, monospace, and the Unicode sans blocks that stay stable regardless
/// of what the body family happens to be).
fn body_face_for_style(style: Style, ambient: FaceStyle) -> Option<FaceStyle> {
    Some(match style {
        // Variables lean; the weight is whatever the label around them is, so a
        // bold title's math comes out bold instead of half-bold.
        Style::Default | Style::It => FaceStyle {
            bold: ambient.bold,
            italic: true,
        },
        Style::Rm => ambient,
        Style::Bf => FaceStyle {
            bold: true,
            italic: false,
        },
        Style::BfIt => FaceStyle {
            bold: true,
            italic: true,
        },
        Style::Bb | Style::Cal | Style::Frak | Style::Sf | Style::SfBf | Style::Tt => return None,
    })
}

/// Decide the codepoint and face for `c` under alphabet `style`.
///
/// Under [`FontSet::Sans`] the body family draws whatever it can - letters,
/// Greek, digits, and the operators of [`body_face_symbol`] - and the math font
/// supplies the rest. Under [`FontSet::Stix`] every atom comes from the math
/// font, so a span is uniformly serif.
pub fn place_char(c: char, style: Style, ambient: FaceStyle, fontset: FontSet) -> Placement {
    if fontset == FontSet::Stix {
        // Uniformly serif: the sans symbol face is not consulted either.
        return Placement::Math {
            ch: styled_char(c, style),
            symbol: false,
        };
    }
    // A mark is a *symbol* when no alphabet claims it: the styling left it
    // alone and it is not a letter. `∇` and `⇒` qualify; `x`, `α` and the
    // `\mathbb{R}` that `styled_char` turned into `ℝ` do not.
    let math = || Placement::Math {
        ch: styled_char(c, style),
        symbol: styled_char(c, style) == c && !is_variable_letter(c),
    };
    let Some(face) = body_face_for_style(style, ambient) else {
        return math();
    };
    if is_variable_letter(c) {
        // Uppercase Greek is upright in the default alphabet (TeX sets `\Gamma`
        // roman and `\gamma` italic), and `math_italic` is the existing record
        // of which characters lean - so ask it rather than restate the rule.
        let face = if matches!(style, Style::Default | Style::It) && math_italic(c) == c {
            FaceStyle {
                bold: face.bold,
                italic: false,
            }
        } else {
            face
        };
        return Placement::Body { ch: c, face };
    }
    if body_face_symbol(c) {
        // Digits and operators are upright under every alphabet; only the weight
        // carries over, so `\mathbf{2}` is a bold 2 and `x_2` an ordinary one.
        return Placement::Body {
            ch: c,
            face: FaceStyle {
                bold: face.bold,
                italic: false,
            },
        };
    }
    math()
}

/// Default class for a literal (non-command) character.
pub fn char_class(c: char) -> Class {
    match c {
        '+' | '-' | '*' => Class::Bin,
        '=' | '<' | '>' => Class::Rel,
        '(' | '[' => Class::Open,
        ')' | ']' | '!' => Class::Close,
        ',' | ';' => Class::Punct,
        '/' | '|' => Class::Ord,
        _ => Class::Ord,
    }
}
