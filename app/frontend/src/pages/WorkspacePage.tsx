import { useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import { PanelRightClose, PanelRightOpen, Sparkles } from "lucide-react";
import { useEffect } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import AssistantPanel from "../components/AssistantPanel";
import EvidenceDrawer from "../components/EvidenceDrawer";
import PatientHeader from "../components/PatientHeader";
import Worklist from "../components/Worklist";
import { ErrorState, Skeleton } from "../components/ui";
import BriefTab from "../features/BriefTab";
import CommsTab from "../features/CommsTab";
import DocumentsTab from "../features/DocumentsTab";
import ImagingTab from "../features/ImagingTab";
import JourneyTab from "../features/JourneyTab";
import MedicationsTab from "../features/MedicationsTab";
import TrendsTab from "../features/TrendsTab";
import Welcome from "../features/Welcome";
import { api } from "../lib/api";
import { useWorkspace } from "../lib/context";

export const TABS = [
  { id: "brief", label: "Brief" },
  { id: "journey", label: "Journey" },
  { id: "trends", label: "Trends" },
  { id: "medications", label: "Medications" },
  { id: "communications", label: "Communications" },
  { id: "documents", label: "Documents" },
  { id: "imaging", label: "Imaging" },
] as const;

export default function WorkspacePage() {
  const { pid, tab = "brief" } = useParams();
  const { assistantOpen, setAssistantOpen, closeEvidence } = useWorkspace();
  const navigate = useNavigate();
  const bundle = useQuery({ queryKey: ["patient", pid], queryFn: () => api.patient(pid!), enabled: !!pid });

  useEffect(() => { closeEvidence(); }, [pid]); // never carry an open source across patients

  const counts = bundle.data?.brief.counts;
  const tabCount: Record<string, number | undefined> = {
    communications: bundle.data?.threads.filter((t) => t.status === "awaiting_reply").length || undefined,
    documents: counts ? counts.documents + counts.notes : undefined,
    imaging: counts?.imaging,
  };

  return (
    <div className={clsx("grid min-h-0 flex-1", pid && assistantOpen ? "grid-cols-[280px_minmax(0,1fr)] xl:grid-cols-[270px_minmax(0,1fr)_360px] 2xl:grid-cols-[290px_minmax(0,1fr)_400px]" : "grid-cols-[280px_minmax(0,1fr)] xl:grid-cols-[290px_minmax(0,1fr)]")}>
      <div className="hidden min-h-0 md:block"><Worklist activeId={pid} /></div>
      <main id="main" className="relative col-span-2 min-h-0 overflow-y-auto scroll-thin md:col-span-1">
        {!pid && <Welcome />}
        {pid && bundle.isLoading && (
          <div className="space-y-4 p-6"><Skeleton className="h-24" /><Skeleton className="h-10 w-2/3" /><Skeleton className="h-64" /></div>
        )}
        {pid && bundle.isError && <div className="p-6"><ErrorState error={bundle.error} retry={() => bundle.refetch()} /></div>}
        {pid && bundle.data && (
          <>
            <div className="sticky top-0 z-10 border-b border-line bg-page/95 px-6 pt-5 backdrop-blur">
              <PatientHeader bundle={bundle.data} />
              <div className="mt-4 flex items-end justify-between gap-4">
                <nav aria-label="Patient record sections" className="-mb-px flex gap-3.5 overflow-x-auto 2xl:gap-5">
                  {TABS.map((t) => (
                    <Link key={t.id} to={`/patients/${pid}/${t.id}`} className={clsx("tab whitespace-nowrap", tab === t.id && "tab-active")}
                      aria-current={tab === t.id ? "page" : undefined}>
                      {t.label}
                      {tabCount[t.id] ? <span className={clsx("ml-1.5 rounded-full px-1.5 py-px text-[11px]", t.id === "communications" ? "bg-attn-100 text-attn-700" : "bg-sunken text-ink-3")}>{tabCount[t.id]}</span> : null}
                    </Link>
                  ))}
                </nav>
                <button className="btn-ghost mb-2 hidden shrink-0 xl:inline-flex" onClick={() => setAssistantOpen(!assistantOpen)}
                  aria-expanded={assistantOpen} aria-controls="assistant-panel" aria-label={assistantOpen ? "Hide assistant" : "Ask the record"}
                  title={assistantOpen ? "Hide assistant" : "Ask the record"}>
                  {assistantOpen ? <PanelRightClose className="h-4 w-4" /> : <PanelRightOpen className="h-4 w-4" />}
                  <span className={assistantOpen ? "hidden min-[1700px]:inline" : ""}>{assistantOpen ? "Hide assistant" : "Ask the record"}</span>
                </button>
              </div>
            </div>
            <div className="px-6 py-5">
              {tab === "brief" && <BriefTab bundle={bundle.data} onNavigate={(t) => navigate(`/patients/${pid}/${t}`)} />}
              {tab === "journey" && <JourneyTab bundle={bundle.data} />}
              {tab === "trends" && <TrendsTab bundle={bundle.data} />}
              {tab === "medications" && <MedicationsTab bundle={bundle.data} />}
              {tab === "communications" && <CommsTab bundle={bundle.data} />}
              {tab === "documents" && <DocumentsTab bundle={bundle.data} />}
              {tab === "imaging" && <ImagingTab bundle={bundle.data} />}
            </div>
          </>
        )}
        {pid && !assistantOpen && (
          <button onClick={() => setAssistantOpen(true)} className="btn-primary fixed bottom-5 right-5 z-20 shadow-pop xl:hidden">
            <Sparkles className="h-4 w-4" /> Ask the record
          </button>
        )}
      </main>
      {pid && bundle.data && assistantOpen && (
        <div id="assistant-panel" className="fixed inset-y-0 right-0 z-30 w-full max-w-[420px] shadow-pop xl:static xl:z-auto xl:w-auto xl:max-w-none xl:shadow-none">
          <AssistantPanel bundle={bundle.data} onClose={() => setAssistantOpen(false)} />
        </div>
      )}
      {pid && bundle.data && <EvidenceDrawer bundle={bundle.data} />}
    </div>
  );
}
