import { useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import { AlertTriangle, BadgeCheck, ExternalLink, FileText, ScanLine, X } from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import { useWorkspace, type EvidenceTarget } from "../lib/context";
import { fmtDate, fmtDateTime, num, SOURCE_LABEL } from "../lib/format";
import { highlight } from "../lib/highlight";
import type { Bundle } from "../lib/types";
import PdfViewer from "./PdfViewer";
import { ClassBadge, SourceIcon, Spinner, StatusChip } from "./ui";

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid grid-cols-[120px_1fr] gap-2 py-1 text-[13px]">
      <dt className="text-ink-3">{label}</dt><dd className="text-ink">{children}</dd>
    </div>
  );
}

function Pre({ text, mark }: { text: string; mark?: string }) {
  return (
    <div className="whitespace-pre-wrap rounded-xl border border-line bg-surface p-4 text-[13px] leading-relaxed text-ink">
      {highlight(text, mark)}
    </div>
  );
}

function DocumentView({ bundle, t }: { bundle: Bundle; t: EvidenceTarget }) {
  const doc = bundle.documents.find((d) => d.document_id === t.id);
  const [page, setPage] = useState(t.page ?? 1);
  const [view, setView] = useState<"pdf" | "text">("pdf");
  const pages = useQuery({ queryKey: ["pages", t.patientId, t.id], queryFn: () => api.pages(t.patientId, t.id), enabled: !!doc });
  useEffect(() => setPage(t.page ?? 1), [t.id, t.page]);
  if (!doc) return <p className="text-sm text-ink-3">Document not found for this patient.</p>;
  const current = pages.data?.find((p) => p.page_number === page);
  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="space-y-2 border-b border-line px-5 pb-3">
        <div className="flex flex-wrap gap-1.5">
          <StatusChip status={doc.identity_status} />
          <span className="chip border-line bg-sunken text-ink-2">{doc.page_count} page{doc.page_count > 1 ? "s" : ""}</span>
          <span className="chip border-line bg-sunken text-ink-2">{doc.received_via}</span>
          {t.page && <span className="chip border-brand-500/30 bg-brand-50 text-brand-700">Cited page {t.page}</span>}
        </div>
        <p className="text-[12.5px] text-ink-3">{doc.doc_type} · {doc.author} · {fmtDateTime(doc.authored_at)} · encounter {doc.encounter_id}</p>
        {!doc.has_text_layer && (
          <div className="flex gap-2 rounded-lg border border-attn-600/25 bg-attn-50 p-2.5 text-[12.5px] text-attn-700">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
            <span>Scanned image with no text layer. OCR was not performed, so this document is not searchable and cannot be cited by the assistant. Its patient association comes from the document index only.</span>
          </div>
        )}
        <div role="tablist" className="flex gap-1">
          {(["pdf", "text"] as const).map((v) => (
            <button key={v} role="tab" aria-selected={view === v} onClick={() => setView(v)}
              className={clsx("rounded-md px-2.5 py-1 text-[12.5px] font-medium", view === v ? "bg-brand-50 text-brand-700" : "text-ink-3 hover:bg-sunken")}>
              {v === "pdf" ? "Original PDF" : "Extracted text"}
            </button>
          ))}
        </div>
      </div>
      <div className="min-h-0 flex-1">
        {view === "pdf" ? (
          <PdfViewer url={api.pdfUrl(t.patientId, doc.document_id)} page={page} onPage={(p) => setPage(Math.min(Math.max(1, p), doc.page_count))} />
        ) : (
          <div className="scroll-thin h-full overflow-y-auto p-5">
            <div className="mb-2 flex items-center justify-between text-[12.5px] text-ink-3">
              <span>Page {page} · {current ? `${current.char_count} characters extracted` : ""}</span>
              <span className="flex gap-1">
                {Array.from({ length: doc.page_count }).map((_, i) => (
                  <button key={i} onClick={() => setPage(i + 1)} className={clsx("h-6 w-6 rounded-md text-[12px]", page === i + 1 ? "bg-brand-600 text-white" : "bg-sunken text-ink-2")}>{i + 1}</button>
                ))}
              </span>
            </div>
            {pages.isLoading && <Spinner />}
            {current && (current.has_text_layer ? <Pre text={current.page_text} mark={t.page === page ? t.highlight : undefined} />
              : <p className="rounded-lg bg-sunken p-4 text-sm text-ink-3">No text layer on this page (scanned image). Nothing was extracted.</p>)}
          </div>
        )}
      </div>
    </div>
  );
}

