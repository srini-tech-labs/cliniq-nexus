import clsx from "clsx";
import { useMemo, useState } from "react";
import { ClassBadge, SectionTitle, SourceIcon, StatusChip } from "../components/ui";
import { useWorkspace, type EvidenceTarget } from "../lib/context";
import { CLASS_COLOR, fmtDate, fmtDateTime, fmtRange, num, toDate } from "../lib/format";
import type { Bundle } from "../lib/types";

const LANES = ["Encounters", "Notes & PDFs", "Medications", "Results", "Messages", "Imaging"] as const;
type Lane = (typeof LANES)[number];

interface Mark { lane: Lane; at: string; end?: string; color: string; label: string; target: EvidenceTarget; ring?: boolean; shape?: "dot" | "diamond" | "square" }

function Ribbon({ bundle }: { bundle: Bundle }) {
  const { openEvidence } = useWorkspace();
  const pid = bundle.patient.patient_id;
  const [hover, setHover] = useState<{ m: Mark; x: number; y: number } | null>(null);
  const marks: Mark[] = useMemo(() => {
    const out: Mark[] = [];
    bundle.encounters.forEach((e) => out.push({ lane: "Encounters", at: e.start_at, end: e.end_at, color: CLASS_COLOR[e.class_code], label: `${e.encounter_type} — ${e.reason}`, target: { type: "encounter", id: e.encounter_id, label: e.encounter_type, patientId: pid } }));
    bundle.notes.forEach((n) => out.push({ lane: "Notes & PDFs", at: n.authored_at, color: "#52514e", label: n.note_type, target: { type: "note", id: n.note_id, label: n.title, patientId: pid } }));
    bundle.documents.forEach((d) => out.push({ lane: "Notes & PDFs", at: d.authored_at, color: "#2a78d6", shape: "square", label: `PDF · ${d.title}`, target: { type: "document", id: d.document_id, label: d.title, page: 1, patientId: pid } }));
    bundle.medications.filter((m) => m.category !== "home").forEach((m) => out.push({ lane: "Medications", at: m.authored_on, color: "#2a78d6", shape: "diamond", label: `${m.action === "changed" ? "Changed" : "Started"} ${m.medication} ${m.dose}`, target: { type: "medication", id: m.medication_request_id, label: m.medication, patientId: pid } }));
    bundle.medications.filter((m) => m.status === "stopped" && !bundle.medications.some((x) => x.prior_request_id === m.medication_request_id) && m.end_date).forEach((m) => out.push({ lane: "Medications", at: m.end_date!, color: "#898781", shape: "diamond", label: `Stopped ${m.medication} ${m.dose}`, target: { type: "medication", id: m.medication_request_id, label: m.medication, patientId: pid } }));
    const labTimes = new Map<string, { flagged: number; n: number; id: string }>();
    bundle.observations.filter((o) => o.category === "laboratory").forEach((o) => {
      const cur = labTimes.get(o.effective_at) ?? { flagged: 0, n: 0, id: o.observation_id };
      cur.n += 1; if (o.interpretation === "H" || o.interpretation === "L") cur.flagged += 1;
      labTimes.set(o.effective_at, cur);
    });
    labTimes.forEach((v, at) => out.push({ lane: "Results", at, color: v.flagged ? "#eda100" : "#898781", ring: v.flagged > 0, label: `${v.n} lab results${v.flagged ? ` · ${v.flagged} outside range` : ""}`, target: { type: "observation", id: v.id, label: "Laboratory results", patientId: pid } }));
    bundle.threads.forEach((t) => t.messages.forEach((m) => out.push({ lane: "Messages", at: m.sent_at, color: m.sender_role === "patient" ? (t.status === "awaiting_reply" && m === t.messages[t.messages.length - 1] ? "#eda100" : "#52514e") : "#c3c2b7", label: `${m.sender_role === "patient" ? "Patient" : "Care team"}: ${t.subject}`, target: { type: "message", id: m.message_id, label: t.subject, patientId: pid } })));
    bundle.imaging.forEach((s) => out.push({ lane: "Imaging", at: s.study_at, color: "#52514e", shape: "square", label: `${s.ordered_procedure} (synthetic test pattern)`, target: { type: "imaging_report", id: s.report_id, label: s.ordered_procedure, patientId: pid } }));
    return out;
  }, [bundle, pid]);

  const t0 = Math.min(...marks.map((m) => toDate(m.at).getTime())) - 3 * 86400000;
  const t1 = Math.max(toDate(bundle.as_of).getTime(), ...marks.map((m) => toDate(m.end ?? m.at).getTime())) + 2 * 86400000;
  const W = 900, L = 118, R = 16, laneH = 30, top = 10, H = top + LANES.length * laneH + 26;
  const x = (iso: string) => L + ((toDate(iso).getTime() - t0) / (t1 - t0)) * (W - L - R);
  const ticks: string[] = [];
  const d = new Date(t0); d.setUTCDate(1); d.setUTCMonth(d.getUTCMonth() + 1);
  while (d.getTime() < t1) { ticks.push(d.toISOString()); d.setUTCMonth(d.getUTCMonth() + 1); }

  return (
    <div className="card relative p-4">
      <div className="mb-1 flex flex-wrap items-center gap-x-4 gap-y-1 text-[11.5px] text-ink-3">
        {Object.entries({ IMP: "Inpatient", EMER: "Emergency", AMB: "Ambulatory", VR: "Virtual" }).filter(([k]) => bundle.encounters.some((e) => e.class_code === k)).map(([k, v]) => (
          <span key={k} className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm" style={{ background: CLASS_COLOR[k] }} />{v}</span>
        ))}
        <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-full bg-[#eda100]" />Outside range / awaiting reply</span>
        <span className="ml-auto">Click any mark to open its source</span>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label="Timeline of encounters, documents, medications, results, messages and imaging">
        {LANES.map((lane, i) => (
          <g key={lane}>
            <text x={0} y={top + i * laneH + laneH / 2 + 4} className="fill-[#44516a] text-[11px] font-medium">{lane}</text>
            <line x1={L} x2={W - R} y1={top + (i + 1) * laneH} y2={top + (i + 1) * laneH} stroke="#eef1f5" />
          </g>
        ))}
        {ticks.map((t) => (
          <g key={t}>
            <line x1={x(t)} x2={x(t)} y1={top} y2={top + LANES.length * laneH} stroke="#eef1f5" />
            <text x={x(t)} y={H - 6} textAnchor="middle" className="fill-[#77839a] text-[10.5px]">{fmtDate(t, false).split(" ")[1]} {toDate(t).getUTCFullYear()}</text>
          </g>
        ))}
        <line x1={x(bundle.as_of)} x2={x(bundle.as_of)} y1={top - 4} y2={top + LANES.length * laneH} stroke="#0f1b2d" strokeDasharray="0" strokeWidth={1} opacity={0.35} />
        <text x={x(bundle.as_of) - 4} y={top + 2} textAnchor="end" className="fill-[#77839a] text-[10px]">as of {fmtDate(bundle.as_of, false)}</text>
        {marks.map((m, i) => {
          const li = LANES.indexOf(m.lane); const cy = top + li * laneH + laneH / 2; const cx = x(m.at);
          const common = {
            onMouseEnter: (e: React.MouseEvent) => setHover({ m, x: e.nativeEvent.offsetX, y: e.nativeEvent.offsetY }),
            onMouseLeave: () => setHover(null), onClick: () => openEvidence(m.target), style: { cursor: "pointer" },
            tabIndex: 0, role: "button", "aria-label": `${fmtDate(m.at)}: ${m.label}`,
            onKeyDown: (e: React.KeyboardEvent) => e.key === "Enter" && openEvidence(m.target),
          };
          if (m.end) {
            const w = Math.max(x(m.end) - cx, 6);
            return <rect key={i} x={cx} y={cy - 6} width={w} height={12} rx={4} fill={m.color} stroke="#fff" strokeWidth={2} {...common} />;
          }
          if (m.shape === "diamond") return <rect key={i} x={cx - 5} y={cy - 5} width={10} height={10} transform={`rotate(45 ${cx} ${cy})`} fill={m.color} stroke="#fff" strokeWidth={2} {...common} />;
          if (m.shape === "square") return <rect key={i} x={cx - 5} y={cy - 5} width={10} height={10} rx={2} fill={m.color} stroke="#fff" strokeWidth={2} {...common} />;
          return <circle key={i} cx={cx} cy={cy} r={5} fill={m.color} stroke={m.ring ? "#8f4a06" : "#fff"} strokeWidth={m.ring ? 1.5 : 2} {...common} />;
        })}
      </svg>
      {hover && (
        <div className="pointer-events-none absolute z-10 max-w-xs rounded-lg border border-line bg-surface px-3 py-2 text-[12px] shadow-pop"
          style={{ left: `calc(${(hover.x / W) * 100}% + 12px)`, top: hover.y + 10 }}>
          <div className="font-medium text-ink">{hover.m.label}</div>
          <div className="text-ink-3">{hover.m.end ? fmtRange(hover.m.at, hover.m.end) : fmtDateTime(hover.m.at)}</div>
        </div>
      )}
    </div>
  );
}

const FILTERS = ["All", "Notes & PDFs", "Medications", "Results", "Messages", "Imaging"] as const;

export default function JourneyTab({ bundle }: { bundle: Bundle }) {
  const { openEvidence } = useWorkspace();
  const pid = bundle.patient.patient_id;
  const [filter, setFilter] = useState<(typeof FILTERS)[number]>("All");
  const show = (f: string) => filter === "All" || filter === f;
  const encs = [...bundle.encounters].reverse();
  const open = (t: Omit<EvidenceTarget, "patientId">) => openEvidence({ ...t, patientId: pid });
  const row = (key: string, type: string, date: string, content: React.ReactNode, onClick: () => void) => (
    <li key={key}>
      <button onClick={onClick} className="flex w-full items-start gap-3 rounded-lg px-2 py-1.5 text-left text-[13px] text-ink-2 hover:bg-sunken/70">
        <SourceIcon type={type} className="mt-0.5 text-ink-3" />
        <span className="flex-1">{content}</span>
        <span className="shrink-0 text-[11.5px] text-ink-3 tabular">{fmtDate(date, false)}</span>
      </button>
    </li>
  );

  return (
    <div className="space-y-6">
      <section>
        <SectionTitle title="Longitudinal overview" hint={`${fmtDate(bundle.encounters[0]?.start_at)} to records as of ${fmtDate(bundle.as_of)}`} />
        <Ribbon bundle={bundle} />
      </section>
      <section>
        <SectionTitle title="Encounters and linked records" hint="Newest first. Records are grouped under the encounter they are linked to in the source data." action={
          <div className="flex flex-wrap gap-1" role="group" aria-label="Filter record types">
            {FILTERS.map((f) => (
              <button key={f} onClick={() => setFilter(f)} aria-pressed={filter === f}
                className={clsx("chip", filter === f ? "border-brand-500/30 bg-brand-50 text-brand-700" : "border-line bg-surface text-ink-2 hover:bg-sunken")}>{f}</button>
            ))}
          </div>} />
        <ol className="relative space-y-4 border-l-2 border-line pl-6">
          {encs.map((e) => {
            const notes = bundle.notes.filter((n) => n.encounter_id === e.encounter_id);
            const docs = bundle.documents.filter((d) => d.encounter_id === e.encounter_id);
            const meds = bundle.medications.filter((m) => m.encounter_id === e.encounter_id);
            const labs = bundle.observations.filter((o) => o.encounter_id === e.encounter_id && o.category === "laboratory");
            const threads = bundle.threads.filter((t) => t.encounter_id === e.encounter_id);
            const studies = bundle.imaging.filter((s) => s.encounter_id === e.encounter_id);
            const dx = bundle.conditions.filter((c) => c.encounter_id === e.encounter_id);
            return (
              <li key={e.encounter_id} className="relative">
                <span className="absolute -left-[33px] top-4 h-4 w-4 rounded-full border-[3px] border-page" style={{ background: CLASS_COLOR[e.class_code] }} aria-hidden />
                <article className="card p-4">
                  <button className="w-full text-left" onClick={() => open({ type: "encounter", id: e.encounter_id, label: `${e.encounter_type} · ${fmtDate(e.start_at)}` })}>
                    <div className="flex flex-wrap items-center gap-2">
                      <ClassBadge code={e.class_code} />
                      <h3 className="text-[14.5px] font-semibold text-ink">{e.encounter_type}</h3>
                      <span className="text-[12.5px] text-ink-3">{fmtRange(e.start_at, e.end_at)} · {e.service}</span>
                    </div>
                    <p className="mt-1 text-[13px] text-ink-2"><span className="text-ink-3">Reason:</span> {e.reason} · <span className="text-ink-3">Disposition:</span> {e.disposition}</p>
                    {dx.length > 0 && <p className="mt-0.5 text-[12.5px] text-ink-3">{dx.map((c) => `${c.display} (${c.code})`).join(" · ")}</p>}
                  </button>
                  <ul className="mt-2 space-y-0.5 border-t border-line pt-2">
                    {show("Notes & PDFs") && notes.map((n) => row(n.note_id, "clinical_note", n.authored_at, <><span className="font-medium text-ink">{n.note_type}</span> · {n.author.split(" — ")[0]}</>, () => open({ type: "note", id: n.note_id, label: n.title })))}
                    {show("Notes & PDFs") && docs.map((d) => row(d.document_id, "document", d.authored_at, <><span className="font-medium text-ink">{d.title}</span> · PDF, {d.page_count} p. {!d.has_text_layer && <span className="text-attn-700">· scanned</span>}</>, () => open({ type: "document", id: d.document_id, label: d.title, page: 1 })))}
                    {show("Medications") && meds.map((m) => row(m.medication_request_id, "medication", m.authored_on, <><span className="font-medium text-ink">{m.action === "reported" ? "Home medication" : m.action === "changed" ? "Dose changed" : "Started"}: {m.medication} {m.dose}</span> · {m.frequency} {m.status !== "active" && <StatusChip status={m.status} />}</>, () => open({ type: "medication", id: m.medication_request_id, label: m.medication })))}
                    {show("Results") && labs.length > 0 && row(`${e.encounter_id}-labs`, "observation", labs[0].effective_at, <><span className="font-medium text-ink">{labs.length} laboratory results</span> · {labs.filter((o) => o.interpretation !== "N").map((o) => `${o.name} ${num(o.value)} ${o.interpretation}`).join(", ") || "all within reference range"}</>, () => open({ type: "observation", id: labs[0].observation_id, label: labs[0].name }))}
                    {show("Imaging") && studies.map((s) => row(s.study_id, "imaging_report", s.study_at, <><span className="font-medium text-ink">{s.ordered_procedure}</span> · synthetic test pattern, report linked</>, () => open({ type: "imaging_report", id: s.report_id, label: s.ordered_procedure })))}
                    {show("Messages") && threads.map((t) => row(t.thread_id, "thread", t.opened_at, <><span className="font-medium text-ink">Portal: {t.subject}</span> · {t.message_count} message{t.message_count === 1 ? "" : "s"} <StatusChip status={t.status} /></>, () => open({ type: "thread", id: t.thread_id, label: t.subject })))}
                  </ul>
                </article>
              </li>
            );
          })}
        </ol>
      </section>
    </div>
  );
}
