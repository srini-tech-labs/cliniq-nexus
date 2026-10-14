import { useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import { CalendarX2, History, MessageSquareWarning, Search } from "lucide-react";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import { fmtDate, sexShort } from "../lib/format";
import type { WorklistRow } from "../lib/types";
import { ClassBadge, ErrorState, Skeleton } from "./ui";

const FILTERS = [
  { id: "all", label: "All", test: () => true },
  { id: "acute", label: "Hospital care · 120 days", test: (r: WorklistRow) => !!r.recent_acute_at },
  { id: "messages", label: "Awaiting reply", test: (r: WorklistRow) => r.awaiting_reply > 0 },
  { id: "overdue", label: "Overdue follow-up", test: (r: WorklistRow) => r.overdue_follow_ups > 0 },
] as const;

export default function Worklist({ activeId }: { activeId?: string }) {
  const q = useQuery({ queryKey: ["worklist"], queryFn: api.worklist });
  const [term, setTerm] = useState("");
  const [filter, setFilter] = useState<(typeof FILTERS)[number]["id"]>("all");
  const rows = useMemo(() => {
    const f = FILTERS.find((x) => x.id === filter)!;
    const t = term.trim().toLowerCase();
    return (q.data ?? []).filter((r) => f.test(r) && (!t || `${r.display_name} ${r.patient_id} ${r.mrn} ${r.care_program}`.toLowerCase().includes(t)));
  }, [q.data, term, filter]);

  return (
    <aside aria-label="Patient worklist" className="flex h-full w-full flex-col border-r border-line bg-surface">
      <div className="border-b border-line p-3">
        <div className="mb-2 flex items-baseline justify-between">
          <h2 className="text-sm font-semibold text-ink">Review worklist</h2>
          <span className="text-xs text-ink-3">{q.data ? `${rows.length} of ${q.data.length}` : ""}</span>
        </div>
        <label className="relative block">
          <span className="sr-only">Search patients</span>
          <Search className="pointer-events-none absolute left-2.5 top-2.5 h-4 w-4 text-ink-3" aria-hidden />
          <input
            value={term} onChange={(e) => setTerm(e.target.value)} placeholder="Search name, MRN or program"
            className="w-full rounded-lg border border-line bg-sunken py-2 pl-8 pr-3 text-sm placeholder:text-ink-3 focus:border-brand-500 focus:bg-surface focus:outline-none"
          />
        </label>
        <div className="mt-2 flex flex-wrap gap-1.5" role="group" aria-label="Filter worklist">
          {FILTERS.map((f) => (
            <button key={f.id} onClick={() => setFilter(f.id)} aria-pressed={filter === f.id}
              className={clsx("chip transition-colors", filter === f.id ? "border-brand-500/30 bg-brand-50 text-brand-700" : "border-line bg-surface text-ink-2 hover:bg-sunken")}>
              {f.label}
            </button>
          ))}
        </div>
      </div>
      <div className="scroll-thin flex-1 overflow-y-auto p-2">
        {q.isLoading && Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="mb-2 h-[86px]" />)}
        {q.isError && <ErrorState error={q.error} retry={() => q.refetch()} />}
        <ul className="space-y-1.5">
          {rows.map((r) => (
            <li key={r.patient_id}>
              <Link to={`/patients/${r.patient_id}`} aria-current={activeId === r.patient_id ? "page" : undefined}
                className={clsx("block rounded-xl border px-3 py-2.5 transition-colors",
                  activeId === r.patient_id ? "border-brand-500/40 bg-brand-50/70 shadow-card" : "border-transparent hover:border-line hover:bg-sunken/70")}>
                <div className="flex items-center justify-between gap-2">
                  <span className="truncate text-[13.5px] font-semibold text-ink">{r.display_name}</span>
                  <span className="shrink-0 text-xs text-ink-3">{sexShort(r.sex)} · {r.age_years}</span>
                </div>
                <div className="mt-0.5 truncate text-[12.5px] text-ink-2">{r.care_program}</div>
                <div className="mt-1.5 flex flex-wrap items-center gap-1.5 text-[11.5px] text-ink-3">
                  {r.last_encounter_class && <ClassBadge code={r.last_encounter_class} compact />}
                  <span>Last encounter {fmtDate(r.last_encounter_at, false)}</span>
                  {r.awaiting_reply > 0 && (
                    <span className="chip border-attn-600/25 bg-attn-50 text-attn-700" title="Portal messages awaiting reply">
                      <MessageSquareWarning className="h-3 w-3" aria-hidden />{r.awaiting_reply}
                    </span>
                  )}
                  {r.overdue_follow_ups > 0 && (
                    <span className="chip border-attn-600/25 bg-attn-50 text-attn-700" title="Follow-up items past due">
                      <CalendarX2 className="h-3 w-3" aria-hidden />{r.overdue_follow_ups}
                    </span>
                  )}
                  {r.recent_acute_at && (
                    <span className="chip border-line bg-sunken text-ink-2"
                      title={`Historical utilization: ${r.recent_acute_class === "IMP" ? "inpatient stay" : "emergency department visit"} ending ${fmtDate(r.recent_acute_at)}. Not a current location — no encounter is in progress.`}>
                      <History className="h-3 w-3" aria-hidden />{r.recent_acute_class === "IMP" ? "Prior inpatient stay" : "Prior ED visit"} · {fmtDate(r.recent_acute_at, false)}
                    </span>
                  )}
                </div>
              </Link>
            </li>
          ))}
        </ul>
        {q.data && rows.length === 0 && <p className="p-4 text-center text-sm text-ink-3">No patients match this filter.</p>}
      </div>
    </aside>
  );
}