function Body({ bundle, t }: { bundle: Bundle; t: EvidenceTarget }) {
  const { openEvidence } = useWorkspace();
  const go = (type: string, id: string, label: string, extra: Partial<EvidenceTarget> = {}) => openEvidence({ type, id, label, patientId: t.patientId, ...extra });
  switch (t.type) {
    case "note": {
      const n = bundle.notes.find((x) => x.note_id === t.id);
      if (!n) break;
      return (
        <div className="space-y-3 p-5">
          <dl><Field label="Author">{n.author}</Field><Field label="Signed">{fmtDateTime(n.authored_at)}</Field><Field label="Encounter">{n.encounter_id}</Field></dl>
          <Pre text={n.note_text} mark={t.highlight} />
        </div>
      );
    }
    case "message": case "thread": {
      const th = bundle.threads.find((x) => x.thread_id === t.id || x.messages.some((m) => m.message_id === t.id));
      if (!th) break;
      return (
        <div className="space-y-3 p-5">
          <div className="flex flex-wrap items-center gap-2"><StatusChip status={th.status} /><span className="chip border-line bg-sunken text-ink-2">{th.category}</span>
            {th.routed_to && <span className="text-[12.5px] text-ink-3">Routed to {th.routed_to}</span>}</div>
          <ol className="space-y-2.5">
            {th.messages.map((m) => (
              <li key={m.message_id} className={clsx("max-w-[88%] rounded-xl border p-3 text-[13px]", m.sender_role === "patient" ? "border-line bg-surface" : "ml-auto border-brand-500/20 bg-brand-50/60",
                m.message_id === t.id && "ring-2 ring-[#f6d77a]")}>
                <div className="mb-1 flex justify-between gap-3 text-[11.5px] text-ink-3"><span className="font-medium text-ink-2">{m.sender_name}</span><span>{fmtDateTime(m.sent_at)}</span></div>
                <p className="leading-relaxed text-ink">{m.message_body}</p>
                {m.is_routing_acknowledgment && <p className="mt-1 text-[11.5px] text-ink-3">Routing acknowledgment</p>}
              </li>
            ))}
          </ol>
          {th.status === "awaiting_reply" && <p className="rounded-lg border border-dashed border-attn-600/40 p-2.5 text-[12.5px] text-attn-700">No care-team reply is recorded for the latest patient message.</p>}
        </div>
      );
    }
    case "encounter": {
      const e = bundle.encounters.find((x) => x.encounter_id === t.id);
      if (!e) break;
      const notes = bundle.notes.filter((n) => n.encounter_id === e.encounter_id);
      const docs = bundle.documents.filter((d) => d.encounter_id === e.encounter_id);
      const dx = bundle.conditions.filter((c) => c.encounter_id === e.encounter_id);
      const meds = bundle.medications.filter((m) => m.encounter_id === e.encounter_id);
      const labs = bundle.observations.filter((o) => o.encounter_id === e.encounter_id && o.category === "laboratory");
      return (
        <div className="space-y-4 p-5">
          <dl>
            <Field label="Class"><ClassBadge code={e.class_code} /></Field>
            <Field label="When">{fmtDateTime(e.start_at)} → {fmtDateTime(e.end_at)}</Field>
            <Field label="Service">{e.service}</Field><Field label="Attending">{e.attending}</Field>
            <Field label="Reason">{e.reason}</Field><Field label="Disposition">{e.disposition}</Field>
            <Field label="Diagnoses">{dx.map((c) => `${c.display} (${c.code}, ${c.clinical_status})`).join("; ") || "None recorded"}</Field>
          </dl>
          <div>
            <div className="eyebrow mb-1.5">Linked records</div>
            <ul className="space-y-1">
              {notes.map((n) => <LinkRow key={n.note_id} type="clinical_note" label={`${n.note_type}`} onClick={() => go("note", n.note_id, n.title)} />)}
              {docs.map((d) => <LinkRow key={d.document_id} type="document" label={`${d.title} (PDF, ${d.page_count} p.)`} onClick={() => go("document", d.document_id, d.title, { page: 1 })} />)}
              {meds.map((m) => <LinkRow key={m.medication_request_id} type="medication" label={`${m.medication} ${m.dose} — ${m.action}`} onClick={() => go("medication", m.medication_request_id, m.medication)} />)}
              {labs.length > 0 && <li className="px-2 py-1 text-[12.5px] text-ink-3">{labs.length} laboratory results recorded at this encounter</li>}
            </ul>
          </div>
        </div>
      );
    }
    case "medication": {
      const m = bundle.medications.find((x) => x.medication_request_id === t.id);
      if (!m) break;
      const prior = bundle.medications.find((x) => x.medication_request_id === m.prior_request_id);
      const next = bundle.medications.find((x) => x.prior_request_id === m.medication_request_id);
      return (
        <div className="p-5">
          <dl>
            <Field label="Medication"><span className="font-medium">{m.medication}</span></Field>
            <Field label="Sig">{m.dose} · {m.route} · {m.frequency}</Field>
            <Field label="Status"><StatusChip status={m.status} /></Field>
            <Field label="Category">{m.category}</Field>
            <Field label="Ordered">{fmtDateTime(m.authored_on)}{m.prescriber ? ` · ${m.prescriber}` : ""}</Field>
            {m.end_date && <Field label="Ended">{fmtDateTime(m.end_date)}</Field>}
            <Field label="Reason">{m.reason}</Field>
            {m.stop_reason && <Field label="Stop reason">{m.stop_reason}</Field>}
            <Field label="Encounter">{m.encounter_id}</Field>
          </dl>
          {(prior || next) && (
            <ul className="mt-3 space-y-1">
              {prior && <LinkRow type="medication" label={`Previous order: ${prior.dose} ${prior.frequency}`} onClick={() => go("medication", prior.medication_request_id, prior.medication)} />}
              {next && <LinkRow type="medication" label={`Replaced by: ${next.dose} ${next.frequency}`} onClick={() => go("medication", next.medication_request_id, next.medication)} />}
            </ul>
          )}
        </div>
      );
    }
    case "observation": {
      const o = bundle.observations.find((x) => x.observation_id === t.id);
      if (!o) break;
      const series = bundle.observations.filter((x) => x.measure_key === o.measure_key);
      return (
        <div className="p-5">
          <dl>
            <Field label="Measurement">{o.name} <span className="text-ink-3">(LOINC {o.code})</span></Field>
            <Field label="Value"><span className="font-semibold">{num(o.value)} {o.display_unit}</span>{o.interpretation && o.interpretation !== "N" ? ` · flagged ${o.interpretation}` : ""}</Field>
            <Field label="Reference">{o.ref_low ?? "—"} – {o.ref_high ?? "—"} {o.display_unit}</Field>
            <Field label="Recorded">{fmtDateTime(o.effective_at)} · encounter {o.encounter_id}</Field>
          </dl>
          <div className="eyebrow mb-1.5 mt-4">All {o.name.toLowerCase()} values</div>
          <table className="w-full text-[13px]">
            <tbody>{series.map((s) => (
              <tr key={s.observation_id} className={clsx("border-b border-line", s.observation_id === o.observation_id && "bg-[#fff8dc]")}>
                <td className="py-1.5 text-ink-2">{fmtDateTime(s.effective_at)}</td><td className="py-1.5 text-right font-medium tabular">{num(s.value)} {s.display_unit}</td>
                <td className="w-8 py-1.5 text-right text-ink-3">{s.interpretation !== "N" ? s.interpretation : ""}</td>
              </tr>))}
            </tbody>
          </table>
        </div>
      );
    }
    case "imaging_report": {
      const s = bundle.imaging.find((x) => x.report?.report_id === t.id || x.study_id === t.id);
      if (!s || !s.report) break;
      return (
        <div className="space-y-3 p-5">
          <div className="flex gap-3">
            <img src={api.imageUrl(t.patientId, s.study_id)} alt="Synthetic test pattern (not a medical image)" className="h-28 w-28 rounded-lg border border-line bg-black object-cover" />
            <div className="text-[13px]">
              <p className="font-medium text-ink">{s.ordered_procedure}</p>
              <p className="text-ink-3">{fmtDateTime(s.study_at)} · {s.accession_number}</p>
              <p className="mt-1 text-attn-700">Stored object is a synthetic test pattern — not a medical image.</p>
              <Link to={`/patients/${t.patientId}/imaging`} className="mt-1 inline-flex items-center gap-1 text-brand-700 hover:underline">Open imaging workspace <ExternalLink className="h-3 w-3" /></Link>
            </div>
          </div>
          <Pre text={s.report.report_text} mark={t.highlight} />
        </div>
      );
    }
    case "follow_up": {
      const f = bundle.follow_ups.find((x) => x.follow_up_id === t.id);
      if (!f) break;
      const note = bundle.notes.find((n) => n.note_id === f.source_note_id);
      return (
        <div className="p-5">
          <dl>
            <Field label="Item">{f.description}</Field><Field label="Status"><StatusChip status={f.status} /></Field>
            <Field label="Due">{fmtDate(f.due_date)}</Field>
            {f.resolved_encounter_id && <Field label="Resolved by">{f.resolved_encounter_id}</Field>}
          </dl>
          {note && <ul className="mt-3"><LinkRow type="clinical_note" label={`Documented in: ${note.note_type} (${fmtDate(note.authored_at)})`} onClick={() => go("note", note.note_id, note.title, { highlight: f.description })} /></ul>}
        </div>
      );
    }
  }
  return <p className="p-5 text-sm text-ink-3">This source is not available for the selected patient.</p>;
}

