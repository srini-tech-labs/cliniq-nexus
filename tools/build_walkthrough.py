"""Build the walkthrough deliverables from ONE lossless source take recorded by tools/demo_video.py.

Usage: python tools/build_walkthrough.py --src build/media/walkthrough-source --out <dir> [--prefix cliniq-nexus-walkthrough]

1. Assemble a constant 25 fps lossless master by sample-and-hold of the browser's own PNG frames
   (each frame shown until the next one arrived). The closing hold is a freeze of the last stable frame.
2. Burn the captions onto a copy of the master -> lossless captioned master. Both masters share one timeline.
3. Encode clean and captioned MP4 (H.264) and WebM (VP9); write WebVTT, transcript and poster.
4. Validate: identical durations/frame counts; captions contiguous (no blank frame between cues), inside the
   video, final disclosure held >= 4 s; every encoded frame compared with its lossless reference (PSNR and
   worst horizontal band error), so encoder artifacts such as slicing or flicker cannot pass unnoticed.
"""
from __future__ import annotations

import argparse
import json
import math
import subprocess
from pathlib import Path

import av
import imageio_ffmpeg
import numpy as np
from PIL import Image

FF = imageio_ffmpeg.get_ffmpeg_exe()
FPS = 25
W, H = 1440, 900
LEAD_IN_S = 1.0
FLASH_W, FLASH_H, FLASH_BANDS = 720, 450, 45   # same criterion as tools/check_video_frames.py
FLASH_THRESHOLD, FLASH_RATIO = 1.0, 3.0
MIN_FINAL_HOLD = 4.0
MIN_LUMA_PSNR_DB = 38.0     # per-frame luma PSNR vs the lossless reference (chroma 4:2:0 loss is expected and excluded)
MAX_BAND_ERR = 3.0          # worst luma mean abs error (0-255) in any 20-px horizontal band of any frame
FONT_DIR = "/usr/share/fonts/truetype/dejavu"
ASS_STYLE = ("Style: Caption,DejaVu Sans,24,&H00FFFFFF,&H00FFFFFF,&H182D1B0F,&H182D1B0F,0,0,0,0,100,100,0,0,4,14,0,2,250,250,42,1")


def ff(*args):
    subprocess.run([FF, "-y", "-hide_banner", "-loglevel", "error", *args], check=True)


def snap(t):
    return round(t * FPS) / FPS


def ts_vtt(t):
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h):02d}:{int(m):02d}:{s:06.3f}"


