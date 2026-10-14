import { useMutation, useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import {
  ArrowUp, BadgeCheck, ChevronDown, CircleSlash, Database, FileSearch, Info, Loader2, ShieldAlert, Sparkles, X,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { api } from "../lib/api";
import { useWorkspace, type EvidenceTarget } from "../lib/context";
import { fmtDate, SOURCE_LABEL } from "../lib/format";
import type { Answer, Bundle, Source } from "../lib/types";
import { SourceIcon } from "./ui";

interface Turn { id: string; question: string; answer?: Answer; error?: string }

export function sourceTarget(s: Source, patientId: string): EvidenceTarget {
  const base = { label: s.label, date: s.date ?? undefined, highlight: s.excerpt, patientId };
  switch (s.type) {
    case "clinical_note": return { ...base, type: "note", id: s.id };
    case "pdf_document": case "document": return { ...base, type: "document", id: s.document_id || s.id, page: s.page ?? 1 };
    case "portal_message": return { ...base, type: "message", id: s.id };
    default: return { ...base, type: s.type, id: s.id };
  }
}

const MODE: Record<string, { label: string; icon: typeof Sparkles; cls: string }> = {
  structured: { label: "From structured records", icon: Database, cls: "border-evidence-600/25 bg-evidence-50 text-evidence-700" },
  generated: { label: "AI summary", icon: Sparkles, cls: "border-brand-500/25 bg-brand-50 text-brand-700" },
  evidence_only: { label: "Evidence only", icon: FileSearch, cls: "border-attn-600/25 bg-attn-50 text-attn-700" },
  policy: { label: "Scope & safety policy", icon: ShieldAlert, cls: "border-synth-600/25 bg-synth-50 text-synth-600" },
  no_evidence: { label: "No matching evidence", icon: CircleSlash, cls: "border-line bg-sunken text-ink-2" },
};
const STEPS = ["Retrieving patient-scoped evidence", "Generating a cited answer", "Validating claims against sources"];

function Pending() {
  const [step, setStep] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setStep((s) => Math.min(s + 1, STEPS.length - 1)), 2600);
    return () => clearInterval(t);
  }, []);
  return (
    <div className="card p-4" role="status" aria-live="polite">
      {STEPS.map((s, i) => (
        <div key={s} className={clsx("flex items-center gap-2 py-1 text-[13px]", i <= step ? "text-ink-2" : "text-ink-3/60")}>
          {i < step ? <BadgeCheck className="h-4 w-4 text-evidence-600" /> : i === step ? <Loader2 className="h-4 w-4 animate-spin text-brand-600" /> : <span className="h-4 w-4 rounded-full border border-line" />}
          {s}
        </div>
      ))}
    </div>
  );
}

