import { useState } from "react";
import { SectionTitle, StatusChip } from "../components/ui";
import { useWorkspace } from "../lib/context";
import { fmtDate, toDate } from "../lib/format";
import type { Bundle, Medication } from "../lib/types";

const COLOR: Record<string, string> = { active: "#1baf7a", stopped: "#898781", completed: "#86b6ef" };

function Gantt({ bundle }: { bundle: Bundle }) {
  const { openEvidence } = useWorkspace();
  const pid = bundle.patient.patient_id;
  const [hover, setHover] = useState<{ m: Medication; x: number; y: number } | null>(null);
  const names = [...new Set(bundle.medications.map((m) => m.medication))];
  const asOf = toDate(bundle.as_of).getTime();
  const starts = bundle.medications.map((m) => toDate(m.authored_on).getTime());
  const t0 = Math.min(...starts, ...bundle.encounters.map((e) => toDate(e.start_at).getTime())) - 5 * 86400000;
  const t1 = asOf + 3 * 86400000;
  const W = 900, L = 190, R = 12, rowH = 26, top = 8, H = top + names.length * rowH + 24;
  const x = (t: number) => L + ((t - t0) / (t1 - t0)) * (W - L - R);
  const ticks: number[] = [];
  const d = new Date(t0); d.setUTCDate(1); d.setUTCMonth(d.getUTCMonth() + 1);
  while (d.getTime() < t1) { ticks.push(d.getTime()); d.setUTCMonth(d.getUTCMonth() + 1); }
  return (
    <div className="card relative p-4">
      <div className="mb-2 flex flex-wrap gap-4 text-[11.5px] text-ink-3">
        {Object.entries({ active: "Active", completed: "Completed course", stopped: "Stopped / replaced" }).map(([k, v]) => (
          <span key={k} className="flex items-center gap-1.5"><span className="h-2.5 w-4 rounded-sm" style={{ background: COLOR[k] }} />{v}</span>
        ))}
        <span className="flex items-center gap-1.5"><span className="h-2.5 w-4 rounded-sm border border-dashed border-ink-3" />Inpatient-only order</span>
        <span className="ml-auto">Bars run from order date to end date (or the records' as-of date)</span>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label="Medication order timeline">
        {ticks.map((t) => (
          <g key={t}>
            <line x1={x(t)} x2={x(t)} y1={top} y2={top + names.length * rowH} stroke="#eef1f5" />
            <text x={x(t)} y={H - 6} textAnchor="middle" className="fill-[#77839a] text-[10.5px]">{fmtDate(new Date(t).toISOString(), false).split(" ")[1]}</text>
          </g>
        ))}
        <line x1={x(asOf)} x2={x(asOf)} y1={top - 2} y2={top + names.length * rowH} stroke="#0f1b2d" opacity={0.35} />
        {names.map((name, i) => {
          const y = top + i * rowH;
          return (
            <g key={name}>
              <text x={0} y={y + rowH / 2 + 4} className="fill-[#0f1b2d] text-[11.5px]">{name.length > 28 ? name.slice(0, 27) + "…" : name}</text>
              <line x1={L} x2={W - R} y1={y + rowH} y2={y + rowH} stroke="#f2f4f7" />
              {bundle.medications.filter((m) => m.medication === name).map((m) => {
                const a = toDate(m.authored_on).getTime();
                const b = m.end_date ? toDate(m.end_date).getTime() : asOf;
                const inpatient = m.category === "inpatient";
                return (
                  <g key={m.medication_request_id} style={{ cursor: "pointer" }} tabIndex={0} role="button"
                    aria-label={`${m.medication} ${m.dose}, ${m.status}, from ${fmtDate(m.authored_on)}`}
                    onClick={() => openEvidence({ type: "medication", id: m.medication_request_id, label: m.medication, patientId: pid })}
                    onKeyDown={(e) => e.key === "Enter" && openEvidence({ type: "medication", id: m.medication_request_id, label: m.medication, patientId: pid })}
                    onMouseEnter={(e) => setHover({ m, x: e.nativeEvent.offsetX, y: e.nativeEvent.offsetY })} onMouseLeave={() => setHover(null)}>
                    <rect x={x(a)} y={y + 6} width={Math.max(x(b) - x(a), 5)} height={rowH - 12} rx={4}
                      fill={inpatient ? "#fff" : COLOR[m.status]} stroke={inpatient ? "#77839a" : "#fff"} strokeDasharray={inpatient ? "3 2" : undefined} strokeWidth={inpatient ? 1 : 2} />
                    {x(b) - x(a) > 70 && !inpatient && <text x={x(a) + 6} y={y + rowH / 2 + 4} className="fill-white text-[10.5px] font-semibold">{m.dose.split(",")[0]}</text>}
                  </g>
                );
              })}
            </g>
          );
        })}
      </svg>
      {hover && (
        <div className="pointer-events-none absolute z-10 rounded-lg border border-line bg-surface px-3 py-2 text-[12px] shadow-pop" style={{ left: `calc(${(hover.x / W) * 100}% + 12px)`, top: hover.y + 12 }}>
          <div className="font-medium text-ink">{hover.m.medication} {hover.m.dose}</div>
          <div className="text-ink-2">{hover.m.route} · {hover.m.frequency}</div>
          <div className="text-ink-3">{fmtDate(hover.m.authored_on)} → {hover.m.end_date ? fmtDate(hover.m.end_date) : "ongoing"} · {hover.m.status}</div>
        </div>
      )}
    </div>
  );
}

export default function MedicationsTab({ bundle }: { bundle: Bundle }) {
  const { openEvidence } = useWorkspace();
  const pid = bundle.patient.patient_id;
  const replaced = new Set(bundle.medications.map((m) => m.prior_request_id).filter(Boolean));
  const groups: [string, string, Medication[]][] = [
    ["Active", "Current orders and documented home medications", bundle.medications.filter((m) => m.status === "active")],
    ["Changed or stopped", "Dose changes reference the prior order", bundle.medications.filter((m) => m.status === "stopped")],
    ["Completed courses", "Time-limited outpatient courses that ended", bundle.medications.filter((m) => m.status === "completed" && m.category !== "inpatient")],
    ["Inpatient-only", "Administered during a hospital stay; not continued at discharge", bundle.medications.filter((m) => m.category === "inpatient")],
  ];
  return (
    <div className="space-y-6">
      <section>
        <SectionTitle title="Medication history" hint="Orders recorded as FHIR MedicationRequest resources. Administration and adherence are not recorded." />
        <Gantt bundle={bundle} />
      </section>
      {groups.map(([title, hint, meds]) => meds.length > 0 && (
        <section key={title}>
          <SectionTitle title={`${title} (${meds.length})`} hint={hint} />
          <div className="card overflow-x-auto">
            <table className="w-full min-w-[720px] text-[13px]">
              <thead><tr className="border-b border-line bg-sunken/60 text-left text-[11.5px] uppercase tracking-wide text-ink-3">
                <th className="px-4 py-2 font-semibold">Medication</th><th className="px-3 py-2 font-semibold">Sig</th><th className="px-3 py-2 font-semibold">Ordered</th>
                <th className="px-3 py-2 font-semibold">Status</th><th className="px-3 py-2 font-semibold">Reason / note</th>
              </tr></thead>
              <tbody>
                {meds.map((m) => {
                  const prior = bundle.medications.find((x) => x.medication_request_id === m.prior_request_id);
                  return (
                    <tr key={m.medication_request_id} onClick={() => openEvidence({ type: "medication", id: m.medication_request_id, label: m.medication, patientId: pid })}
                      className="cursor-pointer border-b border-line last:border-0 hover:bg-sunken/60">
                      <td className="px-4 py-2.5 font-medium text-ink">{m.medication}{prior && <div className="text-[11.5px] font-normal text-ink-3">was {prior.dose}</div>}</td>
                      <td className="px-3 py-2.5 text-ink-2">{m.dose} · {m.route} · {m.frequency}</td>
                      <td className="px-3 py-2.5 text-ink-2 tabular">{fmtDate(m.authored_on)}{m.category === "home" && <div className="text-[11.5px] text-ink-3">home (reported)</div>}</td>
                      <td className="px-3 py-2.5"><StatusChip status={m.status} />{m.end_date && <div className="mt-0.5 text-[11.5px] text-ink-3">{fmtDate(m.end_date)}</div>}</td>
                      <td className="px-3 py-2.5 text-ink-2">{m.stop_reason ?? m.reason}{replaced.has(m.medication_request_id) && <span className="text-ink-3"> · replaced by new dose</span>}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </section>
      ))}
    </div>
  );
}
