//! A PNG writer whose two expensive stages both run in parallel.
//!
//! Encoding a plot dominates its own export: on an ink-heavy figure the DEFLATE
//! pass costs more than the rasterization that produced the pixels. Both stages
//! parallelize cleanly, so this module does the container by hand rather than
//! going through `png`'s single-threaded writer:
//!
//! 1. **Filtering.** Each scanline's filter needs only the *unfiltered* bytes of
//!    the row above, which we already hold, so rows are filtered independently.
//! 2. **Compression.** The filtered stream is cut into chunks that are deflated
//!    independently; every chunk but the last ends in a sync flush (an empty
//!    stored block), which byte-aligns it so the pieces concatenate into one
//!    valid DEFLATE stream. This is the trick `pigz` uses.
//!
//! Chunking costs some ratio, since each chunk restarts LZ77 with an empty
//! window and emits its own Huffman tables - about 30 bytes per chunk. Measured
//! against the `png` crate on 1200x900 test images, the whole encoder comes out
//! at **+6.8%** on a nearly-empty plot (446 bytes on a 6.5 KB file), **+0.4%**
//! on a gradient, and **-25%** on a dense one, where the adaptive filtering here
//! beats what `png` picks. Dense output is where PNG size actually matters, so
//! that trade is a good one; `pigz` would recover the rest by priming each chunk
//! with the preceding 32 KB, but `flate2::Compress::set_dictionary` needs a
//! C-zlib or `zlib-rs` backend, and enabling one would unify flate2's features
//! across the workspace and change krilla's PDF output as a side effect.
//!
//! The output is an ordinary, spec-conformant PNG; nothing here changes the
//! pixels, and the result is deterministic and machine-independent (the chunking
//! depends only on the data length, never on the core count).

use flate2::{Compress, Compression, FlushCompress, Status};
use rayon::prelude::*;

/// Bytes per pixel for the RGBA8 images this module writes.
const BPP: usize = 4;
/// zlib compression level. Matches what the `png` crate's default does, so
/// output size stays comparable; the speed comes from parallelism, not from
/// compressing less hard.
const LEVEL: u32 = 6;
/// How much of the filtered stream each parallel DEFLATE chunk takes. Large
/// enough that restarting LZ77 (a 32 KB window) costs little ratio, small enough
/// that a few-megapixel image yields many more chunks than there are cores, so
/// rayon can balance them.
const DEFLATE_CHUNK: usize = 256 * 1024;

/// Encode straight (non-premultiplied) RGBA8 `rgba` as a PNG.
///
/// `ppu` is the physical resolution in pixels per metre, written as a `pHYs`
/// chunk so consumers such as LaTeX's `\includegraphics` place the image at its
/// intended physical size.
pub fn encode_rgba8(rgba: &[u8], width: u32, height: u32, ppu: u32) -> Result<Vec<u8>, String> {
    let stride = (width as usize)
        .checked_mul(BPP)
        .ok_or_else(|| format!("image row of {width} px overflows"))?;
    if rgba.len() != stride * height as usize {
        return Err(format!(
            "pixel buffer is {} bytes, expected {} for {width} x {height}",
            rgba.len(),
            stride * height as usize
        ));
    }

    let filtered = filter_scanlines(rgba, stride, height as usize);
    let zlib = deflate_parallel(&filtered);

    let mut out = Vec::with_capacity(zlib.len() + 128);
    out.extend_from_slice(b"\x89PNG\r\n\x1a\n");

    let mut ihdr = Vec::with_capacity(13);
    ihdr.extend_from_slice(&width.to_be_bytes());
    ihdr.extend_from_slice(&height.to_be_bytes());
    ihdr.extend_from_slice(&[8, 6, 0, 0, 0]); // 8-bit, RGBA, deflate, adaptive filtering, no interlace
    write_chunk(&mut out, b"IHDR", &ihdr);

    let mut phys = Vec::with_capacity(9);
    phys.extend_from_slice(&ppu.to_be_bytes());
    phys.extend_from_slice(&ppu.to_be_bytes());
    phys.push(1); // unit: metre
    write_chunk(&mut out, b"pHYs", &phys);

    write_chunk(&mut out, b"IDAT", &zlib);
    write_chunk(&mut out, b"IEND", &[]);
    Ok(out)
}

