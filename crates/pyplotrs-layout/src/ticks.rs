//! Tick location and formatting.
//!
//! This is a focused port of the ideas behind matplotlib's `MaxNLocator` /
//! `AutoLocator`: choose a "nice" tick step from the set {1, 2, 2.5, 5} × 10ⁿ
//! such that the number of ticks across `[vmin, vmax]` does not exceed a
//! target, then place ticks on integer multiples of that step. Producing
//! round tick values (and knowing the step) is what lets the layout engine
//! pre-measure tick-label extents before solving the figure layout.

/// The canonical "nice" step multipliers, in increasing order. These are the
/// same candidate steps matplotlib's `MaxNLocator` uses by default.
const NICE_STEPS: [f64; 4] = [1.0, 2.0, 2.5, 5.0];

/// A located axis tick: its data value plus a formatted label string.
#[derive(Debug, Clone, PartialEq)]
pub struct Tick {
    pub value: f64,
    pub label: String,
}

/// Choose a "nice" tick step for `[vmin, vmax]` aiming for at most `max_ticks`
/// ticks. Considers each candidate in [`NICE_STEPS`] (× 10ⁿ) and picks the
/// smallest step that keeps the tick count within budget.
pub fn nice_step(vmin: f64, vmax: f64, max_ticks: usize) -> f64 {
    let span = (vmax - vmin).abs();
    if span == 0.0 || !span.is_finite() {
        return 1.0;
    }
    let max_ticks = max_ticks.max(2);
    let raw = span / (max_ticks as f64);
    // Base magnitude just below `raw`.
    let mag = 10f64.powf(raw.log10().floor());
    for &mult in NICE_STEPS.iter() {
        let step = mult * mag;
        if span / step <= (max_ticks - 1) as f64 + 1e-9 {
            return step;
        }
    }
    // Fall back to the next magnitude up.
    10.0 * mag
}

/// Locate tick *values* on multiples of a nice step within `[vmin, vmax]`.
pub fn tick_values(vmin: f64, vmax: f64, max_ticks: usize) -> Vec<f64> {
    let (lo, hi) = if vmin <= vmax {
        (vmin, vmax)
    } else {
        (vmax, vmin)
    };
    if !(lo.is_finite() && hi.is_finite()) {
        return vec![lo];
    }
    if lo == hi {
        return vec![lo];
    }
    let step = nice_step(lo, hi, max_ticks);
    // First multiple of `step` at or above `lo`, with a tiny epsilon so values
    // a hair below a tick (from float error) still register.
    let eps = step * 1e-9;
    let first = ((lo - eps) / step).ceil();
    let last = ((hi + eps) / step).floor();
    let n = (last - first) as i64;
    if n < 0 {
        return vec![lo, hi];
    }
    let mut out = Vec::with_capacity((n + 1) as usize);
    let mut k = first;
    while k <= last + 0.5 {
        // `k * step` accumulates float noise, which is worth erasing so that
        // ticks come out as the round numbers they are. Erase it *relative to
        // the value*, never to a fixed number of decimal places: quantizing a
        // tick to the precision of its own label is how an axis spanning less
        // than 1e-6 used to collapse - every tick rounded to the same number,
        // so five ticks all sat on 0 and all read "0". Labels may be as coarse
        // as they like; the values they point at may not.
        let v = round_significant(k * step, TICK_VALUE_SIG_DIGITS);
        out.push(if v == 0.0 { 0.0 } else { v }); // normalize -0.0
        k += 1.0;
    }
    out
}

/// Significant decimal digits kept in a located tick value. Comfortably below
/// f64's ~15-17, so accumulated `k * step` noise is erased, and comfortably
/// above anything a real axis needs, so nothing is lost.
const TICK_VALUE_SIG_DIGITS: i32 = 12;

/// Most decimal places [`decimals_for_step`] will ask a label to carry. f64
/// runs out of significant digits before this matters for any real axis; the
/// cap exists so a pathological step cannot generate an unbounded string.
const MAX_TICK_DECIMALS: usize = 17;

