const MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

export const toDate = (iso: string) => new Date(iso.length === 10 ? iso + "T00:00:00Z" : iso);
export function fmtDate(iso?: string | null, withYear = true) {
  if (!iso) return "—";
  const d = toDate(iso);
  return `${d.getUTCDate()} ${MON[d.getUTCMonth()]}${withYear ? " " + d.getUTCFullYear() : ""}`;
}
export function fmtDateTime(iso?: string | null) {
  if (!iso) return "—";
  const d = toDate(iso);
  return `${fmtDate(iso)} · ${String(d.getUTCHours()).padStart(2, "0")}:${String(d.getUTCMinutes()).padStart(2, "0")} UTC`;
}
export function fmtRange(a: string, b: string) {
  return fmtDate(a, false) === fmtDate(b, false) ? fmtDate(a) : `${fmtDate(a, false)} – ${fmtDate(b)}`;
}
export function daysBetween(a: string, b: string) {
  return Math.round((toDate(b).getTime() - toDate(a).getTime()) / 86400000);
}
export function relDays(iso: string, asOf: string) {
  const d = daysBetween(iso, asOf);
  if (d <= 0) return "today";
  if (d === 1) return "1 day ago";
  if (d < 45) return `${d} days ago`;
  return `${Math.round(d / 30)} months ago`;
}
export const num = (v: number) => (Number.isInteger(v) ? String(v) : String(+v.toFixed(2)));
export const CLASS_LABEL: Record<string, string> = { AMB: "Ambulatory", EMER: "Emergency", IMP: "Inpatient", VR: "Virtual" };
export const SOURCE_LABEL: Record<string, string> = {
  clinical_note: "Clinical note", pdf_document: "PDF document", document: "PDF document", portal_message: "Portal message",
  imaging_report: "Imaging report", encounter: "Encounter", medication: "Medication order", observation: "Measurement",
  thread: "Portal thread", follow_up: "Follow-up item", note: "Clinical note",
};
export const sexShort = (s: string) => (s === "female" ? "F" : s === "male" ? "M" : s);
/** Encounter-class hues: validated categorical order (blue, orange, aqua, magenta); identity also carried by text labels. */
export const CLASS_COLOR: Record<string, string> = { AMB: "#2a78d6", EMER: "#eb6834", IMP: "#1baf7a", VR: "#e87ba4" };
