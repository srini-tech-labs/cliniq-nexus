import clsx from "clsx";
import { Clock, MessageSquare, Route, Sparkles } from "lucide-react";
import { useState } from "react";
import { EmptyState, StatusChip } from "../components/ui";
import { useWorkspace } from "../lib/context";
import { daysBetween, fmtDate, fmtDateTime } from "../lib/format";
import type { Bundle } from "../lib/types";

function waited(minutes: number | null) {
  if (minutes === null) return "—";
  return minutes < 60 ? `${minutes} min` : minutes < 1440 ? `${(minutes / 60).toFixed(1)} h` : `${(minutes / 1440).toFixed(1)} d`;
}

export default function CommsTab({ bundle }: { bundle: Bundle }) {
  const { askAssistant } = useWorkspace();
  const order = { awaiting_reply: 0, routed: 1, answered: 2 } as const;
  const threads = [...bundle.threads].sort((a, b) => order[a.status] - order[b.status] || b.last_message_at.localeCompare(a.last_message_at));
  const [sel, setSel] = useState(threads[0]?.thread_id);
  const t = threads.find((x) => x.thread_id === sel) ?? threads[0];
  if (!threads.length) return <EmptyState icon={MessageSquare} title="No portal messages are documented for this patient." />;
  const count = (s: string) => threads.filter((x) => x.status === s).length;
  return (
    <div className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-3">
        {[
          { s: "awaiting_reply", label: "Awaiting reply", hint: "Last message is from the patient; no reply recorded", cls: "text-attn-700" },
          { s: "routed", label: "Routed · pending", hint: "Acknowledged and routed; no completion recorded", cls: "text-brand-700" },
          { s: "answered", label: "Answered", hint: "Substantive care-team or clinician reply recorded", cls: "text-evidence-700" },
        ].map((x) => (
          <div key={x.s} className="card px-4 py-3">
            <div className={clsx("text-2xl font-semibold", x.cls)}>{count(x.s)}</div>
            <div className="text-[13px] font-medium text-ink">{x.label}</div>
            <div className="text-[11.5px] text-ink-3">{x.hint}</div>
          </div>
        ))}
      </div>
      <div className="grid gap-4 lg:grid-cols-[320px_minmax(0,1fr)]">
        <ul className="card divide-y divide-line overflow-hidden" aria-label="Portal threads">
          {threads.map((x) => {
            const age = daysBetween(x.last_message_at, bundle.as_of);
            return (
              <li key={x.thread_id}>
                <button onClick={() => setSel(x.thread_id)} aria-current={x.thread_id === t.thread_id}
                  className={clsx("w-full px-4 py-3 text-left", x.thread_id === t.thread_id ? "bg-brand-50/70" : "hover:bg-sunken/60")}>
                  <div className="flex items-center justify-between gap-2"><span className="truncate text-[13.5px] font-medium text-ink">{x.subject}</span><StatusChip status={x.status} /></div>
                  <div className="mt-0.5 text-[12px] text-ink-3">{x.category} · {x.message_count} message{x.message_count === 1 ? "" : "s"} · last {fmtDate(x.last_message_at, false)}</div>
                  {x.status !== "answered" && <div className="mt-1 flex items-center gap-1 text-[12px] text-attn-700"><Clock className="h-3 w-3" />waiting {age <= 0 ? "since today" : `${age} day${age > 1 ? "s" : ""}`}</div>}
                </button>
              </li>
            );
          })}
        </ul>
        <article className="card flex flex-col">
          <header className="flex flex-wrap items-start justify-between gap-3 border-b border-line px-5 py-3">
            <div>
              <h3 className="text-[15px] font-semibold text-ink">{t.subject}</h3>
              <p className="mt-0.5 flex flex-wrap items-center gap-x-3 text-[12px] text-ink-3">
                <span>{t.category}</span><span>Opened {fmtDateTime(t.opened_at)}</span>
                <span>First response {waited(t.first_response_minutes)}</span>
                {t.routed_to && <span className="flex items-center gap-1"><Route className="h-3 w-3" />{t.routed_to}</span>}
              </p>
            </div>
            <button className="chip border-brand-500/25 bg-brand-50 text-brand-700 hover:bg-brand-100"
              onClick={() => askAssistant(`What is documented about the portal thread "${t.subject}"?`)}>
              <Sparkles className="h-3 w-3" />Ask about this thread
            </button>
          </header>
          <ol className="flex-1 space-y-3 p-5">
            {t.messages.map((m) => (
              <li key={m.message_id} className={clsx("max-w-[80%]", m.sender_role !== "patient" && "ml-auto")}>
                <div className={clsx("rounded-2xl px-4 py-2.5 text-[13.5px] leading-relaxed", m.sender_role === "patient" ? "rounded-tl-sm border border-line bg-surface text-ink" : "rounded-tr-sm bg-brand-600 text-white")}>
                  {m.message_body}
                </div>
                <div className={clsx("mt-1 text-[11.5px] text-ink-3", m.sender_role !== "patient" && "text-right")}>
                  {m.sender_name}{m.is_routing_acknowledgment && " · routing acknowledgment"} · {fmtDateTime(m.sent_at)}
                </div>
              </li>
            ))}
          </ol>
          {t.status !== "answered" && (
            <footer className="border-t border-dashed border-attn-600/30 bg-attn-50/60 px-5 py-2.5 text-[12.5px] text-attn-700">
              {t.status === "awaiting_reply" ? "No care-team reply is recorded for the latest patient message." : `Routed to ${t.routed_to}; no completion is recorded.`}
              {" "}ClinIQ Nexus displays communication status only and does not send messages.
            </footer>
          )}
        </article>
      </div>
    </div>
  );
}
