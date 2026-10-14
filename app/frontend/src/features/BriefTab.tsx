import clsx from "clsx";
import {
  AlertTriangle, ArrowRight, CalendarCheck, ClipboardList, HeartPulse, Info, ListChecks, Pill, Sparkles,
} from "lucide-react";
import { ClassBadge, SectionTitle, SourceIcon } from "../components/ui";
import { useWorkspace } from "../lib/context";
import { fmtDate, fmtRange, num } from "../lib/format";
import type { BriefItem, Bundle, Observation, VitalTile } from "../lib/types";

const ASK: Record<string, string> = {
  acute_care: "What brought this patient to the hospital recently?",
  awaiting_reply: "Are there portal messages awaiting a reply?",
  routed: "Are there portal messages awaiting a reply?",
  medication_changes: "What medication changes are recorded?",
  abnormal_results: "What are the latest laboratory results?",
  overdue_follow_up: "What follow-up is documented and is any of it still open?",
  unsearchable_documents: "What information cannot be established from the available records?",
};

function Item({ item, pid }: { item: BriefItem; pid: string }) {
  const { openEvidence, askAssistant } = useWorkspace();
  const attn = item.severity === "attention";
  return (
    <li className={clsx("card relative overflow-hidden p-4 pl-5", attn && "border-attn-600/25")}>
      <span className={clsx("absolute inset-y-0 left-0 w-1", attn ? "bg-attn-600" : "bg-brand-500/50")} aria-hidden />
      <div className="flex items-start gap-3">
        {attn ? <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-attn-600" aria-label="Needs attention" />
          : <Info className="mt-0.5 h-4 w-4 shrink-0 text-brand-600" aria-label="Information" />}
        <div className="min-w-0 flex-1">
          <h3 className="text-[14px] font-semibold text-ink">{item.title}</h3>
          <p className="mt-0.5 text-[13px] leading-relaxed text-ink-2">{item.detail}</p>
          <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
            {item.refs.slice(0, 4).map((r) => (
              <button key={r.type + r.id} onClick={() => openEvidence({ ...r, patientId: pid, type: r.type === "thread" ? "thread" : r.type })}
                className="chip border-line bg-surface text-ink-2 hover:border-brand-500/40 hover:text-brand-700">
                <SourceIcon type={r.type} className="h-3 w-3" />{r.label}
              </button>
            ))}
            {item.refs.length > 4 && <span className="text-[11.5px] text-ink-3">+{item.refs.length - 4} more</span>}
            {ASK[item.kind] && (
              <button onClick={() => askAssistant(ASK[item.kind])} className="chip ml-auto border-brand-500/25 bg-brand-50 text-brand-700 hover:bg-brand-100">
                <Sparkles className="h-3 w-3" /> Ask
              </button>
            )}
          </div>
        </div>
      </div>
    </li>
  );
}

function Spark({ values }: { values: number[] }) {
  if (values.length < 2) return <span className="text-[11px] text-ink-3">single reading</span>;
  const w = 84, h = 26, lo = Math.min(...values), hi = Math.max(...values), span = hi - lo || 1;
  const pts = values.map((v, i) => [2 + (i * (w - 4)) / (values.length - 1), h - 3 - ((v - lo) / span) * (h - 6)]);
  return (
    <svg width={w} height={h} aria-hidden className="overflow-visible">
      <polyline points={pts.map((p) => p.join(",")).join(" ")} fill="none" stroke="#2a78d6" strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
      <circle cx={pts[pts.length - 1][0]} cy={pts[pts.length - 1][1]} r={3.5} fill="#2a78d6" stroke="#fff" strokeWidth={2} />
    </svg>
  );
}

function VitalCard({ v, series, pid }: { v: VitalTile; series: Observation[]; pid: string }) {
  const { openEvidence } = useWorkspace();
  const value = v.key === "sbp" ? `${num(v.value)}/${num(v.value_diastolic ?? 0)}` : num(v.value);
  const prev = v.previous === null ? null : v.key === "sbp" ? `${num(v.previous)}/${num(v.previous_diastolic ?? 0)}` : num(v.previous);
  return (
    <button onClick={() => openEvidence({ type: "observation", id: v.observation_id, label: `${v.name} · ${fmtDate(v.at)}`, patientId: pid })}
      className="rounded-xl border border-line bg-surface p-3 text-left hover:border-brand-500/40">
      <div className="text-[11.5px] text-ink-3">{v.key === "sbp" ? "Blood pressure" : v.name}</div>
      <div className="mt-0.5 flex items-end justify-between gap-2">
        <div><span className="text-[19px] font-semibold tracking-tight text-ink">{value}</span> <span className="text-[11.5px] text-ink-3">{v.unit}</span></div>
        <Spark values={series.map((o) => o.value)} />
      </div>
      <div className="mt-0.5 text-[11px] text-ink-3">{fmtDate(v.at, false)}{prev ? ` · prior ${prev} (${fmtDate(v.previous_at, false)})` : ""} · n={v.count}</div>
    </button>
  );
}