fn write_chunk(out: &mut Vec<u8>, kind: &[u8; 4], data: &[u8]) {
    out.extend_from_slice(&(data.len() as u32).to_be_bytes());
    out.extend_from_slice(kind);
    out.extend_from_slice(data);
    let mut crc = flate2::Crc::new();
    crc.update(kind);
    crc.update(data);
    out.extend_from_slice(&crc.sum().to_be_bytes());
}

/// The five PNG filter types, in the order the format numbers them.
#[derive(Clone, Copy)]
enum Filter {
    None = 0,
    Sub = 1,
    Up = 2,
    Average = 3,
    Paeth = 4,
}

#[inline]
fn paeth(a: u8, b: u8, c: u8) -> u8 {
    let p = a as i16 + b as i16 - c as i16;
    let (pa, pb, pc) = (
        (p - a as i16).abs(),
        (p - b as i16).abs(),
        (p - c as i16).abs(),
    );
    if pa <= pb && pa <= pc {
        a
    } else if pb <= pc {
        b
    } else {
        c
    }
}

/// Apply one filter to `row` (with `prev` the unfiltered row above, or zeros for
/// the first row), writing `row.len()` bytes into `out`.
fn apply_filter(f: Filter, row: &[u8], prev: &[u8], out: &mut [u8]) {
    let left = |i: usize| if i >= BPP { row[i - BPP] } else { 0 };
    let upleft = |i: usize| if i >= BPP { prev[i - BPP] } else { 0 };
    match f {
        Filter::None => out.copy_from_slice(row),
        Filter::Sub => {
            for i in 0..row.len() {
                out[i] = row[i].wrapping_sub(left(i));
            }
        }
        Filter::Up => {
            for i in 0..row.len() {
                out[i] = row[i].wrapping_sub(prev[i]);
            }
        }
        Filter::Average => {
            for i in 0..row.len() {
                let avg = ((left(i) as u16 + prev[i] as u16) / 2) as u8;
                out[i] = row[i].wrapping_sub(avg);
            }
        }
        Filter::Paeth => {
            for i in 0..row.len() {
                out[i] = row[i].wrapping_sub(paeth(left(i), prev[i], upleft(i)));
            }
        }
    }
}

/// The usual minimum-sum-of-absolute-differences heuristic: the filter whose
/// output has the smallest total magnitude (reading bytes as signed) is the one
/// most likely to deflate well.
fn filter_cost(buf: &[u8]) -> u64 {
    buf.iter()
        .map(|&b| u64::from(if b < 128 { b } else { 255 - b + 1 }))
        .sum()
}

/// Filter every scanline into the `1 + stride`-byte-per-row layout PNG expects.
/// Rows only read `rgba`, never each other's output, so this is a plain
/// parallel map over the destination rows.
fn filter_scanlines(rgba: &[u8], stride: usize, height: usize) -> Vec<u8> {
    let mut filtered = vec![0u8; height * (stride + 1)];
    let zeros = vec![0u8; stride];
    filtered
        .par_chunks_mut(stride + 1)
        // One scratch row per worker, not per row: `for_each_init` hands the
        // same buffer to every row a thread takes.
        .enumerate()
        .for_each_init(
            || vec![0u8; stride],
            |scratch, (y, out)| {
                let row = &rgba[y * stride..(y + 1) * stride];
                let prev = if y == 0 {
                    &zeros[..]
                } else {
                    &rgba[(y - 1) * stride..y * stride]
                };
                let (kind, body) = out.split_at_mut(1);
                let mut best = (Filter::None, u64::MAX);
                for f in [
                    Filter::None,
                    Filter::Sub,
                    Filter::Up,
                    Filter::Average,
                    Filter::Paeth,
                ] {
                    apply_filter(f, row, prev, scratch);
                    let cost = filter_cost(scratch);
                    if cost < best.1 {
                        best = (f, cost);
                    }
                }
                kind[0] = best.0 as u8;
                apply_filter(best.0, row, prev, body);
            },
        );
    filtered
}