/// Round `v` to `sig` significant decimal digits (scale-free, unlike rounding
/// to a fixed number of decimal *places*).
fn round_significant(v: f64, sig: i32) -> f64 {
    if v == 0.0 || !v.is_finite() {
        return v;
    }
    let mag = v.abs().log10().floor() as i32;
    let f = 10f64.powi(sig - 1 - mag);
    if !f.is_finite() || f == 0.0 {
        return v;
    }
    (v * f).round() / f
}

/// Number of decimal places needed to render `step` (and therefore all of its
/// integer multiples) exactly. Handles the 2.5-style "half" steps correctly,
/// e.g. a step of 0.25 needs 2 decimals, not 1.
fn decimals_for_step(step: f64) -> usize {
    let s = step.abs();
    if s == 0.0 || !s.is_finite() {
        return 0;
    }
    for d in 0..=MAX_TICK_DECIMALS {
        let scaled = s * 10f64.powi(d as i32);
        // Two conditions, and the first one is the one that used to be
        // missing. `scaled` has to have reached the leading digit before it
        // can be called whole - otherwise every step below the old absolute
        // 1e-6 tolerance answered "0 decimals" at d = 0, because a small
        // enough number is indistinguishable from the integer zero. The
        // tolerance is relative to `scaled` for the same reason.
        if scaled >= 1.0 - 1e-9 && (scaled - scaled.round()).abs() < 1e-6 * scaled {
            return d;
        }
    }
    MAX_TICK_DECIMALS
}

/// Format a single tick `value` given the tick `step` (which fixes the number
/// of decimal places so all labels on an axis are consistent).
///
/// The sign is an ASCII `-`, not U+2212: this is a pure function with no view
/// of the display setting, so swapping in a real minus is the Python locator
/// wrapper's job (`scales.nice_ticks`). Keep it ASCII - the `-0` guard below
/// slices by byte and a multi-byte sign would cut mid-character.
pub fn format_tick(value: f64, step: f64) -> String {
    let decimals = decimals_for_step(step);
    let v = if value == 0.0 { 0.0 } else { value }; // normalize -0.0
    let mut s = format!("{v:.decimals$}");
    // Guard against "-0" from rounding.
    if s.starts_with("-0") && s[1..].chars().all(|c| c == '0' || c == '.') {
        s = s[1..].to_string();
    }
    s
}

