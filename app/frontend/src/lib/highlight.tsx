import type { ReactNode } from "react";

/** Find passages of `excerpt` that occur verbatim in `text` and wrap them in <mark>. */
export function highlight(text: string, excerpt?: string): ReactNode {
  if (!excerpt) return text;
  const segments = excerpt
    .split(/\n|(?<=\.)\s+/)
    .map((s) => s.replace(/^[A-Z][A-Za-z ,()/-]{2,40}:\s+/, "").trim())
    .filter((s) => s.length >= 18);
  const lower = text.toLowerCase();
  const ranges: [number, number][] = [];
  for (const seg of segments) {
    const i = lower.indexOf(seg.toLowerCase());
    if (i >= 0) ranges.push([i, i + seg.length]);
  }
  if (!ranges.length) return text;
  ranges.sort((a, b) => a[0] - b[0]);
  const merged: [number, number][] = [];
  for (const r of ranges) {
    const last = merged[merged.length - 1];
    if (last && r[0] <= last[1] + 2) last[1] = Math.max(last[1], r[1]);
    else merged.push([...r]);
  }
  const out: ReactNode[] = [];
  let pos = 0;
  merged.forEach(([a, b], k) => {
    if (a > pos) out.push(text.slice(pos, a));
    out.push(<mark key={k} className="mark-hit text-ink" data-evidence-highlight>{text.slice(a, b)}</mark>);
    pos = b;
  });
  if (pos < text.length) out.push(text.slice(pos));
  return out;
}
