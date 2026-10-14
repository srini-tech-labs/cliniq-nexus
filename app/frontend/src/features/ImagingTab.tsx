import { useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import { AlertTriangle, Contrast, Maximize, RotateCcw, ScanLine, ZoomIn, ZoomOut } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { EmptyState, Spinner } from "../components/ui";
import { api } from "../lib/api";
import { useWorkspace } from "../lib/context";
import { fmtDate, fmtDateTime } from "../lib/format";
import type { Bundle } from "../lib/types";

function useDebounced<T>(v: T, ms = 250) {
  const [d, setD] = useState(v);
  useEffect(() => { const t = setTimeout(() => setD(v), ms); return () => clearTimeout(t); }, [v, ms]);
  return d;
}

export default function ImagingTab({ bundle }: { bundle: Bundle }) {
  const pid = bundle.patient.patient_id;
  const { openEvidence } = useWorkspace();
  const [sel, setSel] = useState(bundle.imaging[bundle.imaging.length - 1]?.study_id);
  const study = bundle.imaging.find((s) => s.study_id === sel);
  const meta = useQuery({ queryKey: ["dicom", pid, sel], queryFn: () => api.imagingMeta(pid, sel!), enabled: !!sel });
  const [wc, setWc] = useState<number | null>(null);
  const [ww, setWw] = useState<number | null>(null);
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [loaded, setLoaded] = useState(false);
  const drag = useRef<{ x: number; y: number } | null>(null);
  useEffect(() => { setWc(null); setWw(null); setZoom(1); setPan({ x: 0, y: 0 }); }, [sel]);
  useEffect(() => { if (meta.data && wc === null) { setWc(meta.data.window_center); setWw(meta.data.window_width); } }, [meta.data, wc]);
  const dwc = useDebounced(wc), dww = useDebounced(ww);
  const src = sel ? api.imageUrl(pid, sel, dwc ?? undefined, dww ?? undefined) : "";
  useEffect(() => setLoaded(false), [src]);

  if (!bundle.imaging.length) {
    return <EmptyState icon={ScanLine} title="No imaging studies are documented for this patient.">The imaging workspace shows DICOM objects and their linked reports when a study exists.</EmptyState>;
  }
  return (
    <div className="space-y-4">
      <div className="flex gap-3 rounded-xl2 border border-attn-600/25 bg-attn-50 p-3.5 text-[13px] text-attn-700">
        <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
        <p><span className="font-semibold">Synthetic imaging objects.</span> Each study is a DICOM Secondary Capture (modality OT, ConversionType SYN) containing a
          geometric test pattern linked to a real-looking order. They are not radiographs, CT, MRI, ultrasound or echocardiograms, and no image interpretation is performed or displayed.</p>
      </div>
      <div className="grid gap-4 lg:grid-cols-[240px_minmax(0,1fr)] min-[1900px]:grid-cols-[250px_minmax(0,1fr)_340px]">
        <ul className="card h-fit divide-y divide-line overflow-hidden" aria-label="Imaging studies">
          {bundle.imaging.map((s) => (
            <li key={s.study_id}>
              <button onClick={() => setSel(s.study_id)} aria-current={s.study_id === sel}
                className={clsx("flex w-full gap-3 px-3 py-3 text-left", s.study_id === sel ? "bg-brand-50/70" : "hover:bg-sunken/60")}>
                <img src={api.imageUrl(pid, s.study_id)} alt="" className="h-12 w-12 rounded-md border border-line bg-black object-cover" loading="lazy" />
                <span className="min-w-0">
                  <span className="block text-[13px] font-medium leading-snug text-ink">{s.ordered_procedure}</span>
                  <span className="block text-[11.5px] text-ink-3">{fmtDate(s.study_at)} · {s.accession_number}</span>
                </span>
              </button>
            </li>
          ))}
        </ul>

        {study && (
          <div className="card overflow-hidden">
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line px-4 py-2">
              <div className="text-[13px] font-medium text-ink">{study.ordered_procedure} <span className="font-normal text-ink-3">· order context</span></div>
              <div className="flex items-center gap-1">
                <button className="btn-ghost px-1.5" onClick={() => setZoom((z) => Math.min(4, z * 1.25))} aria-label="Zoom in"><ZoomIn className="h-4 w-4" /></button>
                <button className="btn-ghost px-1.5" onClick={() => setZoom((z) => Math.max(0.5, z / 1.25))} aria-label="Zoom out"><ZoomOut className="h-4 w-4" /></button>
                <button className="btn-ghost px-1.5" onClick={() => { setZoom(1); setPan({ x: 0, y: 0 }); }} aria-label="Fit"><Maximize className="h-4 w-4" /></button>
                <button className="btn-ghost px-1.5" onClick={() => { setWc(meta.data?.window_center ?? null); setWw(meta.data?.window_width ?? null); }} aria-label="Reset window/level"><RotateCcw className="h-4 w-4" /></button>
              </div>
            </div>
            <div className="relative h-[460px] select-none overflow-hidden bg-[#0b0f16]"
              onMouseDown={(e) => (drag.current = { x: e.clientX - pan.x, y: e.clientY - pan.y })}
              onMouseMove={(e) => drag.current && setPan({ x: e.clientX - drag.current.x, y: e.clientY - drag.current.y })}
              onMouseUp={() => (drag.current = null)} onMouseLeave={() => (drag.current = null)}
              onWheel={(e) => setZoom((z) => Math.min(4, Math.max(0.5, z * (e.deltaY < 0 ? 1.1 : 0.9))))}>
              <div className="absolute inset-x-0 top-0 z-10 bg-attn-600/90 px-3 py-1 text-center text-[11.5px] font-semibold tracking-wide text-white">
                SYNTHETIC TEST PATTERN — NOT A MEDICAL IMAGE · NO INTERPRETATION
              </div>
              {!loaded && <div className="absolute inset-0 grid place-items-center"><Spinner label="Rendering DICOM from Unity Catalog volume…" /></div>}
              <img src={src} alt={`Synthetic test pattern for study ${study.study_id} (not a medical image)`} draggable={false} onLoad={() => setLoaded(true)}
                className="absolute left-1/2 top-1/2 max-h-[400px] cursor-grab active:cursor-grabbing"
                style={{ transform: `translate(calc(-50% + ${pan.x}px), calc(-50% + ${pan.y}px)) scale(${zoom})`, imageRendering: zoom > 1.5 ? "pixelated" : "auto" }} />
              <div className="absolute bottom-2 left-3 text-[11px] text-white/70 tabular">
                {meta.data ? `${meta.data.rows}×${meta.data.columns} · ${meta.data.bits_stored}-bit ${meta.data.photometric}` : ""} · W {Math.round(ww ?? 0)} / L {Math.round(wc ?? 0)} · {Math.round(zoom * 100)}%
              </div>
            </div>
            <div className="grid gap-4 border-t border-line px-4 py-3 sm:grid-cols-2">
              <label className="text-[12px] text-ink-3">
                <span className="mb-1 flex items-center gap-1"><Contrast className="h-3.5 w-3.5" />Window level (center): {Math.round(wc ?? 0)}</span>
                <input type="range" min={0} max={4095} value={wc ?? 2048} onChange={(e) => setWc(+e.target.value)} className="w-full accent-brand-600" />
              </label>
              <label className="text-[12px] text-ink-3">
                <span className="mb-1 block">Window width: {Math.round(ww ?? 0)}</span>
                <input type="range" min={64} max={4096} value={ww ?? 4096} onChange={(e) => setWw(+e.target.value)} className="w-full accent-brand-600" />
              </label>
            </div>
          </div>
        )}

        {study && (
          <div className="grid gap-4 md:grid-cols-2 lg:col-span-2 min-[1900px]:col-span-1 min-[1900px]:grid-cols-1 min-[1900px]:content-start">
            <div className="card p-4">
              <div className="eyebrow mb-2">DICOM metadata (read from the file)</div>
              {meta.isLoading && <Spinner />}
              {meta.isError && <p className="text-sm text-crit-600">Metadata unavailable.</p>}
              {meta.data && (
                <dl className="space-y-1 text-[12.5px]">
                  {[
                    ["SOP class", meta.data.sop_class], ["Modality", `${meta.data.modality} (other)`], ["Conversion type", `${meta.data.conversion_type} (synthetic image)`],
                    ["Burned-in annotation", meta.data.burned_in_annotation], ["Study date", meta.data.study_date], ["Accession", meta.data.accession],
                    ["Institution", meta.data.institution], ["Header patient", `${pid} ✓ matches record`],
                  ].map(([k, v]) => <div key={k} className="grid grid-cols-[120px_1fr] gap-2"><dt className="text-ink-3">{k}</dt><dd className="text-ink">{v}</dd></div>)}
                  <details className="pt-1 text-ink-3"><summary className="cursor-pointer">UIDs</summary>
                    <p className="mt-1 break-all">Study {meta.data.study_uid}</p><p className="break-all">SOP {meta.data.sop_uid}</p></details>
                </dl>
              )}
            </div>
            <div className="card p-4">
              <div className="eyebrow mb-1">Linked report</div>
              <p className="mb-2 text-[12px] text-ink-3">Indication (from order): {study.indication} · {fmtDateTime(study.study_at)}</p>
              {study.report ? (
                <>
                  <div className="max-h-56 overflow-y-auto whitespace-pre-wrap rounded-lg bg-sunken p-3 text-[12px] leading-relaxed text-ink scroll-thin">{study.report.report_text}</div>
                  <button className="btn-outline mt-2 w-full text-[12.5px]" onClick={() => openEvidence({ type: "imaging_report", id: study.report!.report_id, label: study.ordered_procedure, patientId: pid })}>Open report as source</button>
                </>
              ) : <p className="text-sm text-ink-3">No report is linked to this study.</p>}
              <p className="mt-2 text-[11.5px] text-ink-3">Report text is associated metadata. ClinIQ Nexus performs no AI image interpretation.</p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
