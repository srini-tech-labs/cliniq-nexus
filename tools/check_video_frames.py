"""Frame-by-frame artifact check for the walkthrough videos.

Usage: python tools/check_video_frames.py <video> [<video> ...] [--dump DIR]

Flags "transient" frames: a frame that differs from BOTH neighbours while the two neighbours are nearly
identical (an intact / broken / intact pattern, as produced by slicing, tearing or flicker). Legitimate
changes (navigation, typing, scrolling) differ from the previous frame but persist into the next one,
so they are not flagged. Also reports, per flagged frame, which horizontal bands differ.
Exit code 1 if any transient frame is found.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import av
import numpy as np

W, H = 720, 450          # analysis resolution (1/2 of 1440x900)
BANDS = 45


def frames(path):
    with av.open(str(path)) as c:
        s = c.streams.video[0]
        for f in c.decode(s):
            yield float(f.pts * s.time_base), f.reformat(width=W, height=H, format="gray").to_ndarray().astype(np.int16), f


def diff(a, b):
    return float(np.abs(a - b).mean())


def check(path: Path, dump: Path | None = None, threshold: float = 1.0, ratio: float = 3.0):
    prev2 = prev1 = None
    flagged, n = [], 0
    keep = {}
    for t, g, f in frames(path):
        n += 1
        if prev2 is not None:
            (t1, g1, f1), (_, g2, _) = prev1, prev2
            band = lambda a, b: np.abs(a - b).reshape(BANDS, H // BANDS, W).mean(axis=(1, 2))  # noqa: E731
            bp, bn, bs = band(g2, g1), band(g1, g), band(g2, g)
            # a band is transient if it changes into AND back out of this frame, but not across the pair
            hit = (np.minimum(bp, bn) > threshold) & (np.minimum(bp, bn) > ratio * np.maximum(bs, 0.05))
            if hit.any():
                flagged.append({"time": round(t1, 3), "bands": [int(i) for i in np.nonzero(hit)[0]],
                                "band_change": round(float(np.minimum(bp, bn)[hit].max()), 2),
                                "band_skip": round(float(bs[hit].max()), 2)})
                if dump is not None and len(keep) < 12:
                    keep[t1] = f1.to_image()
        prev2, prev1 = prev1, (t, g, f)
    if dump is not None:
        dump.mkdir(parents=True, exist_ok=True)
        for t, im in keep.items():
            im.save(dump / f"{path.stem}-{t:08.3f}.png")
    return n, flagged


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("videos", nargs="+")
    ap.add_argument("--dump", default=None)
    a = ap.parse_args()
    bad = False
    for v in a.videos:
        n, flagged = check(Path(v), Path(a.dump) if a.dump else None)
        print(f"{Path(v).name}: {n} frames checked, {len(flagged)} transient (slice/flicker) frames")
        for fl in flagged[:20]:
            print("   ", fl)
        bad |= bool(flagged)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
