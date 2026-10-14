import type { Answer, Bundle, Meta, Page, WorklistRow } from "./types";

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, { ...init, headers: { "Content-Type": "application/json", ...(init?.headers || {}) } });
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail ?? detail; } catch { /* non-JSON error */ }
    throw new ApiError(res.status, detail);
  }
  return res.json() as Promise<T>;
}

export const api = {
  meta: () => request<Meta>("/api/meta"),
  worklist: () => request<WorklistRow[]>("/api/patients"),
  patient: (pid: string) => request<Bundle>(`/api/patients/${pid}`),
  pages: (pid: string, docId: string) => request<Page[]>(`/api/patients/${pid}/documents/${docId}/pages`),
  suggestions: (pid: string) => request<{ q: string; kind: string }[]>(`/api/patients/${pid}/suggestions`),
  ask: (pid: string, question: string) => request<Answer>(`/api/patients/${pid}/ask`, { method: "POST", body: JSON.stringify({ question }) }),
  operations: () => request<any>("/api/operations"),
  evaluation: () => request<any>("/api/evaluation"),
  imagingMeta: (pid: string, sid: string) => request<Record<string, any>>(`/api/patients/${pid}/imaging/${sid}/metadata`),
  pdfUrl: (pid: string, docId: string) => `/api/patients/${pid}/documents/${docId}/file`,
  imageUrl: (pid: string, sid: string, wc?: number, ww?: number) =>
    `/api/patients/${pid}/imaging/${sid}/image.png` + (wc !== undefined && ww !== undefined ? `?wc=${Math.round(wc)}&ww=${Math.round(ww)}` : ""),
};
