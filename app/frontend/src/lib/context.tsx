import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";
import type { Ref } from "./types";

export interface EvidenceTarget extends Ref {
  highlight?: string;          // passage to highlight inside the source
  patientId: string;
}

interface Ctx {
  evidence: EvidenceTarget | null;
  openEvidence: (t: EvidenceTarget) => void;
  closeEvidence: () => void;
  assistantOpen: boolean;
  setAssistantOpen: (v: boolean) => void;
  pendingQuestion: string | null;
  askAssistant: (q: string) => void;
  consumeQuestion: () => string | null;
}

const WorkspaceContext = createContext<Ctx | null>(null);

export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const [evidence, setEvidence] = useState<EvidenceTarget | null>(null);
  const [assistantOpen, setAssistantOpen] = useState(() => typeof window === "undefined" || window.innerWidth >= 1280);
  const [pendingQuestion, setPending] = useState<string | null>(null);
  const askAssistant = useCallback((q: string) => { setAssistantOpen(true); setPending(q); }, []);
  const consumeQuestion = useCallback(() => { const q = pendingQuestion; setPending(null); return q; }, [pendingQuestion]);
  const value = useMemo(() => ({
    evidence, openEvidence: setEvidence, closeEvidence: () => setEvidence(null),
    assistantOpen, setAssistantOpen, pendingQuestion, askAssistant, consumeQuestion,
  }), [evidence, assistantOpen, pendingQuestion, askAssistant, consumeQuestion]);
  return <WorkspaceContext.Provider value={value}>{children}</WorkspaceContext.Provider>;
}

export function useWorkspace() {
  const ctx = useContext(WorkspaceContext);
  if (!ctx) throw new Error("useWorkspace outside provider");
  return ctx;
}