def ts_ass(t):
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def schedule(src: Path, frames: list[dict], t0: float, n_out: int) -> list[str]:
    """Sample-and-hold the browser frames onto the 25 fps grid, then remove one-frame flashes.

    A flash is an output frame that differs from BOTH neighbours in some horizontal band while the two
    neighbours agree there (intact / different / intact), e.g. a loading skeleton painted for a single frame
    between two pages, or the first frame of a fade. It is replaced by the previous frame (hold). Genuine
    motion such as a progress spinner changes from frame to frame, so its neighbours never agree and it is
    kept. Repeats until no flash remains; tools/check_video_frames.py applies the same test to the result."""
    chosen, j = [], 0
    for k in range(n_out):
        t = t0 + k / FPS
        while j + 1 < len(frames) and frames[j + 1]["t"] <= t:
            j += 1
        chosen.append(frames[j]["file"])
    cache: dict[str, np.ndarray] = {}

    def gray(name):
        if name not in cache:
            im = Image.open(src / "frames" / name).convert("L").resize((FLASH_W, FLASH_H), Image.BILINEAR)
            cache[name] = np.asarray(im, dtype=np.int16)
        return cache[name]

    def bands(a, b):
        return np.abs(gray(a) - gray(b)).reshape(FLASH_BANDS, FLASH_H // FLASH_BANDS, FLASH_W).mean(axis=(1, 2))

    for _ in range(20):
        fixed = 0
        for k in range(1, n_out - 1):
            a, x, c = chosen[k - 1], chosen[k], chosen[k + 1]
            if x == a or x == c:
                continue
            bp, bn, bs = bands(a, x), bands(x, c), bands(a, c)
            m = np.minimum(bp, bn)
            if ((m > FLASH_THRESHOLD) & (m > FLASH_RATIO * np.maximum(bs, 0.05))).any():
                chosen[k] = a
                fixed += 1
        if not fixed:
            break
    return chosen


def build_master(src: Path, frames: list[dict], t0: float, n_out: int, out: Path):
    """Write a lossless RGB master by piping the debounced sample-and-hold frames to ffmpeg."""
    plan = schedule(src, frames, t0, n_out)
    proc = subprocess.Popen([FF, "-y", "-hide_banner", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
                             "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-c:v", "ffv1", "-pix_fmt", "bgr0", str(out)],
                            stdin=subprocess.PIPE)
    cur_file, cur_bytes, used = None, None, []
    for k in range(n_out):
        if plan[k] != cur_file:
            cur_file = plan[k]
            im = Image.open(src / "frames" / cur_file).convert("RGB")
            if im.size != (W, H):
                raise SystemExit(f"unexpected frame size {im.size} in {cur_file}")
            cur_bytes = im.tobytes()
        used.append(cur_file)
        proc.stdin.write(cur_bytes)
    proc.stdin.close()
    if proc.wait() != 0:
        raise SystemExit("master encode failed")
    return used


def decode_gray(path: Path):
    with av.open(str(path)) as c:
        for f in c.decode(c.streams.video[0]):
            yield f.to_ndarray(format="rgb24").astype(np.int16)


def luma(rgb):
    return 0.299 * rgb[..., 0] + 0.587 * rgb[..., 1] + 0.114 * rgb[..., 2]


def compare(encoded: Path, reference: Path):
    """Per-frame luma PSNR and worst 20-px-band luma error of encoded vs lossless reference (RGB PSNR reported too).

    Slicing, tearing, displaced sections or flicker show up as large localized luma errors in a band;
    4:2:0 chroma subsampling of coloured text edges does not, so it is reported but not gated."""
    worst_y, worst_rgb, worst_band, worst_at, n = 99.0, 99.0, 0.0, None, 0
    for i, (a, b) in enumerate(zip(decode_gray(encoded), decode_gray(reference))):
        n += 1
        ey = np.abs(luma(a) - luma(b))
        mse_y = float((ey ** 2).mean())
        mse_rgb = float(((a - b).astype(np.float64) ** 2).mean())
        py = 99.0 if mse_y == 0 else 10 * math.log10(255 ** 2 / mse_y)
        prgb = 99.0 if mse_rgb == 0 else 10 * math.log10(255 ** 2 / mse_rgb)
        band = float(ey.reshape(H // 20, 20, W).mean(axis=(1, 2)).max())
        worst_y, worst_rgb = min(worst_y, py), min(worst_rgb, prgb)
        if band > worst_band:
            worst_band, worst_at = band, round(i / FPS, 2)
    return {"frames_compared": n, "min_luma_psnr_db": round(worst_y, 2), "min_rgb_psnr_db": round(worst_rgb, 2),
            "max_band_err": round(worst_band, 2), "max_band_err_at_s": worst_at}


def probe(path: Path):
    with av.open(str(path)) as c:
        n = sum(1 for _ in c.decode(c.streams.video[0]))
        return round(float(c.duration / av.time_base), 3), n


def contact_sheet(video: Path, start_s: float, end_s: float, out: Path):
    tiles = []
    with av.open(str(video)) as c:
        s = c.streams.video[0]
        for f in c.decode(s):
            t = float(f.pts * s.time_base)
            if start_s - 1e-6 <= t < end_s:
                im = f.to_image().resize((360, 225))
                tiles.append((t, im))
    cols = 5
    rows = math.ceil(len(tiles) / cols)
    sheet = Image.new("RGB", (360 * cols, 245 * rows), "white")
    from PIL import ImageDraw
    for i, (t, im) in enumerate(tiles):
        x, y = (i % cols) * 360, (i // cols) * 245
        sheet.paste(im, (x, y + 20))
        ImageDraw.Draw(sheet).text((x + 4, y + 4), f"{t:.2f}s", fill="black")
    sheet.save(out)
    return len(tiles)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default="build/media/walkthrough-source")
    ap.add_argument("--out", required=True)
    ap.add_argument("--prefix", default="cliniq-nexus-walkthrough")
    a = ap.parse_args()
    src, out = Path(a.src), Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    work = src / "_build"
    work.mkdir(exist_ok=True)
    frames = sorted(json.loads((src / "frames.json").read_text()), key=lambda f: f["t"])
    log = json.loads((src / "cues.json").read_text())

    t0 = max(frames[0]["t"], log[0]["start"] - LEAD_IN_S)
    duration = snap(log[-1]["end"] - t0)
    n_out = int(round(duration * FPS))
    duration = n_out / FPS
    cues = []
    for i, c in enumerate(log):
        s = snap(c["start"] - t0)
        e = snap(log[i + 1]["start"] - t0) if i + 1 < len(log) else duration
        cues.append({"start": s, "end": min(e, duration), "text": c["text"]})

    master = work / "master-clean.mkv"
    used = build_master(src, frames, t0, n_out, master)
    ass = work / "captions.ass"
    header = ("[Script Info]\nScriptType: v4.00+\nPlayResX: 1440\nPlayResY: 900\nWrapStyle: 0\nScaledBorderAndShadow: yes\n\n"
              "[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, "
              "Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
              f"{ASS_STYLE}\n\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")
    ass.write_text(header + "\n".join(f"Dialogue: 0,{ts_ass(c['start'])},{ts_ass(c['end'])},Caption,,0,0,0,,{c['text']}" for c in cues) + "\n")
    master_cap = work / "master-captioned.mkv"
    ff("-i", str(master), "-vf", f"subtitles={ass.as_posix()}:fontsdir={FONT_DIR}", "-c:v", "ffv1", "-pix_fmt", "bgr0", str(master_cap))

    p = a.prefix
    x264 = ["-c:v", "libx264", "-preset", "slow", "-crf", "18", "-tune", "stillimage", "-pix_fmt", "yuv420p", "-profile:v", "high",
            "-g", "250", "-movflags", "+faststart", "-an"]
    vp9 = ["-c:v", "libvpx-vp9", "-crf", "30", "-b:v", "0", "-row-mt", "1", "-deadline", "good", "-cpu-used", "1", "-g", "250", "-an"]
    targets = {f"{p}-clean.mp4": (master, x264), f"{p}-clean.webm": (master, vp9),
               f"{p}-captioned.mp4": (master_cap, x264), f"{p}-captioned.webm": (master_cap, vp9)}
    for name, (m, opts) in targets.items():
        ff("-i", str(m), *opts, str(out / name))

    vtt = ["WEBVTT", "Kind: captions", "Language: en", "", "NOTE ClinIQ Nexus walkthrough. Synthetic demonstration data only.", ""]
    for i, c in enumerate(cues, 1):
        vtt += [str(i), f"{ts_vtt(c['start'])} --> {ts_vtt(c['end'])}", c["text"], ""]
    (out / f"{p}.en.vtt").write_text("\n".join(vtt))
    tr = ["# ClinIQ Nexus walkthrough: transcript", "",
          f"Silent screen recording ({duration:.2f} seconds) of the deployed application using synthetic records. The narration appears as "
          "burned-in captions (captioned version) or as a WebVTT track (clean version); both versions share one timeline. "
          "Timestamps below are caption start times rounded down to whole seconds; exact times are in the WebVTT file.", ""]
    for c in cues:
        m, s = divmod(int(c["start"]), 60)
        tr.append(f"**[{m}:{s:02d}]** {c['text']}  ")
    (out / "transcript.md").write_text("\n".join(tr) + "\n")
    (out / "transcript.txt").write_text("\n".join(c["text"] for c in cues) + "\n")
    (out / f"{p}.cues.json").write_text(json.dumps({"duration_s": duration, "fps": FPS, "frames": n_out, "cues": cues}, indent=1))

    poster_i = int(round((next(c for c in cues if c["text"].startswith("Each claim cites"))["start"] + 2.0) * FPS))
    for i, fr in enumerate(decode_gray(master)):
        if i == poster_i:
            im = Image.fromarray(fr.astype("uint8"))
            im.save(out / f"{p}-poster.jpg", quality=90, optimize=True, progressive=True)
            im.save(out / f"{p}-poster.webp", quality=88, method=6)
            break

    report = {"source_frames": len(frames), "distinct_frames_used": len(set(used)), "output_frames": n_out, "duration_s": duration,
              "final_cue": cues[-1], "final_cue_hold_s": round(cues[-1]["end"] - cues[-1]["start"], 3), "outputs": {}}
    for name, (m, _) in targets.items():
        d, n = probe(out / name)
        report["outputs"][name] = {"duration_s": d, "frames": n, "bytes": (out / name).stat().st_size, **compare(out / name, m)}
    report["contiguous_cues"] = all(cues[i]["end"] == cues[i + 1]["start"] for i in range(len(cues) - 1))
    report["all_cues_within_video"] = all(0 <= c["start"] < c["end"] <= duration for c in cues)
    o = report["outputs"].values()
    report["consistent"] = len({v["frames"] for v in o}) == 1 and max(v["duration_s"] for v in o) - min(v["duration_s"] for v in o) < 0.001
    report["fidelity_ok"] = all(v["min_luma_psnr_db"] >= MIN_LUMA_PSNR_DB and v["max_band_err"] <= MAX_BAND_ERR for v in o)
    report["contact_sheets"] = {
        "captioned_first_second": contact_sheet(out / f"{p}-captioned.mp4", 0, 1, work / "sheet-captioned-first.png"),
        "captioned_last_second": contact_sheet(out / f"{p}-captioned.mp4", duration - 1, duration + 1, work / "sheet-captioned-last.png"),
        "clean_first_second": contact_sheet(out / f"{p}-clean.webm", 0, 1, work / "sheet-clean-first.png"),
        "clean_last_second": contact_sheet(out / f"{p}-clean.webm", duration - 1, duration + 1, work / "sheet-clean-last.png"),
    }
    (work / "report.json").write_text(json.dumps(report, indent=1))
    print(json.dumps(report, indent=1))
    if not (report["consistent"] and report["contiguous_cues"] and report["all_cues_within_video"]
            and report["fidelity_ok"] and report["final_cue_hold_s"] >= MIN_FINAL_HOLD):
        raise SystemExit("validation failed")


if __name__ == "__main__":
    main()
