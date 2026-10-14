import { FileText, FileWarning, ShieldCheck } from "lucide-react";
import { EmptyState, SectionTitle, StatusChip } from "../components/ui";
import { useWorkspace } from "../lib/context";
import { fmtDate } from "../lib/format";
import type { Bundle } from "../lib/types";

export default function DocumentsTab({ bundle }: { bundle: Bundle }) {
  const { openEvidence } = useWorkspace();
  const pid = bundle.patient.patient_id;
  const docs = [...bundle.documents].reverse();
  const notes = [...bundle.notes].reverse();
  return (
    <div className="space-y-7">
      <section>
        <SectionTitle icon={FileText} title={`PDF documents (${docs.length})`}
          hint="Text is extracted page by page from the PDF text layer. Every page's printed patient and encounter identifiers are checked against the document index; mismatched files are quarantined at ingestion." />
        {docs.length === 0 ? <EmptyState title="No PDF documents are filed for this patient." /> : (
          <div className="grid gap-3 md:grid-cols-2 2xl:grid-cols-3">
            {docs.map((d) => (
              <button key={d.document_id} onClick={() => openEvidence({ type: "document", id: d.document_id, label: d.title, page: 1, patientId: pid })}
                className="card group flex gap-3 p-4 text-left transition-shadow hover:shadow-pop">
                <div className="grid h-14 w-11 shrink-0 place-items-center rounded-md border border-line bg-sunken">
                  {d.has_text_layer ? <FileText className="h-5 w-5 text-brand-600" /> : <FileWarning className="h-5 w-5 text-attn-600" />}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="truncate text-[13.5px] font-semibold text-ink group-hover:text-brand-700">{d.title}</div>
                  <div className="text-[12px] text-ink-3">{d.doc_type} · {fmtDate(d.authored_at)} · {d.page_count} page{d.page_count > 1 ? "s" : ""}</div>
                  <div className="text-[12px] text-ink-3 truncate">{d.author}</div>
                  <div className="mt-2 flex flex-wrap gap-1.5"><StatusChip status={d.identity_status} /><span className="chip border-line bg-sunken text-ink-3">{d.received_via}</span></div>
                </div>
              </button>
            ))}
          </div>
        )}
        <p className="mt-3 flex items-center gap-1.5 text-[12px] text-ink-3"><ShieldCheck className="h-3.5 w-3.5" />Scanned documents are shown as received; OCR is not performed, so their content is not searchable or cited.</p>
      </section>
      <section>
        <SectionTitle icon={FileText} title={`Clinical notes (${notes.length})`} hint="Encounter notes authored in the source system." />
        <ul className="card divide-y divide-line">
          {notes.map((n) => (
            <li key={n.note_id}>
              <button onClick={() => openEvidence({ type: "note", id: n.note_id, label: n.title, patientId: pid })} className="flex w-full items-center gap-3 px-4 py-2.5 text-left hover:bg-sunken/60">
                <span className="w-24 shrink-0 text-[12px] text-ink-3 tabular">{fmtDate(n.authored_at)}</span>
                <span className="flex-1 text-[13px]"><span className="font-medium text-ink">{n.note_type}</span> <span className="text-ink-3">· {n.author}</span></span>
                <span className="text-[11.5px] text-ink-3">{n.encounter_id}</span>
              </button>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
