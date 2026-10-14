import { ChevronLeft, ChevronRight, Minus, Plus } from "lucide-react";
import { GlobalWorkerOptions, getDocument, type PDFDocumentProxy } from "pdfjs-dist";
import workerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";
import { useEffect, useRef, useState } from "react";
import { Spinner } from "./ui";

GlobalWorkerOptions.workerSrc = workerUrl;

export default function PdfViewer({ url, page, onPage }: { url: string; page: number; onPage: (p: number) => void }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const box = useRef<HTMLDivElement>(null);
  const [doc, setDoc] = useState<PDFDocumentProxy | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [zoom, setZoom] = useState(1);

  useEffect(() => {
    let cancelled = false;
    setDoc(null); setError(null);
    const task = getDocument({ url, isEvalSupported: false });
    task.promise.then((d) => { if (!cancelled) setDoc(d); }).catch((e) => !cancelled && setError(String(e?.message ?? e)));
    return () => { cancelled = true; task.destroy(); };
  }, [url]);

  useEffect(() => {
    if (!doc || !canvas.current || !box.current) return;
    let task: { cancel: () => void } | null = null;
    doc.getPage(Math.min(Math.max(page, 1), doc.numPages)).then((p) => {
      const width = box.current!.clientWidth - 2;
      const base = p.getViewport({ scale: 1 });
      const scale = (width / base.width) * zoom;
      const vp = p.getViewport({ scale: scale * window.devicePixelRatio });
      const c = canvas.current!;
      c.width = vp.width; c.height = vp.height;
      c.style.width = `${vp.width / window.devicePixelRatio}px`;
      c.style.height = `${vp.height / window.devicePixelRatio}px`;
      const r = p.render({ canvasContext: c.getContext("2d")!, viewport: vp });
      task = r;
      r.promise.catch(() => undefined);
    });
    return () => task?.cancel();
  }, [doc, page, zoom]);

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between gap-2 border-b border-line bg-surface px-3 py-1.5 text-[12.5px] text-ink-2">
        <div className="flex items-center gap-1">
          <button className="btn-ghost px-1.5" onClick={() => onPage(page - 1)} disabled={page <= 1} aria-label="Previous page"><ChevronLeft className="h-4 w-4" /></button>
          <span className="tabular">Page {page} of {doc?.numPages ?? "…"}</span>
          <button className="btn-ghost px-1.5" onClick={() => onPage(page + 1)} disabled={!doc || page >= doc.numPages} aria-label="Next page"><ChevronRight className="h-4 w-4" /></button>
        </div>
        <div className="flex items-center gap-1">
          <button className="btn-ghost px-1.5" onClick={() => setZoom((z) => Math.max(0.6, z - 0.2))} aria-label="Zoom out"><Minus className="h-4 w-4" /></button>
          <span className="w-10 text-center tabular">{Math.round(zoom * 100)}%</span>
          <button className="btn-ghost px-1.5" onClick={() => setZoom((z) => Math.min(2.4, z + 0.2))} aria-label="Zoom in"><Plus className="h-4 w-4" /></button>
        </div>
      </div>
      <div ref={box} className="scroll-thin flex-1 overflow-auto bg-[#e9edf2] p-3">
        {!doc && !error && <Spinner label="Loading PDF from Unity Catalog volume…" />}
        {error && <p className="text-sm text-crit-600">The PDF could not be rendered: {error}</p>}
        <canvas ref={canvas} className="mx-auto block rounded-sm bg-white shadow-card" aria-label={`PDF page ${page}`} />
      </div>
    </div>
  );
}