export default function BriefTab({ bundle, onNavigate }: { bundle: Bundle; onNavigate: (tab: string) => void }) {
  const pid = bundle.patient.patient_id;
  const { openEvidence } = useWorkspace();
  const b = bundle.brief;
  const active = bundle.medications.filter((m) => m.status === "active");
  const recent = [
    ...bundle.encounters.map((e) => ({ date: e.start_at, kind: "encounter", node: <><ClassBadge code={e.class_code} compact /> <span className="font-medium text-ink">{e.encounter_type}</span> · {e.reason}</>, open: () => openEvidence({ type: "encounter", id: e.encounter_id, label: `${e.encounter_type} · ${fmtDate(e.start_at)}`, patientId: pid }) })),
    ...bundle.documents.map((d) => ({ date: d.authored_at, kind: "document", node: <><span className="font-medium text-ink">{d.title}</span> · {d.page_count} p.</>, open: () => openEvidence({ type: "document", id: d.document_id, label: d.title, page: 1, patientId: pid }) })),
    ...bundle.threads.map((t) => ({ date: t.opened_at, kind: "thread", node: <><span className="font-medium text-ink">Portal: {t.subject}</span> · {t.status.replace("_", " ")}</>, open: () => openEvidence({ type: "thread", id: t.thread_id, label: t.subject, patientId: pid }) })),
  ].sort((a, c) => c.date.localeCompare(a.date)).slice(0, 7);

  return (
    <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_340px]">
      <div className="space-y-6">
        <section>
          <SectionTitle icon={ListChecks} title="What needs attention" hint="Derived deterministically from the records — each item links to its evidence." />
          {b.items.length ? <ul className="space-y-2.5">{b.items.map((i) => <Item key={i.id} item={i} pid={pid} />)}</ul>
            : <p className="card p-4 text-sm text-ink-3">No open items, acute episodes or recent changes are documented.</p>}
        </section>
        <section>
          <SectionTitle icon={ClipboardList} title="Recent course" action={<button className="btn-ghost text-[12.5px]" onClick={() => onNavigate("journey")}>Full journey <ArrowRight className="h-3.5 w-3.5" /></button>} />
          <ol className="card divide-y divide-line">
            {recent.map((r, i) => (
              <li key={i}>
                <button onClick={r.open} className="flex w-full items-center gap-3 px-4 py-2.5 text-left text-[13px] text-ink-2 hover:bg-sunken/60">
                  <span className="w-16 shrink-0 text-[12px] text-ink-3 tabular">{fmtDate(r.date, false)}</span>
                  <SourceIcon type={r.kind} className="text-ink-3" />
                  <span className="truncate">{r.node}</span>
                </button>
              </li>
            ))}
          </ol>
        </section>
      </div>
      <div className="space-y-6">
        <section>
          <SectionTitle icon={HeartPulse} title="Vitals at a glance" action={<button className="btn-ghost text-[12.5px]" onClick={() => onNavigate("trends")}>Trends <ArrowRight className="h-3.5 w-3.5" /></button>} />
          <div className="grid grid-cols-2 gap-2">
            {b.vitals.filter((v) => v.key !== "rr").slice(0, 6).map((v) => (
              <VitalCard key={v.key} v={v} pid={pid} series={bundle.observations.filter((o) => o.measure_key === v.key)} />
            ))}
          </div>
          {b.vitals.length === 0 && <p className="text-sm text-ink-3">No vital signs recorded.</p>}
        </section>
        <section>
          <SectionTitle title="Problem list" hint="Latest status per coded diagnosis (ICD-10-CM)" />
          <ul className="card divide-y divide-line">
            {bundle.problems.map((c) => (
              <li key={c.condition_id} className="flex items-center justify-between gap-2 px-4 py-2 text-[13px]">
                <span className={clsx(c.clinical_status === "resolved" ? "text-ink-3 line-through decoration-ink-3/40" : "text-ink")}>{c.display}</span>
                <span className="shrink-0 text-[11.5px] text-ink-3">{c.code} · {c.clinical_status}</span>
              </li>
            ))}
          </ul>
        </section>
        <section>
          <SectionTitle icon={Pill} title={`Active medications (${active.length})`} action={<button className="btn-ghost text-[12.5px]" onClick={() => onNavigate("medications")}>History <ArrowRight className="h-3.5 w-3.5" /></button>} />
          <ul className="card divide-y divide-line">
            {active.map((m) => (
              <li key={m.medication_request_id}>
                <button onClick={() => openEvidence({ type: "medication", id: m.medication_request_id, label: m.medication, patientId: pid })} className="w-full px-4 py-2 text-left hover:bg-sunken/60">
                  <div className="text-[13px] font-medium text-ink">{m.medication} <span className="font-normal text-ink-2">{m.dose}</span></div>
                  <div className="text-[11.5px] text-ink-3">{m.route} · {m.frequency}{m.category === "home" ? " · home medication" : ` · since ${fmtDate(m.authored_on, false)}`}</div>
                </button>
              </li>
            ))}
          </ul>
        </section>
        {b.upcoming.length > 0 && (
          <section>
            <SectionTitle icon={CalendarCheck} title="Scheduled next" />
            <ul className="card divide-y divide-line">
              {b.upcoming.map((f) => (
                <li key={f.follow_up_id} className="flex justify-between gap-2 px-4 py-2 text-[13px]"><span className="text-ink">{f.description}</span><span className="shrink-0 text-ink-3">{fmtDate(f.due_date, false)}</span></li>
              ))}
            </ul>
          </section>
        )}
        {b.last_encounter && (
          <p className="text-[12px] text-ink-3">Last encounter {fmtRange(b.last_encounter.start_at, b.last_encounter.end_at)} · {b.days_since_last_encounter} days before records' as-of date.</p>
        )}
      </div>
    </div>
  );
}