function AnswerCard({ a, patientId }: { a: Answer; patientId: string }) {
  const { openEvidence } = useWorkspace();
  const [details, setDetails] = useState(false);
  const mode = MODE[a.mode] ?? MODE.no_evidence;
  const idx = Object.fromEntries(a.sources.map((s, i) => [s.sid, i + 1]));
  const passed = a.validation.checks.filter((c) => c.passed).length;
  const open = (s: Source) => openEvidence(sourceTarget(s, patientId));
  const searched = a.retrieval.searched
    ? Object.entries(a.retrieval.searched).map(([k, v]) => `${v} ${(SOURCE_LABEL[k] ?? k).toLowerCase()}${v === 1 ? "" : "s"}`).join(" · ")
    : null;
  return (
    <div className="card overflow-hidden">
      <div className="flex items-center justify-between gap-2 border-b border-line bg-sunken/50 px-4 py-2">
        <span className={clsx("chip", mode.cls)}><mode.icon className="h-3 w-3" aria-hidden />{mode.label}
          {a.mode === "generated" && a.validation.level === "verified" && " · verified"}</span>
        <span className="text-[11.5px] text-ink-3 tabular">{(a.latency_ms / 1000).toFixed(1)} s</span>
      </div>
      <div className="space-y-3 p-4">
        {a.notice && (
          <div className="flex gap-2 rounded-lg border border-line bg-sunken/70 p-2.5 text-[12.5px] leading-relaxed text-ink-2">
            <Info className="mt-0.5 h-3.5 w-3.5 shrink-0 text-ink-3" aria-hidden />{a.notice}
          </div>
        )}
        {a.claims.length > 0 && (
          <ul className="space-y-2.5">
            {a.claims.map((c, i) => c.kind === "documented" ? (
              <li key={i} className="flex gap-2.5 text-[13.5px] leading-relaxed text-ink">
                <span className="mt-[7px] h-1.5 w-1.5 shrink-0 rounded-full bg-evidence-600" aria-hidden />
                <span>
                  {c.text}{" "}
                  {c.citations.map((sid) => {
                    const s = a.sources.find((x) => x.sid === sid);
                    return s ? (
                      <button key={sid} onClick={() => open(s)} title={`Open source: ${s.label}`}
                        className="mx-0.5 inline-flex h-[18px] min-w-[18px] items-center justify-center rounded-md border border-brand-500/30 bg-brand-50 px-1 align-[1px] text-[10.5px] font-semibold text-brand-700 hover:bg-brand-100">
                        {idx[sid]}
                      </button>
                    ) : null;
                  })}
                </span>
              </li>
            ) : (
              <li key={i} className="flex gap-2.5 rounded-lg border border-dashed border-lineStrong px-3 py-2 text-[13px] text-ink-2">
                <CircleSlash className="mt-0.5 h-3.5 w-3.5 shrink-0 text-ink-3" aria-hidden />
                <span><span className="font-semibold text-ink-2">Not documented · </span>{c.text}</span>
              </li>
            ))}
          </ul>
        )}
        {a.sources.length > 0 && (
          <div>
            <div className="eyebrow mb-1.5">{a.mode === "evidence_only" || a.mode === "policy" ? "Relevant documentation" : "Sources"}</div>
            <ol className="space-y-1">
              {a.sources.map((s, i) => (
                <li key={s.sid}>
                  <button onClick={() => open(s)} className="group flex w-full items-start gap-2 rounded-lg px-2 py-1.5 text-left hover:bg-sunken">
                    <span className="mt-px w-4 shrink-0 text-right text-[11px] font-semibold text-ink-3 tabular">{i + 1}</span>
                    <SourceIcon type={s.type} className="mt-0.5 text-ink-3 group-hover:text-brand-600" />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-[12.5px] font-medium text-ink group-hover:text-brand-700">{s.label}</span>
                      {(a.mode === "evidence_only" || a.mode === "policy") && (
                        <span className="line-clamp-2 text-[12px] text-ink-3">{s.excerpt.split("\n").slice(1).join(" ") || s.excerpt}</span>
                      )}
                    </span>
                  </button>
                </li>
              ))}
            </ol>
          </div>
        )}
      </div>
      <button onClick={() => setDetails(!details)} aria-expanded={details}
        className="flex w-full items-center justify-between border-t border-line px-4 py-2 text-[12px] text-ink-3 hover:bg-sunken/60">
        <span className="flex items-center gap-1.5">
          {a.validation.passed ? <BadgeCheck className="h-3.5 w-3.5 text-evidence-600" /> : <ShieldAlert className="h-3.5 w-3.5 text-attn-600" />}
          {a.mode === "structured" ? "Deterministic · built from records" : a.validation.checks.length ? `${passed}/${a.validation.checks.length} validation checks passed` : "How this answer was produced"}
        </span>
        <ChevronDown className={clsx("h-3.5 w-3.5 transition-transform", details && "rotate-180")} />
      </button>
      {details && (
        <div className="space-y-2 border-t border-line bg-sunken/40 px-4 py-3 text-[12px] text-ink-2">
          {a.retrieval.mode && a.retrieval.mode !== "structured" && (
            <p><span className="font-medium text-ink">Retrieval:</span> {a.retrieval.mode === "hybrid" ? `hybrid lexical (BM25) + embedding rerank (${a.retrieval.embedding_model})` : "lexical (BM25)"} over this patient only{searched ? ` — ${searched}` : ""}.</p>
          )}
          {a.retrieval.not_searchable && a.retrieval.not_searchable.length > 0 && (
            <p><span className="font-medium text-ink">Not searchable:</span> {a.retrieval.not_searchable.join("; ")}.</p>
          )}
          {a.model && <p><span className="font-medium text-ink">Model:</span> {a.model}</p>}
          <ul className="space-y-1">
            {a.validation.checks.map((c) => (
              <li key={c.name} className="flex gap-1.5">
                {c.passed ? <BadgeCheck className="mt-px h-3.5 w-3.5 shrink-0 text-evidence-600" /> : <ShieldAlert className="mt-px h-3.5 w-3.5 shrink-0 text-attn-600" />}
                <span><span className="font-medium">{c.name.replace(/_/g, " ")}</span>{c.detail ? ` — ${c.detail}` : ""}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

export default function AssistantPanel({ bundle, onClose }: { bundle: Bundle; onClose: () => void }) {
  const pid = bundle.patient.patient_id;
  const { consumeQuestion, pendingQuestion } = useWorkspace();
  const [turns, setTurns] = useState<Turn[]>([]);
  const [text, setText] = useState("");
  const [cleared, setCleared] = useState(false);
  const scroller = useRef<HTMLDivElement>(null);
  const prevPid = useRef(pid);
  const suggestions = useQuery({ queryKey: ["suggestions", pid], queryFn: () => api.suggestions(pid) });

  const ask = useMutation({
    mutationFn: ({ q }: { q: string; id: string }) => api.ask(pid, q),
    onSuccess: (answer, { id }) => setTurns((ts) => ts.map((t) => (t.id === id ? { ...t, answer } : t))),
    onError: (e, { id }) => setTurns((ts) => ts.map((t) => (t.id === id ? { ...t, error: (e as Error).message } : t))),
  });

  useEffect(() => {
    if (prevPid.current !== pid) {
      setCleared(turns.length > 0);
      setTurns([]);
      prevPid.current = pid;
    }
  }, [pid]); // eslint-disable-line react-hooks/exhaustive-deps

  const submit = (q: string) => {
    const question = q.trim();
    if (question.length < 3 || ask.isPending) return;
    const id = Math.random().toString(36).slice(2);
    setTurns((ts) => [...ts, { id, question }]);
    setText("");
    setCleared(false);
    ask.mutate({ q: question, id });
  };

  useEffect(() => {
    if (pendingQuestion) { const q = consumeQuestion(); if (q) submit(q); }
  }, [pendingQuestion]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => { scroller.current?.scrollTo({ top: scroller.current.scrollHeight, behavior: "smooth" }); }, [turns]);

  return (
    <section aria-label="Ask the record assistant" className="flex h-full min-h-0 flex-col border-l border-line bg-[#f8fafc]">
      <div className="flex items-start justify-between gap-2 border-b border-line bg-surface px-4 py-3">
        <div>
          <h2 className="flex items-center gap-1.5 text-[15px] font-semibold text-ink"><Sparkles className="h-4 w-4 text-brand-600" aria-hidden />Ask the record</h2>
          <p className="mt-0.5 text-[12px] text-ink-3">Scoped to {bundle.patient.display_name} · every statement links to its source</p>
        </div>
        <button className="btn-ghost -mr-1 px-2" onClick={onClose} aria-label="Close assistant"><X className="h-4 w-4" /></button>
      </div>
      <div ref={scroller} className="scroll-thin flex-1 space-y-4 overflow-y-auto p-4" aria-live="polite">
        {cleared && <p className="rounded-lg bg-sunken px-3 py-2 text-[12px] text-ink-3">Patient changed — the previous conversation was cleared so no context carries across patients.</p>}
        {turns.length === 0 && (
          <div>
            <p className="mb-3 text-[13px] leading-relaxed text-ink-2">
              Ask about this patient's documented care. Structured questions are answered directly from records; narrative questions use
              grounded generation that is checked against the cited sources before it is shown.
            </p>
            <div className="eyebrow mb-2">Suggested for this patient</div>
            <div className="space-y-1.5">
              {(suggestions.data ?? []).map((s) => (
                <button key={s.q} onClick={() => submit(s.q)}
                  className="flex w-full items-center justify-between gap-2 rounded-lg border border-line bg-surface px-3 py-2 text-left text-[13px] text-ink hover:border-brand-500/40 hover:bg-brand-50/40">
                  <span>{s.q}</span>
                  {s.kind === "structured" ? <Database className="h-3.5 w-3.5 shrink-0 text-ink-3" aria-label="Answered from structured records" />
                    : <Sparkles className="h-3.5 w-3.5 shrink-0 text-ink-3" aria-label="Grounded AI answer" />}
                </button>
              ))}
            </div>
          </div>
        )}
        {turns.map((t) => (
          <div key={t.id} className="space-y-2">
            <div className="ml-8 rounded-xl rounded-tr-sm bg-brand-600 px-3 py-2 text-[13.5px] text-white">{t.question}</div>
            {t.answer ? <AnswerCard a={t.answer} patientId={pid} />
              : t.error ? <div role="alert" className="rounded-lg border border-crit-600/25 bg-crit-50 p-3 text-[13px] text-ink-2">The assistant could not answer: {t.error}</div>
              : <Pending />}
          </div>
        ))}
      </div>
      <form className="border-t border-line bg-surface p-3" onSubmit={(e) => { e.preventDefault(); submit(text); }}>
        <div className="flex items-end gap-2 rounded-xl border border-line bg-surface p-1.5 focus-within:border-brand-500">
          <label htmlFor="assistant-input" className="sr-only">Question about this patient</label>
          <textarea id="assistant-input" value={text} onChange={(e) => setText(e.target.value)} rows={2} maxLength={500}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submit(text); } }}
            placeholder="e.g. What follow-up instructions are documented?" className="flex-1 resize-none bg-transparent px-2 py-1 text-[13.5px] placeholder:text-ink-3 focus:outline-none" />
          <button type="submit" className="btn-primary h-8 w-8 p-0" disabled={ask.isPending || text.trim().length < 3} aria-label="Ask">
            <ArrowUp className="h-4 w-4" />
          </button>
        </div>
        <p className="mt-1.5 text-[11px] text-ink-3">Synthetic records as of {fmtDate(bundle.as_of)}. Summaries support record review — not diagnosis or treatment decisions.</p>
      </form>
    </section>
  );
}
