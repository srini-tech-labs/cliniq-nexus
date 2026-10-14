import { useQuery } from "@tanstack/react-query";
import { ArrowRight, Database, FileStack, MessagesSquare, ScanLine, ShieldCheck, Sparkles, Stethoscope } from "lucide-react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";

const STEPS = [
  { icon: Database, title: "Connected sources", body: "FHIR-style encounters, vitals, labs and medication orders; clinical notes; PDF discharge summaries, consults and lab reports; portal messages; DICOM studies — unified in Unity Catalog." },
  { icon: Stethoscope, title: "Patient context", body: "A brief of what changed and what needs attention, a longitudinal journey, trends with units and reference ranges, and medication history — derived from the records." },
  { icon: Sparkles, title: "Cited answers", body: "Ask in plain language. Structured questions are answered from records; narrative answers are generated from patient-scoped evidence and rejected unless every claim checks out against its sources." },
];

export default function Welcome() {
  const wl = useQuery({ queryKey: ["worklist"], queryFn: api.worklist });
  const ops = useQuery({ queryKey: ["operations"], queryFn: api.operations });
  const t = ops.data?.totals;
  const featured = ["CN-P003", "CN-P008", "CN-P009"].map((id) => wl.data?.find((r) => r.patient_id === id)).filter(Boolean);
  return (
    <div className="mx-auto max-w-5xl px-8 py-10">
      <p className="eyebrow text-brand-700">Pre-visit and post-discharge chart review</p>
      <h1 className="mt-2 max-w-3xl text-[32px] font-semibold leading-tight tracking-tight text-ink">
        What has happened with this patient, what matters, and where is the evidence?
      </h1>
      <p className="mt-3 max-w-3xl text-[15px] leading-relaxed text-ink-2">
        ClinIQ Nexus brings structured and unstructured hospital information into one patient-scoped workspace so a physician can understand
        the clinical journey in minutes — with every statement traceable to the note, PDF page, message or record it came from.
      </p>
      <div className="mt-8 grid gap-4 md:grid-cols-3">
        {STEPS.map((s, i) => (
          <div key={s.title} className="card relative p-5">
            <div className="mb-3 flex items-center gap-2">
              <span className="grid h-8 w-8 place-items-center rounded-lg bg-brand-50 text-brand-700"><s.icon className="h-4 w-4" aria-hidden /></span>
              <span className="text-[11px] font-semibold text-ink-3">STEP {i + 1}</span>
            </div>
            <h2 className="text-[15px] font-semibold text-ink">{s.title}</h2>
            <p className="mt-1.5 text-[13px] leading-relaxed text-ink-2">{s.body}</p>
            {i < 2 && <ArrowRight className="absolute -right-3.5 top-1/2 hidden h-5 w-5 -translate-y-1/2 text-lineStrong md:block" aria-hidden />}
          </div>
        ))}
      </div>

      <h2 className="mt-10 text-[15px] font-semibold text-ink">Start with a guided example</h2>
      <p className="mt-0.5 text-[13px] text-ink-3">Or choose any patient from the review worklist.</p>
      <div className="mt-3 grid gap-3 md:grid-cols-3">
        {featured.map((r) => r && (
          <Link key={r.patient_id} to={`/patients/${r.patient_id}`} className="card group p-4 transition-shadow hover:shadow-pop">
            <div className="text-[13.5px] font-semibold text-ink group-hover:text-brand-700">{r.display_name}</div>
            <div className="mt-0.5 text-[12.5px] text-ink-2">{r.care_program}</div>
            <div className="mt-3 flex items-center gap-1 text-[12.5px] font-medium text-brand-700">Open record <ArrowRight className="h-3.5 w-3.5" /></div>
          </Link>
        ))}
      </div>

      {t && (
        <div className="mt-10 grid grid-cols-2 gap-3 rounded-xl2 border border-line bg-surface p-5 sm:grid-cols-4">
          {[
            { icon: Stethoscope, v: t.encounters, l: "encounters" },
            { icon: FileStack, v: `${t.documents} · ${t.pages}`, l: "PDFs · pages" },
            { icon: MessagesSquare, v: t.threads, l: "portal threads" },
            { icon: ScanLine, v: t.imaging, l: "DICOM studies" },
          ].map((x) => (
            <div key={x.l} className="flex items-center gap-3">
              <x.icon className="h-5 w-5 text-ink-3" aria-hidden />
              <div><div className="text-lg font-semibold text-ink tabular">{x.v}</div><div className="text-[12px] text-ink-3">{x.l}</div></div>
            </div>
          ))}
        </div>
      )}
      <p className="mt-6 flex items-start gap-2 text-[12.5px] leading-relaxed text-ink-3">
        <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
        Technology demonstration on synthetic records only. Not a clinical decision-support system, not an EHR, and not validated for patient care.
        Imaging objects are synthetic test patterns and are never interpreted.
      </p>
    </div>
  );
}