/// Deflate `data` into a zlib stream, compressing independent chunks of it in
/// parallel and concatenating them (see the module docs).
fn deflate_parallel(data: &[u8]) -> Vec<u8> {
    // A fixed chunk size, deliberately not one derived from the core count:
    // where the cuts fall changes the compressed bytes (not the pixels), and a
    // PNG should not differ between a laptop and a build machine. Rayon
    // parallelizes across however many chunks this yields.
    let n_chunks = data.len().div_ceil(DEFLATE_CHUNK).max(1);

    let pieces: Vec<(Vec<u8>, u32, usize)> = data
        .par_chunks(DEFLATE_CHUNK)
        .enumerate()
        .map(|(i, c)| {
            let last = i + 1 == n_chunks;
            (deflate_chunk(c, last), adler32(c), c.len())
        })
        .collect();

    // zlib header: deflate, 32K window, no preset dictionary, default level.
    // 0x789C is the canonical pair and satisfies the (CMF<<8|FLG) % 31 == 0 check.
    let total: usize = pieces.iter().map(|(d, _, _)| d.len()).sum();
    let mut out = Vec::with_capacity(total + 6);
    out.extend_from_slice(&[0x78, 0x9C]);
    let mut adler = 1u32;
    for (deflated, chunk_adler, len) in &pieces {
        out.extend_from_slice(deflated);
        adler = adler_combine(adler, *chunk_adler, *len as u64);
    }
    out.extend_from_slice(&adler.to_be_bytes());
    out
}

/// Raw-deflate one chunk. Non-final chunks end with a sync flush, which emits an
/// empty stored block and leaves the output byte-aligned so the next chunk's
/// blocks can simply follow; the final chunk closes the stream.
fn deflate_chunk(data: &[u8], last: bool) -> Vec<u8> {
    let mut c = Compress::new(Compression::new(LEVEL), false);
    let flush = if last {
        FlushCompress::Finish
    } else {
        FlushCompress::Sync
    };
    // Deflate only exceeds its input for incompressible data, and then only by
    // ~5 bytes per 64 KB stored block, so this is a one-shot in practice.
    let mut out = Vec::with_capacity(data.len() + data.len() / 64 + 128);
    loop {
        if out.len() == out.capacity() {
            out.reserve(out.capacity().max(4096));
        }
        let consumed = c.total_in() as usize;
        let status = c
            .compress_vec(&data[consumed..], &mut out, flush)
            .expect("deflate of an in-memory buffer cannot fail");
        match status {
            Status::StreamEnd => break,
            // zlib reports a flush complete by leaving output space unused once
            // it has taken all the input.
            _ if !last && c.total_in() as usize == data.len() && out.len() < out.capacity() => {
                break
            }
            _ => out.reserve(out.capacity().max(4096)),
        }
    }
    out
}

const ADLER_BASE: u32 = 65521;

fn adler32(data: &[u8]) -> u32 {
    let (mut a, mut b) = (1u32, 0u32);
    // 5552 is the most bytes that can be summed before `b` can overflow u32.
    for block in data.chunks(5552) {
        for &byte in block {
            a += u32::from(byte);
            b += a;
        }
        a %= ADLER_BASE;
        b %= ADLER_BASE;
    }
    (b << 16) | a
}