/// Locate ticks and format their labels in one call - the typical entry point.
pub fn ticks(vmin: f64, vmax: f64, max_ticks: usize) -> Vec<Tick> {
    let values = tick_values(vmin, vmax, max_ticks);
    let step = nice_step(vmin.min(vmax), vmax.max(vmin), max_ticks);
    values
        .into_iter()
        .map(|value| Tick {
            value,
            label: format_tick(value, step),
        })
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    fn vals(vmin: f64, vmax: f64, n: usize) -> Vec<f64> {
        tick_values(vmin, vmax, n)
    }

    #[test]
    fn simple_unit_range() {
        assert_eq!(vals(0.0, 1.0, 6), vec![0.0, 0.2, 0.4, 0.6, 0.8, 1.0]);
    }

    #[test]
    fn integer_range() {
        assert_eq!(vals(0.0, 10.0, 6), vec![0.0, 2.0, 4.0, 6.0, 8.0, 10.0]);
    }

    #[test]
    fn nonzero_start() {
        // 3..97 with ~6 ticks -> step 20 -> 20,40,60,80
        let t = vals(3.0, 97.0, 6);
        assert_eq!(t, vec![20.0, 40.0, 60.0, 80.0]);
    }

    #[test]
    fn labels_are_consistent() {
        let t = ticks(0.0, 1.0, 6);
        let labels: Vec<_> = t.iter().map(|t| t.label.clone()).collect();
        assert_eq!(labels, vec!["0.0", "0.2", "0.4", "0.6", "0.8", "1.0"]);
    }

    #[test]
    fn quarter_step_keeps_two_decimals() {
        // span 1 with max 5 ticks -> step 0.25, which must format with 2
        // decimals (a step of 0.25 truncated to 1 decimal would read "0.2").
        let t = ticks(0.0, 1.0, 5);
        let labels: Vec<_> = t.iter().map(|t| t.label.clone()).collect();
        assert_eq!(labels, vec!["0.00", "0.25", "0.50", "0.75", "1.00"]);
    }

    #[test]
    fn degenerate_range() {
        assert_eq!(vals(5.0, 5.0, 6), vec![5.0]);
    }

    #[test]
    fn negative_range() {
        assert_eq!(vals(-1.0, 1.0, 6), vec![-1.0, -0.5, 0.0, 0.5, 1.0]);
    }

    /// A sub-microsecond / nanometer / picoamp axis. This used to return five
    /// copies of 0.0 labeled "0": `decimals_for_step` answered 0 for any step
    /// below its absolute 1e-6 tolerance, and the tick *values* were then
    /// rounded to that. The axis silently stopped carrying a scale.
    #[test]
    fn a_tiny_span_keeps_distinct_ticks() {
        for &(lo, hi) in &[(0.0, 1e-6), (0.0, 1e-9), (0.0, 1e-12)] {
            let t = ticks(lo, hi, 6);
            assert!(t.len() >= 2, "span {hi} located {} ticks", t.len());

            let values: Vec<f64> = t.iter().map(|t| t.value).collect();
            for w in values.windows(2) {
                assert!(
                    w[1] > w[0],
                    "span {hi} located non-increasing ticks: {values:?}"
                );
            }
            assert!(
                values.last().unwrap() > &0.0,
                "span {hi} collapsed every tick onto {values:?}"
            );

            let labels: Vec<String> = t.iter().map(|t| t.label.clone()).collect();
            let unique: std::collections::HashSet<&String> = labels.iter().collect();
            assert_eq!(
                unique.len(),
                labels.len(),
                "span {hi} produced duplicate labels: {labels:?}"
            );
        }
    }

    /// The same collapse away from the origin: `[1.0, 1.0000005]` used to
    /// round every tick to 1.0 and label them all "1".
    #[test]
    fn a_tiny_span_far_from_zero_keeps_distinct_ticks() {
        let t = ticks(1.0, 1.0000005, 6);
        let labels: Vec<String> = t.iter().map(|t| t.label.clone()).collect();
        let unique: std::collections::HashSet<&String> = labels.iter().collect();
        assert_eq!(unique.len(), labels.len(), "duplicate labels: {labels:?}");
        assert!(t.iter().any(|t| t.value > 1.0), "every tick sat on 1.0");
    }

    /// Values stay exact multiples of the step: the noise-erasing round is
    /// relative to the value, so it may never move a tick off its step.
    #[test]
    fn rounding_erases_noise_without_moving_a_tick() {
        for &(lo, hi) in &[(0.0, 1.0), (0.0, 1e-9), (-3.0, 7.0), (1e6, 1e6 + 10.0)] {
            let step = nice_step(lo, hi, 6);
            for v in tick_values(lo, hi, 6) {
                let k = v / step;
                assert!(
                    (k - k.round()).abs() < 1e-6,
                    "tick {v} is not a multiple of step {step}"
                );
            }
        }
    }

    #[test]
    fn decimals_track_the_step_at_every_magnitude() {
        assert_eq!(decimals_for_step(1.0), 0);
        assert_eq!(decimals_for_step(2.0), 0);
        assert_eq!(decimals_for_step(200.0), 0);
        assert_eq!(decimals_for_step(0.5), 1);
        assert_eq!(decimals_for_step(0.25), 2);
        assert_eq!(decimals_for_step(2e-7), 7);
        assert_eq!(decimals_for_step(2.5e-9), 10);
    }
}
