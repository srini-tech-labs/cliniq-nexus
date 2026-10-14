import { useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import { Database, ShieldCheck } from "lucide-react";
import { NavLink, useLocation } from "react-router-dom";
import { api } from "../lib/api";
import { fmtDate } from "../lib/format";

function Logo() {
  return (
    <div className="flex items-center gap-2.5">
      <svg viewBox="0 0 32 32" className="h-8 w-8" aria-hidden>
        <rect width="32" height="32" rx="9" fill="#184f95" />
        <path d="M8 16.5h4.2l2.3-5.5 3.2 11 2.3-5.5H24" fill="none" stroke="#fff" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
      <div className="leading-tight">
        <div className="text-[15px] font-semibold tracking-tight text-ink">ClinIQ Nexus</div>
        <div className="hidden text-[11px] text-ink-3 xl:block">Clinical intelligence workspace</div>
      </div>
    </div>
  );
}

export default function TopBar() {
  const meta = useQuery({ queryKey: ["meta"], queryFn: api.meta });
  const location = useLocation();
  const link = ({ isActive }: { isActive: boolean }) =>
    clsx("rounded-lg px-3 py-1.5 text-sm font-medium transition-colors", isActive ? "bg-brand-50 text-brand-700" : "text-ink-2 hover:bg-sunken");
  const ds = meta.data?.dataset;
  return (
    <header className="z-20 flex h-14 shrink-0 items-center gap-6 border-b border-line bg-surface px-4 lg:px-5">
      <Logo />
      <nav aria-label="Primary" className="flex items-center gap-1 whitespace-nowrap">
        <NavLink to="/" end className={({ isActive }) => link({ isActive: isActive || location.pathname.startsWith("/patients") })}>Clinical workspace</NavLink>
        <NavLink to="/operations" className={link}>Operations</NavLink>
        <NavLink to="/about" className={link}>How it works</NavLink>
      </nav>
      <div className="ml-auto hidden items-center gap-2 md:flex">
        {ds && (
          <span className="chip hidden border-line bg-sunken text-ink-2 xl:inline-flex" title={`Dataset ${ds.dataset_version} · pipeline ${ds.pipeline_version} · processed ${fmtDate(ds.processed_at)}`}>
            <Database className="h-3 w-3" aria-hidden />
            {meta.data?.source.mode === "warehouse" ? "Unity Catalog" : "Local snapshot"} · records as of {fmtDate(ds.as_of)}
          </span>
        )}
        <span className="chip border-synth-600/25 bg-synth-50 text-synth-600" title="Every record in this application is synthetic. Not for clinical use.">
          <ShieldCheck className="h-3 w-3" aria-hidden /> Synthetic data<span className="hidden xl:inline"> · not for clinical use</span>
        </span>
      </div>
    </header>
  );
}
