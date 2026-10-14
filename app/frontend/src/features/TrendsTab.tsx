import clsx from "clsx";
import { FlaskConical, HeartPulse, Table2 } from "lucide-react";
import { useMemo, useState } from "react";
import { CartesianGrid, Line, LineChart, ReferenceArea, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { SectionTitle } from "../components/ui";
import { useWorkspace } from "../lib/context";
import { fmtDate, fmtDateTime, num, toDate } from "../lib/format";
import type { Bundle, Observation } from "../lib/types";

const BLUE = "#2a78d6", ORANGE = "#eb6834";
const VITAL_ORDER = ["bp", "hr", "spo2", "temp", "wt", "rr", "pain"];

interface Series { key: string; label: string; color: string; points: Observation[] }
interface Panel { id: string; title: string; unit: string; series: Series[]; refLow: number | null; refHigh: number | null; loinc: string }

function buildPanels(obs: Observation[], category: "vital-signs" | "laboratory"): Panel[] {
  const by = new Map<string, Observation[]>();
  obs.filter((o) => o.category === category).forEach((o) => by.set(o.measure_key, [...(by.get(o.measure_key) ?? []), o]));
  const panels: Panel[] = [];
  if (category === "vital-signs" && by.has("sbp")) {
    panels.push({ id: "bp", title: "Blood pressure", unit: "mmHg", loinc: "8480-6 / 8462-4", refLow: null, refHigh: null, series: [
      { key: "sbp", label: "Systolic", color: BLUE, points: by.get("sbp")! },
      { key: "dbp", label: "Diastolic", color: ORANGE, points: by.get("dbp") ?? [] },
    ] });
  }
  by.forEach((points, key) => {
    if (key === "sbp" || key === "dbp") return;
    const o = points[0];
    panels.push({ id: key, title: o.name, unit: o.display_unit, loinc: o.code, refLow: o.ref_low, refHigh: o.ref_high, series: [{ key, label: o.name, color: BLUE, points }] });
  });
  if (category === "vital-signs") panels.sort((a, b) => VITAL_ORDER.indexOf(a.id) - VITAL_ORDER.indexOf(b.id));
  else panels.sort((a, b) => b.series[0].points.length - a.series[0].points.length || a.title.localeCompare(b.title));
  return panels;
}

function niceTicks(lo: number, hi: number): number[] {
  const span = hi - lo || Math.abs(hi) || 1;
  const raw = span / 4;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw)!;
  const start = Math.floor(lo / step) * step, end = Math.ceil(hi / step) * step;
  const out: number[] = [];
  for (let v = start; v <= end + step / 2; v += step) out.push(+v.toFixed(6));
  return out;
}

function TipBox({ active, payload, unit }: any) {
  if (!active || !payload?.length) return null;
  const p = payload[0].payload;
  return (
    <div className="rounded-lg border border-line bg-surface px-3 py-2 text-[12px] shadow-pop">
      <div className="text-ink-3">{fmtDateTime(new Date(p.t).toISOString())}</div>
      {payload.map((s: any) => (
        <div key={s.dataKey} className="flex items-center gap-2 text-ink">
          <span className="h-2 w-2 rounded-full" style={{ background: s.color }} />{s.name}: <span className="font-semibold">{num(s.value)} {unit}</span>
          {p[`${s.dataKey}_flag`] && p[`${s.dataKey}_flag`] !== "N" && <span className="text-attn-700">({p[`${s.dataKey}_flag`]})</span>}
        </div>
      ))}
    </div>
  );
}

