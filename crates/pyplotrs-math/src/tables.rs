//! LaTeX command tables, ported from the original `python/pyplotrs/mathtext.py`
//! and annotated with TeX math atom *classes* (the thing the old engine
//! lacked) so the layout pass can insert correct inter-atom spacing.

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

/// Displayed codepoint for a literal (non-command) math character under the
/// active alphabet `style`: ASCII `-` becomes a real minus sign (U+2212),
/// otherwise the character is mapped through the alphabet (letters → math
/// italic by default; digits/operators upright).
pub fn styled_char_for_literal(c: char, style: Style) -> char {
    match c {
        '-' => '−', // U+2212 MINUS SIGN
        '*' => '∗', // U+2217 ASTERISK OPERATOR
        _ => styled_char(c, style),
    }
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