/// zlib's `adler32_combine`: the checksum of `A ++ B` from those of `A` and `B`.
fn adler_combine(adler1: u32, adler2: u32, len2: u64) -> u32 {
    let rem = (len2 % u64::from(ADLER_BASE)) as u32;
    let mut sum1 = adler1 & 0xffff;
    let mut sum2 = ((u64::from(rem) * u64::from(sum1)) % u64::from(ADLER_BASE)) as u32;
    sum1 += (adler2 & 0xffff) + ADLER_BASE - 1;
    sum2 += ((adler1 >> 16) & 0xffff) + ((adler2 >> 16) & 0xffff) + ADLER_BASE - rem;
    if sum1 >= ADLER_BASE {
        sum1 -= ADLER_BASE;
    }
    if sum1 >= ADLER_BASE {
        sum1 -= ADLER_BASE;
    }
    if sum2 >= ADLER_BASE << 1 {
        sum2 -= ADLER_BASE << 1;
    }
    if sum2 >= ADLER_BASE {
        sum2 -= ADLER_BASE;
    }
    sum1 | (sum2 << 16)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn image(w: u32, h: u32) -> Vec<u8> {
        // Gradients plus a hard edge, so every filter type is plausibly the
        // winner somewhere and the adaptive choice actually varies by row.
        let mut v = Vec::with_capacity((w * h * 4) as usize);
        for y in 0..h {
            for x in 0..w {
                let edge = if x > w / 2 { 255 } else { 0 };
                v.extend_from_slice(&[(x % 256) as u8, (y % 256) as u8, edge, 255]);
            }
        }
        v
    }

    /// The bytes we write must decode, through an independent implementation,
    /// back to exactly the pixels we put in - at every size that exercises a
    /// different number of deflate chunks.
    #[test]
    fn round_trips_through_a_decoder() {
        for (w, h) in [(1u32, 1u32), (7, 3), (64, 64), (600, 400)] {
            let src = image(w, h);
            let png = encode_rgba8(&src, w, h, 3780).unwrap();

            let decoder = png::Decoder::new(std::io::Cursor::new(&png));
            let mut reader = decoder.read_info().unwrap();
            let mut buf = vec![0; reader.output_buffer_size().unwrap()];
            let info = reader.next_frame(&mut buf).unwrap();
            assert_eq!((info.width, info.height), (w, h));
            assert_eq!(info.color_type, png::ColorType::Rgba);
            assert_eq!(&buf[..info.buffer_size()], &src[..], "{w}x{h} round trip");
        }
    }

    /// Forces several deflate chunks (and so several sync-flush joins) and
    /// checks the concatenated stream is still one valid zlib stream carrying
    /// the right adler32 - the part a decoder would reject if the pigz-style
    /// framing were wrong.
    #[test]
    fn multi_chunk_stream_is_valid() {
        let (w, h) = (900u32, 700u32);
        let src = image(w, h);
        assert!(
            src.len() > 4 * DEFLATE_CHUNK,
            "test image must span several deflate chunks"
        );
        let png = encode_rgba8(&src, w, h, 3780).unwrap();
        let decoder = png::Decoder::new(std::io::Cursor::new(&png));
        let mut reader = decoder.read_info().unwrap();
        let mut buf = vec![0; reader.output_buffer_size().unwrap()];
        let info = reader.next_frame(&mut buf).unwrap();
        assert_eq!(&buf[..info.buffer_size()], &src[..]);
    }

    /// `adler_combine` must agree with checksumming the concatenation directly.
    #[test]
    fn adler_combine_matches_whole() {
        let data = image(37, 11);
        for split in [1usize, 64, 1000, data.len() - 1] {
            let (a, b) = data.split_at(split);
            assert_eq!(
                adler_combine(adler32(a), adler32(b), b.len() as u64),
                adler32(&data),
                "split at {split}"
            );
        }
    }

    /// The pHYs chunk has to survive, since PDF/LaTeX placement depends on it.
    #[test]
    fn writes_phys_density() {
        let png = encode_rgba8(&image(8, 8), 8, 8, 11811).unwrap();
        let decoder = png::Decoder::new(std::io::Cursor::new(&png));
        let reader = decoder.read_info().unwrap();
        let phys = reader.info().pixel_dims.unwrap();
        assert_eq!((phys.xppu, phys.yppu), (11811, 11811));
        assert_eq!(phys.unit, png::Unit::Meter);
    }

    /// Same input, same bytes - the golden suite compares whole files.
    #[test]
    fn encoding_is_deterministic() {
        let src = image(300, 200);
        assert_eq!(
            encode_rgba8(&src, 300, 200, 3780).unwrap(),
            encode_rgba8(&src, 300, 200, 3780).unwrap()
        );
    }

    /// ...and the same bytes on any machine. Where the deflate chunks are cut
    /// changes the compressed output, so cutting them by core count would make
    /// a PNG differ between a laptop and a build box.
    #[test]
    fn encoding_does_not_depend_on_core_count() {
        let (w, h) = (900u32, 700u32);
        let src = image(w, h);
        assert!(
            src.len() > 4 * DEFLATE_CHUNK,
            "test image must span several deflate chunks"
        );
        let expected = encode_rgba8(&src, w, h, 3780).unwrap();
        for threads in [1usize, 2, 7, 24] {
            let pool = rayon::ThreadPoolBuilder::new()
                .num_threads(threads)
                .build()
                .unwrap();
            let got = pool.install(|| encode_rgba8(&src, w, h, 3780).unwrap());
            assert_eq!(got, expected, "output changed with {threads} threads");
        }
    }
}