function ChartCard({ panel, domain, episodes, showTable, pid }: { panel: Panel; domain: [number, number]; episodes: [number, number][]; showTable: boolean; pid: string }) {
  const { openEvidence } = useWorkspace();
  const n = panel.series[0].points.length;
  const data = useMemo(() => {
    const rows = new Map<number, any>();
    panel.series.forEach((s) => s.points.forEach((o) => {
      const t = toDate(o.effective_at).getTime();
      const row = rows.get(t) ?? { t };
      row[s.key] = o.value; row[`${s.key}_flag`] = o.interpretation; row[`${s.key}_id`] = o.observation_id;
      rows.set(t, row);
    }));
    return [...rows.values()].sort((a, b) => a.t - b.t);
  }, [panel]);
  const values = panel.series.flatMap((s) => s.points.map((p) => p.value));
  const lo = Math.min(...values, panel.refLow ?? Infinity), hi = Math.max(...values, panel.refHigh ?? -Infinity);
  const pad = (hi - lo) * 0.12 || Math.abs(hi) * 0.05 || 1;
  const ticks = niceTicks(lo - pad, hi + pad);
  const last = panel.series[0].points[n - 1];
  const sparse = n === 1 ? "Single measurement — no trend can be shown." : n === 2 ? "Two measurements — a comparison, not a trend." : null;
  const openPoint = (row: any) => {
    const id = row?.activePayload?.[0]?.payload?.[`${panel.series[0].key}_id`];
    if (id) openEvidence({ type: "observation", id, label: panel.title, patientId: pid });
  };

  return (
    <article className="card flex flex-col p-4">
      <div className="flex items-start justify-between gap-2">
        <div>
          <h3 className="text-[13.5px] font-semibold text-ink">{panel.title}</h3>
          <p className="text-[11.5px] text-ink-3">{panel.unit} · LOINC {panel.loinc} · n={n}</p>
        </div>
        <div className="text-right">
          <div className="text-[17px] font-semibold tracking-tight text-ink">
            {panel.id === "bp" ? `${num(last.value)}/${num(panel.series[1].points[panel.series[1].points.length - 1]?.value ?? 0)}` : num(last.value)}
            <span className="ml-1 text-[11.5px] font-normal text-ink-3">{panel.unit}</span>
          </div>
          <div className="text-[11px] text-ink-3">latest · {fmtDate(last.effective_at, false)}</div>
        </div>
      </div>
      {panel.series.length > 1 && (
        <div className="mt-2 flex gap-3 text-[11.5px] text-ink-2">
          {panel.series.map((s) => <span key={s.key} className="flex items-center gap-1.5"><span className="h-0.5 w-3.5 rounded" style={{ background: s.color }} />{s.label}</span>)}
        </div>
      )}
      {showTable || n === 1 ? (
        <table className="mt-3 w-full text-[12.5px]">
          <thead><tr className="text-left text-ink-3"><th className="py-1 font-medium">Recorded</th>{panel.series.map((s) => <th key={s.key} className="py-1 text-right font-medium">{s.label}</th>)}</tr></thead>
          <tbody>
            {data.map((r) => (
              <tr key={r.t} className="border-t border-line">
                <td className="py-1 text-ink-2">{fmtDateTime(new Date(r.t).toISOString())}</td>
                {panel.series.map((s) => <td key={s.key} className="py-1 text-right font-medium tabular text-ink">{r[s.key] !== undefined ? num(r[s.key]) : "—"}{r[`${s.key}_flag`] && r[`${s.key}_flag`] !== "N" ? ` ${r[`${s.key}_flag`]}` : ""}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <div className="mt-2 h-44">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: -12 }} onClick={openPoint}>
              <CartesianGrid vertical={false} />
              {episodes.map(([a, b], i) => <ReferenceArea key={i} x1={a} x2={b} fill="#1baf7a" fillOpacity={0.09} ifOverflow="hidden" />)}
              {panel.refLow !== null && panel.refHigh !== null && (
                <ReferenceArea y1={panel.refLow} y2={panel.refHigh} fill="#77839a" fillOpacity={0.08} ifOverflow="hidden" />
              )}
              <XAxis dataKey="t" type="number" scale="time" domain={domain} tickFormatter={(t) => fmtDate(new Date(t).toISOString(), false)} tickLine={false} axisLine={{ stroke: "#cfd6e0" }} minTickGap={28} />
              <YAxis domain={[ticks[0], ticks[ticks.length - 1]]} ticks={ticks} interval={0} tickLine={false} axisLine={false} width={44} tickFormatter={(v) => num(v)} />
              <Tooltip content={<TipBox unit={panel.unit} />} cursor={{ stroke: "#cfd6e0" }} />
              {panel.series.map((s) => (
                <Line key={s.key} dataKey={s.key} name={s.label} stroke={s.color} strokeWidth={2} connectNulls isAnimationActive={false}
                  dot={{ r: 4, fill: s.color, stroke: "#fff", strokeWidth: 2 }} activeDot={{ r: 6, stroke: "#fff", strokeWidth: 2, cursor: "pointer" }} />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
      <p className={clsx("mt-2 text-[11.5px]", sparse ? "text-attn-700" : "text-ink-3")}>
        {sparse ?? (panel.refLow !== null && panel.refHigh !== null ? `Gray band: reference ${num(panel.refLow)}–${num(panel.refHigh)} ${panel.unit} (typical adult range, context only).` :
          panel.refHigh !== null ? `Reference ≤ ${num(panel.refHigh)} ${panel.unit}.` : panel.refLow !== null ? `Reference ≥ ${num(panel.refLow)} ${panel.unit}.` : "No reference range applies.")}
      </p>
    </article>
  );
}

export default function TrendsTab({ bundle }: { bundle: Bundle }) {
  const [table, setTable] = useState(false);
  const pid = bundle.patient.patient_id;
  const times = bundle.observations.map((o) => toDate(o.effective_at).getTime());
  const domain: [number, number] = [Math.min(...times) - 4 * 86400000, Math.max(...times) + 4 * 86400000];
  const episodes: [number, number][] = bundle.encounters.filter((e) => e.class_code === "IMP").map((e) => [toDate(e.start_at).getTime(), toDate(e.end_at).getTime()]);
  const vitals = buildPanels(bundle.observations, "vital-signs");
  const labs = buildPanels(bundle.observations, "laboratory");
  const toggle = (
    <button className="btn-outline text-[12.5px]" onClick={() => setTable(!table)} aria-pressed={table}><Table2 className="h-3.5 w-3.5" />{table ? "Show charts" : "Show tables"}</button>
  );
  return (
    <div className="space-y-7">
      <div className="flex flex-wrap items-center gap-x-5 gap-y-1 rounded-xl border border-line bg-surface px-4 py-2.5 text-[12px] text-ink-2">
        <span>Each chart has its own scale and units — measurements are never combined on one axis.</span>
        {episodes.length > 0 && <span className="flex items-center gap-1.5"><span className="h-3 w-4 rounded-sm bg-[#1baf7a]/20" />Inpatient stay</span>}
        <span className="flex items-center gap-1.5"><span className="h-3 w-4 rounded-sm bg-[#77839a]/20" />Reference range (context)</span>
        <span>Click a point to open the source measurement.</span>
      </div>
      <section>
        <SectionTitle icon={HeartPulse} title="Vital signs" hint={`${bundle.observations.filter((o) => o.category === "vital-signs").length} measurements across ${new Set(bundle.observations.filter((o) => o.category === "vital-signs").map((o) => o.encounter_id)).size} encounters`} action={toggle} />
        <div className="grid gap-4 lg:grid-cols-2 2xl:grid-cols-3">{vitals.map((p) => <ChartCard key={p.id} panel={p} domain={domain} episodes={episodes} showTable={table} pid={pid} />)}</div>
      </section>
      <section>
        <SectionTitle icon={FlaskConical} title="Laboratory results" hint="Flags (H/L) are recorded by the laboratory relative to its reference range." />
        {labs.length ? <div className="grid gap-4 lg:grid-cols-2 2xl:grid-cols-3">{labs.map((p) => <ChartCard key={p.id} panel={p} domain={domain} episodes={episodes} showTable={table} pid={pid} />)}</div>
          : <p className="card p-4 text-sm text-ink-3">No laboratory results are documented for this patient.</p>}
      </section>
    </div>
  );
}
