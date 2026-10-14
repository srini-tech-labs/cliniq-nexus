export type ClassCode = "AMB" | "EMER" | "IMP" | "VR";

export interface Patient {
  patient_id: string; display_name: string; mrn: string; sex: string; birth_date: string; age_years: number;
  primary_clinician: string; care_program: string; program_summary: string;
}
export interface WorklistRow {
  patient_id: string; display_name: string; sex: string; age_years: number; mrn: string; care_program: string;
  primary_clinician: string; last_encounter_at: string | null; last_encounter_type: string | null;
  last_encounter_class: ClassCode | null; recent_acute_at: string | null; recent_acute_class: ClassCode | null;
  awaiting_reply: number; routed_pending: number; overdue_follow_ups: number; documents: number; imaging: number; encounters: number;
}
export interface Encounter {
  encounter_id: string; patient_id: string; status: string; class_code: ClassCode; class_display: string; encounter_type: string; service: string;
  attending: string; location: string; reason: string; disposition: string; start_at: string; end_at: string; duration_hours: number;
}
export interface Condition { condition_id: string; encounter_id: string; code: string; display: string; clinical_status: string; recorded_at: string; code_system: string }
export interface Observation {
  observation_id: string; encounter_id: string; category: "vital-signs" | "laboratory"; code: string; measure_key: string; name: string;
  value: number; unit: string; display_unit: string; ref_low: number | null; ref_high: number | null; interpretation: "H" | "L" | "N" | null;
  panel_id: string | null; effective_at: string;
}
export interface Medication {
  medication_request_id: string; encounter_id: string; medication: string; dose: string; route: string; frequency: string;
  category: "home" | "inpatient" | "discharge" | "outpatient"; action: "reported" | "started" | "changed"; status: "active" | "stopped" | "completed";
  authored_on: string; end_date: string | null; prior_request_id: string | null; reason: string; stop_reason: string | null; prescriber: string | null;
}
export interface Note { note_id: string; encounter_id: string; note_type: string; author: string; authored_at: string; title: string; note_text: string }
export interface FollowUp {
  follow_up_id: string; encounter_id: string; description: string; due_date: string | null; status: "open" | "scheduled" | "completed";
  resolved_encounter_id: string | null; source_note_id: string;
}
export interface Message {
  message_id: string; thread_id: string; encounter_id: string; sender_role: "patient" | "care_team" | "clinician"; sender_name: string;
  sent_at: string; subject: string; message_body: string; is_routing_acknowledgment: boolean;
}
export interface Thread {
  thread_id: string; encounter_id: string; subject: string; category: string; status: "awaiting_reply" | "routed" | "answered";
  routed_to: string | null; opened_at: string; last_message_at: string; last_sender_role: string; message_count: number;
  first_response_minutes: number | null; messages: Message[];
}
export interface ImagingStudy {
  study_id: string; encounter_id: string; accession_number: string; ordered_procedure: string; indication: string; stored_modality: string;
  sop_class: string; image_content: string; study_at: string; report_id: string; ordering_clinician: string; rows: number; columns: number;
  dicom_header_verified: boolean; report: { report_id: string; report_text: string; status: string; authored_at: string } | null;
}
export interface Doc {
  document_id: string; encounter_id: string; doc_kind: string; doc_type: string; title: string; author: string; authored_at: string;
  file_name: string; received_via: string; page_count: number; file_bytes: number; has_text_layer: boolean; extraction_status: string;
  identity_status: "verified" | "unverified_no_text_layer"; identity_detail: string;
}
export interface Ref { type: string; id: string; label: string; date?: string; page?: number }
export interface BriefItem { id: string; kind: string; severity: "attention" | "info"; title: string; detail: string; date: string; refs: Ref[] }
export interface VitalTile {
  key: string; name: string; value: number; unit: string; at: string; observation_id: string; count: number;
  previous: number | null; previous_at: string | null; value_diastolic?: number | null; previous_diastolic?: number | null;
}
export interface Brief {
  items: BriefItem[]; active_encounter: Encounter | null; last_encounter: Encounter | null; days_since_last_encounter: number | null; vitals: VitalTile[];
  upcoming: FollowUp[]; counts: Record<string, number>;
}
export interface Bundle {
  patient: Patient; encounters: Encounter[]; conditions: Condition[]; observations: Observation[]; medications: Medication[];
  notes: Note[]; follow_ups: FollowUp[]; threads: Thread[]; imaging: ImagingStudy[]; documents: Doc[]; as_of: string;
  brief: Brief; problems: Condition[];
}
export interface Page { page_id: string; document_id: string; page_number: number; page_text: string; char_count: number; has_text_layer: boolean }

export interface Claim { kind: "documented" | "not_documented"; text: string; citations: string[]; support?: number }
export interface Source {
  sid: string; type: string; id: string; label: string; excerpt: string; date: string | null; page: number | null;
  document_id: string | null; encounter_id: string | null; score?: number | null;
}
export interface Answer {
  answer_id: string; question: string; patient_id: string; route: string; intent: string | null;
  mode: "structured" | "generated" | "evidence_only" | "policy" | "no_evidence"; notice: string | null; claims: Claim[]; sources: Source[];
  validation: { passed: boolean; level: string; checks: { name: string; passed: boolean; detail: string }[] };
  retrieval: { mode?: string; candidates?: number; considered?: number; searched?: Record<string, number>; not_searchable?: string[]; embedding_model?: string | null };
  model: string | null; latency_ms: number;
}
export interface Meta {
  dataset: Record<string, string>; source: { mode: string; schema?: string }; ai_enabled: boolean;
  models: { generator: string; fallback: string; verifier: string; embedding: string };
}