function LinkRow({ type, label, onClick }: { type: string; label: string; onClick: () => void }) {
  return (
    <li>
      <button onClick={onClick} className="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-[13px] text-ink hover:bg-sunken">
        <SourceIcon type={type} className="text-ink-3" />{label}
      </button>
    </li>
  );
}

export default function EvidenceDrawer({ bundle }: { bundle: Bundle }) {
  const { evidence, closeEvidence } = useWorkspace();
  const panel = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!evidence) return;
    panel.current?.focus();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && closeEvidence();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [evidence, closeEvidence]);
  useEffect(() => {
    if (evidence?.highlight) setTimeout(() => document.querySelector("[data-evidence-highlight]")?.scrollIntoView({ block: "center", behavior: "smooth" }), 120);
  }, [evidence]);
  if (!evidence || evidence.patientId !== bundle.patient.patient_id) return null;
  const isDoc = evidence.type === "document";
  const typeLabel = SOURCE_LABEL[evidence.type] ?? evidence.type;
  return (
    <div className="fixed inset-0 z-40 flex justify-end" role="dialog" aria-modal="true" aria-label={`Source: ${evidence.label}`}>
      <button className="absolute inset-0 bg-ink/20 backdrop-blur-[1px]" aria-label="Close source" onClick={closeEvidence} />
      <div ref={panel} tabIndex={-1} className={clsx("relative flex h-full w-full flex-col bg-page shadow-pop outline-none", isDoc ? "max-w-[760px]" : "max-w-[600px]")}>
        <div className="flex items-start justify-between gap-3 border-b border-line bg-surface px-5 py-4">
          <div className="min-w-0">
            <div className="eyebrow flex items-center gap-1.5">
              {evidence.type === "imaging_report" ? <ScanLine className="h-3.5 w-3.5" /> : isDoc ? <FileText className="h-3.5 w-3.5" /> : <SourceIcon type={evidence.type} className="h-3.5 w-3.5" />}
              {typeLabel} · source record
            </div>
            <h2 className="mt-1 truncate text-[16px] font-semibold text-ink">{evidence.label}</h2>
            {evidence.highlight && <p className="mt-1 flex items-center gap-1 text-[12px] text-ink-3"><BadgeCheck className="h-3.5 w-3.5 text-evidence-600" /> Cited passage highlighted</p>}
          </div>
          <button className="btn-ghost px-2" onClick={closeEvidence} aria-label="Close source"><X className="h-4 w-4" /></button>
        </div>
        <div className={clsx("min-h-0 flex-1", isDoc ? "pt-3" : "scroll-thin overflow-y-auto")}>
          {isDoc ? <DocumentView bundle={bundle} t={evidence} /> : <Body bundle={bundle} t={evidence} />}
        </div>
        <div className="border-t border-line bg-surface px-5 py-2 text-[11.5px] text-ink-3">
          {bundle.patient.display_name} · {bundle.patient.patient_id} · synthetic record · read-only view
        </div>
      </div>
    </div>
  );
}
