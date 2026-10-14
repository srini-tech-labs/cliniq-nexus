import { useQuery } from "@tanstack/react-query";
import { Activity, BadgeCheck, FileStack, Inbox, MessagesSquare, ScanLine, ShieldAlert, ShieldCheck, Stethoscope } from "lucide-react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Link } from "react-router-dom";
import { ErrorState, SectionTitle, Skeleton, Stat } from "../components/ui";
import { api } from "../lib/api";
import { CLASS_COLOR, CLASS_LABEL, fmtDate } from "../lib/format";

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function Meter({ label, value, total, note }: { label: string; value: number; total: number; note?: string }) {
  const pct = total ? Math.round((100 * value) / total) : 0;
  return (
    <div>
      <div className="flex justify-between text-[13px]"><span className="text-ink">{label}</span><span className="font-semibold tabular text-ink">{value}/{total} · {pct}%</span></div>
      <div className="mt-1.5 h-2 rounded-full bg-brand-100"><div className="h-2 rounded-full bg-brand-500" style={{ width: `${pct}%` }} /></div>
      {note && <p className="mt-1 text-[11.5px] text-ink-3">{note}</p>}
    </div>
  );
}

export default function OperationsPage() {
  const q = useQuery({ queryKey: ["operations"], queryFn: api.operations });
  if (q.isLoading) return <div className="space-y-4 p-8"><Skeleton className="h-24" /><Skeleton className="h-72" /></div>;
  if (q.isError) return <div className="p-8"><ErrorState error={q.error} retry={() => q.refetch()} /></div>;
  const o = q.data;
  const classes = ["AMB", "EMER", "IMP", "VR"].filter((c) => o.encounters.by_class[c]);
  const months = o.encounters.by_month.map((m: any) => ({ ...m, label: MONTHS[+m.month.slice(5, 7) - 1] }));
  const passed = o.quality.filter((c: any) => c.status === "pass").length;
  const docTotal = o.documentation.text_layer + o.documentation.scanned;
  const responses: number[] = o.communications.first_response_minutes;
  const buckets = [["< 2 h", 0, 120], ["2–6 h", 120, 360], ["6–24 h", 360, 1440], ["1–3 d", 1440, 4320], ["> 3 d", 4320, Infinity]].map(([l, a, b]) => ({ label: l, n: responses.filter((m) => m >= (a as number) && m < (b as number)).length }));
  const [d1, d2] = o.documentation.admissions_with_discharge_summary.split("/").map(Number);

  return (
    <main id="main" className="min-h-0 flex-1 overflow-y-auto scroll-thin">
      <div className="mx-auto max-w-[1280px] space-y-8 px-8 py-7">
        <div>
          <p className="eyebrow text-brand-700">Operational intelligence</p>
          <h1 className="mt-1 text-2xl font-semibold tracking-tight text-ink">Integration, documentation and communication health</h1>
          <p className="mt-1 max-w-3xl text-[13.5px] text-ink-2">
            Records as of {fmtDate(o.as_of)}. These metrics describe a 10-patient synthetic dataset and illustrate how the platform measures coverage and
            follow-through across source systems — they are not hospital performance figures.
          </p>
        </div>

        <div className="grid grid-cols-2 gap-3 lg:grid-cols-3 xl:grid-cols-6">
          <Stat icon={Stethoscope} label="Encounters" value={o.totals.encounters} sub={`${o.encounters.by_class.IMP ?? 0} inpatient · ${o.encounters.by_class.EMER ?? 0} ED`} />
          <Stat icon={FileStack} label="Clinical PDFs" value={o.totals.documents} sub={`${o.totals.pages} pages · ${o.documentation.scanned} scanned`} />
          <Stat icon={Inbox} label="Awaiting reply" value={o.communications.by_status.awaiting_reply ?? 0} sub={`${o.communications.by_status.routed ?? 0} routed · pending`} />
          <Stat icon={MessagesSquare} label="Median first response" value={o.communications.median_first_response_hours !== null ? `${o.communications.median_first_response_hours} h` : "—"} sub="Threads with a reply" />
          <Stat icon={ScanLine} label="Imaging studies" value={o.imaging.studies} sub={`${o.imaging.with_report} with linked report`} />
          <Stat icon={ShieldCheck} label="Integrity checks" value={`${passed}/${o.quality.length}`} sub="Passing at last ingestion" />
        </div>

        <div className="grid gap-6 lg:grid-cols-2">
          <section className="card p-5">
            <SectionTitle icon={Activity} title="Encounter activity by month" hint="Count of encounters starting in each month, by care class" />
            <div className="mb-2 flex flex-wrap gap-3 text-[12px] text-ink-2">
              {classes.map((c) => <span key={c} className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm" style={{ background: CLASS_COLOR[c] }} />{CLASS_LABEL[c]} ({o.encounters.by_class[c]})</span>)}
            </div>
            <div className="h-56">
              <ResponsiveContainer>
                <BarChart data={months} margin={{ left: -20, right: 8, top: 8 }} barCategoryGap="30%">
                  <CartesianGrid vertical={false} />
                  <XAxis dataKey="label" tickLine={false} axisLine={{ stroke: "#cfd6e0" }} />
                  <YAxis allowDecimals={false} tickLine={false} axisLine={false} />
                  <Tooltip cursor={{ fill: "#f0f3f7" }} contentStyle={{ borderRadius: 8, borderColor: "#e3e8ef", fontSize: 12 }} />
                  {classes.map((c, i) => (
                    <Bar key={c} dataKey={c} name={CLASS_LABEL[c]} stackId="a" fill={CLASS_COLOR[c]} stroke="#fff" strokeWidth={2} maxBarSize={24}
                      radius={i === classes.length - 1 ? [4, 4, 0, 0] : [0, 0, 0, 0]} isAnimationActive={false} />
                  ))}
                </BarChart>
              </ResponsiveContainer>
            </div>
            <p className="mt-2 text-[12px] text-ink-3">Inpatient length of stay (days): {o.encounters.inpatient_los_days.join(", ") || "—"}</p>
          </section>

          <section className="card p-5">
            <SectionTitle icon={FileStack} title="Documentation coverage" hint="Is the narrative record complete enough to review?" />
            <div className="space-y-4">
              <Meter label="Encounters with a signed note" value={Math.round((o.documentation.encounters_with_note_pct * o.totals.encounters) / 100)} total={o.totals.encounters} />
              <Meter label="Admissions with a discharge summary PDF" value={d1} total={d2} />
              <Meter label="PDFs with an extractable text layer" value={o.documentation.text_layer} total={docTotal} note={`${o.documentation.scanned} scanned faxes are viewable but not searchable (OCR not performed).`} />
              <Meter label="PDFs with page-level identity verified" value={o.documentation.verified} total={docTotal} note="Every page's printed patient and encounter identifiers match the document index." />
            </div>
            {o.documentation.quarantine.length > 0 && (
              <div className="mt-4 rounded-lg border border-attn-600/25 bg-attn-50 p-3 text-[12.5px] text-attn-700">
                <div className="flex items-center gap-1.5 font-semibold"><ShieldAlert className="h-4 w-4" />{o.documentation.quarantined} document quarantined at ingestion</div>
                {o.documentation.quarantine.map((x: any) => <p key={x.document_id} className="mt-1">{x.document_id}: {x.reason}. Excluded from every patient view and from retrieval.</p>)}
              </div>
            )}
          </section>

          <section className="card p-5">
            <SectionTitle icon={MessagesSquare} title="Portal communication" hint="Time from a patient's first message to the first care-team response" />
            <div className="h-44">
              <ResponsiveContainer>
                <BarChart data={buckets} margin={{ left: -20, right: 8, top: 8 }}>
                  <CartesianGrid vertical={false} />
                  <XAxis dataKey="label" tickLine={false} axisLine={{ stroke: "#cfd6e0" }} />
                  <YAxis allowDecimals={false} tickLine={false} axisLine={false} />
                  <Tooltip cursor={{ fill: "#f0f3f7" }} formatter={(v) => [`${v} threads`, "Threads"]} contentStyle={{ borderRadius: 8, borderColor: "#e3e8ef", fontSize: 12 }} />
                  <Bar dataKey="n" fill="#2a78d6" maxBarSize={24} radius={[4, 4, 0, 0]} isAnimationActive={false} />
                </BarChart>
              </ResponsiveContainer>
            </div>
            <div className="mt-3 flex flex-wrap gap-2 text-[12px]">
              {Object.entries(o.communications.by_category).map(([k, v]) => <span key={k} className="chip border-line bg-sunken text-ink-2">{k} · {v as number}</span>)}
            </div>
          </section>

          <section className="card p-5">
            <SectionTitle icon={Inbox} title="Open patient requests" hint="Threads whose latest message is from the patient with no recorded reply" />
            <table className="w-full text-[13px]">
              <thead><tr className="border-b border-line text-left text-[11.5px] uppercase tracking-wide text-ink-3"><th className="py-1.5 font-semibold">Patient</th><th className="py-1.5 font-semibold">Subject</th><th className="py-1.5 text-right font-semibold">Waiting</th></tr></thead>
              <tbody>
                {o.communications.awaiting.map((a: any) => (
                  <tr key={a.thread_id} className="border-b border-line last:border-0">
                    <td className="py-2"><Link className="font-medium text-brand-700 hover:underline" to={`/patients/${a.patient_id}/communications`}>{a.patient_id}</Link></td>
                    <td className="py-2 text-ink-2">{a.subject} <span className="text-ink-3">· {a.category}</span></td>
                    <td className="py-2 text-right tabular text-ink">{a.waiting_days <= 0 ? "< 1 day" : `${a.waiting_days} d`}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        </div>

        <section className="card p-5">
          <SectionTitle icon={ShieldCheck} title="Data quality and integration checks" hint={`Run by the ingestion pipeline (${o.manifest.pipeline_version}) on ${fmtDate(o.manifest.processed_at)} against dataset ${o.manifest.dataset_version}`} />
          <div className="overflow-x-auto">
            <table className="w-full min-w-[760px] text-[13px]">
              <thead><tr className="border-b border-line text-left text-[11.5px] uppercase tracking-wide text-ink-3">
                <th className="py-2 font-semibold">Check</th><th className="py-2 font-semibold">Category</th><th className="py-2 font-semibold">What it verifies</th><th className="py-2 text-right font-semibold">Checked</th><th className="py-2 text-right font-semibold">Result</th>
              </tr></thead>
              <tbody>
                {o.quality.map((c: any) => (
                  <tr key={c.check_id} className="border-b border-line align-top last:border-0">
                    <td className="py-2 pr-3"><span className="text-ink-3">{c.check_id}</span> <span className="font-medium text-ink">{c.check_name}</span></td>
                    <td className="py-2 pr-3 text-ink-2">{c.category}</td>
                    <td className="py-2 pr-3 text-ink-2">{c.description}{c.detail ? <span className="block text-[12px] text-ink-3">{c.detail}</span> : null}</td>
                    <td className="py-2 text-right tabular text-ink-2">{c.checked_count}</td>
                    <td className="py-2 text-right">{c.status === "pass" ? <span className="chip border-evidence-600/20 bg-evidence-50 text-evidence-700"><BadgeCheck className="h-3 w-3" />Pass</span>
                      : <span className="chip border-crit-600/20 bg-crit-50 text-crit-600"><ShieldAlert className="h-3 w-3" />Fail · {c.failing_count}</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <section className="grid gap-6 lg:grid-cols-2">
          <div className="card p-5">
            <SectionTitle icon={ScanLine} title="Imaging integration" hint="DICOM objects linked to orders, encounters and reports" />
            <div className="space-y-4">
              <Meter label="Studies with a linked report" value={o.imaging.with_report} total={o.imaging.studies} />
              <Meter label="DICOM header matches catalog (patient, accession, SYN)" value={o.imaging.header_verified} total={o.imaging.studies} />
            </div>
            <ul className="mt-4 space-y-1 text-[12.5px] text-ink-2">{Object.entries(o.imaging.by_procedure).map(([k, v]) => <li key={k} className="flex justify-between"><span>{k}</span><span className="tabular">{v as number}</span></li>)}</ul>
          </div>
          <div className="card p-5">
            <SectionTitle title="Retrieval index" hint="Patient-scoped evidence chunks available to the assistant" />
            <ul className="space-y-2 text-[13px]">
              {Object.entries(o.retrieval.by_source).map(([k, v]) => (
                <li key={k} className="flex items-center justify-between"><span className="text-ink-2">{k.replace("_", " ")}</span><span className="font-semibold tabular text-ink">{v as number}</span></li>
              ))}
            </ul>
            <p className="mt-3 text-[12px] text-ink-3">Embeddings: {o.manifest.embedding_model} (1024-d), stored per chunk in Unity Catalog and compared in-app; no Vector Search endpoint is provisioned.</p>
          </div>
        </section>
      </div>
    </main>
  );
}
