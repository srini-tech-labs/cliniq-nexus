import clsx from "clsx";
import {
  Activity, AlertTriangle, Building2, CalendarClock, FileImage, FileText, FlaskConical, HeartPulse, Inbox, Info,
  Loader2, MessageSquare, Pill, ScanLine, Stethoscope, type LucideIcon,
} from "lucide-react";
import type { ReactNode } from "react";
import { CLASS_COLOR } from "../lib/format";

export const SOURCE_ICON: Record<string, LucideIcon> = {
  clinical_note: FileText, note: FileText, pdf_document: FileText, document: FileText, portal_message: MessageSquare,
  thread: MessageSquare, imaging_report: ScanLine, imaging: FileImage, encounter: Stethoscope, medication: Pill,
  observation: FlaskConical, vital: HeartPulse, follow_up: CalendarClock,
};

export function SourceIcon({ type, className }: { type: string; className?: string }) {
  const Icon = SOURCE_ICON[type] ?? FileText;
  return <Icon className={clsx("h-4 w-4 shrink-0", className)} aria-hidden />;
}

const CLASS_NAME: Record<string, string> = { IMP: "Inpatient", EMER: "Emergency", AMB: "Ambulatory", VR: "Virtual" };

export function ClassBadge({ code, compact }: { code: string; compact?: boolean }) {
  return (
    <span className="chip border-line bg-surface text-ink-2" title={CLASS_NAME[code]}>
      <span className="h-2 w-2 rounded-full" style={{ background: CLASS_COLOR[code] }} aria-hidden />{compact ? code : CLASS_NAME[code] ?? code}
    </span>
  );
}

export function StatusChip({ status }: { status: string }) {
  const map: Record<string, [string, string]> = {
    awaiting_reply: ["Awaiting reply", "bg-attn-50 text-attn-700 border-attn-600/25"],
    routed: ["Routed · pending", "bg-brand-50 text-brand-700 border-brand-500/20"],
    answered: ["Answered", "bg-evidence-50 text-evidence-700 border-evidence-600/20"],
    active: ["Active", "bg-evidence-50 text-evidence-700 border-evidence-600/20"],
    stopped: ["Stopped", "bg-sunken text-ink-2 border-line"],
    completed: ["Completed", "bg-sunken text-ink-2 border-line"],
    open: ["Open", "bg-attn-50 text-attn-700 border-attn-600/25"],
    scheduled: ["Scheduled", "bg-brand-50 text-brand-700 border-brand-500/20"],
    verified: ["Identity verified", "bg-evidence-50 text-evidence-700 border-evidence-600/20"],
    unverified_no_text_layer: ["Scanned · not searchable", "bg-attn-50 text-attn-700 border-attn-600/25"],
  };
  const [label, cls] = map[status] ?? [status, "bg-sunken text-ink-2 border-line"];
  return <span className={clsx("chip", cls)}>{label}</span>;
}

export function SyntheticBadge({ className }: { className?: string }) {
  return (
    <span className={clsx("chip border-synth-600/25 bg-synth-50 text-synth-600", className)} title="All records are synthetic demonstration data">
      <Info className="h-3 w-3" aria-hidden /> Synthetic data
    </span>
  );
}

export function Spinner({ label }: { label?: string }) {
  return (
    <div role="status" className="flex items-center gap-2 text-sm text-ink-3">
      <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> {label ?? "Loading…"}
    </div>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={clsx("animate-pulse rounded-lg bg-sunken", className)} />;
}

export function EmptyState({ icon: Icon = Inbox, title, children }: { icon?: LucideIcon; title: string; children?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center rounded-xl2 border border-dashed border-lineStrong bg-surface/60 px-6 py-10 text-center">
      <Icon className="mb-3 h-6 w-6 text-ink-3" aria-hidden />
      <p className="text-sm font-medium text-ink">{title}</p>
      {children && <div className="mt-1 max-w-md text-sm text-ink-3">{children}</div>}
    </div>
  );
}

export function ErrorState({ error, retry }: { error: unknown; retry?: () => void }) {
  const msg = error instanceof Error ? error.message : String(error);
  return (
    <div role="alert" className="flex items-start gap-3 rounded-xl2 border border-crit-600/25 bg-crit-50 p-4 text-sm">
      <AlertTriangle className="mt-0.5 h-4 w-4 text-crit-600" aria-hidden />
      <div className="flex-1">
        <p className="font-medium text-ink">This information could not be loaded.</p>
        <p className="mt-0.5 text-ink-2">{msg}. The SQL warehouse may be resuming; retrying usually succeeds within a minute.</p>
      </div>
      {retry && <button className="btn-outline" onClick={retry}>Retry</button>}
    </div>
  );
}

export function SectionTitle({ title, hint, action, icon: Icon }: { title: string; hint?: ReactNode; action?: ReactNode; icon?: LucideIcon }) {
  return (
    <div className="mb-3 flex items-end justify-between gap-3">
      <div>
        <h2 className="flex items-center gap-2 text-[15px] font-semibold text-ink">
          {Icon && <Icon className="h-4 w-4 text-ink-3" aria-hidden />} {title}
        </h2>
        {hint && <p className="mt-0.5 text-[12.5px] text-ink-3">{hint}</p>}
      </div>
      {action}
    </div>
  );
}

export function Stat({ label, value, sub, icon: Icon = Activity }: { label: string; value: ReactNode; sub?: ReactNode; icon?: LucideIcon }) {
  return (
    <div className="card p-4">
      <div className="flex items-center gap-2 text-[12.5px] text-ink-3"><Icon className="h-4 w-4" aria-hidden />{label}</div>
      <div className="mt-1.5 text-2xl font-semibold tracking-tight text-ink">{value}</div>
      {sub && <div className="mt-0.5 text-[12.5px] text-ink-3">{sub}</div>}
    </div>
  );
}

export { Building2 };
