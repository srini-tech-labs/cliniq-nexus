import { CalendarDays, FileText, FlaskConical, ImageIcon, MessageSquare, Stethoscope, UserRound } from "lucide-react";
import { CLASS_LABEL, fmtDate, relDays, sexShort } from "../lib/format";
import type { Bundle } from "../lib/types";
import { SyntheticBadge } from "./ui";

export default function PatientHeader({ bundle }: { bundle: Bundle }) {
  const p = bundle.patient;
  const b = bundle.brief;
  const last = b.last_encounter;
  const inv = [
    { icon: Stethoscope, n: b.counts.encounters, label: "encounters" },
    { icon: FileText, n: b.counts.notes, label: "notes" },
    { icon: FileText, n: b.counts.documents, label: `PDFs · ${b.counts.pages} pages` },
    { icon: FlaskConical, n: b.counts.observations, label: "measurements" },
    { icon: MessageSquare, n: b.counts.messages, label: "portal messages" },
    { icon: ImageIcon, n: b.counts.imaging, label: "imaging studies" },
  ];
  return (
    <div className="flex flex-wrap items-start justify-between gap-4">
      <div className="flex items-start gap-3.5">
        <div className="grid h-12 w-12 shrink-0 place-items-center rounded-2xl bg-gradient-to-br from-brand-100 to-brand-50 text-brand-700 ring-1 ring-brand-200">
          <UserRound className="h-6 w-6" aria-hidden />
        </div>
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-xl font-semibold tracking-tight text-ink">{p.display_name}</h1>
            <SyntheticBadge />
          </div>
          <p className="mt-0.5 text-[13px] text-ink-2">
            {sexShort(p.sex)} · {p.age_years} y · DOB {fmtDate(p.birth_date)} · MRN {p.mrn} · <span className="text-ink-3">{p.patient_id}</span>
          </p>
          <p className="mt-1 text-[13px] text-ink-2">
            <span className="font-medium text-ink">{p.care_program}</span> · PCP {p.primary_clinician.split(" — ")[0]}
          </p>
        </div>
      </div>
      <div className="flex flex-col items-end gap-2">
        <span className={b.active_encounter ? "chip border-attn-600/25 bg-attn-50 text-attn-700" : "chip border-line bg-surface text-ink-2"}
          title="Derived from encounter status in the source records">
          {b.active_encounter ? `Encounter in progress · ${CLASS_LABEL[b.active_encounter.class_code]}` : "No encounter in progress"}
        </span>
        {last && (
          <div className="flex items-center gap-1.5 text-[12.5px] text-ink-2">
            <CalendarDays className="h-3.5 w-3.5 text-ink-3" aria-hidden />
            Last encounter <span className="font-medium text-ink">{fmtDate(last.start_at)}</span>
            · {CLASS_LABEL[last.class_code]} · {relDays(last.start_at, bundle.as_of)}
          </div>
        )}
        <ul className="flex flex-wrap justify-end gap-x-3 gap-y-1 text-[12px] text-ink-3" aria-label="Available sources">
          {inv.map((x) => (
            <li key={x.label} className="flex items-center gap-1"><x.icon className="h-3.5 w-3.5" aria-hidden /><span className="tabular font-medium text-ink-2">{x.n}</span> {x.label}</li>
          ))}
        </ul>
      </div>
    </div>
  );
}
