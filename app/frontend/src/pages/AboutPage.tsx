import { useQuery } from "@tanstack/react-query";
import { BadgeCheck, FlaskConical, ShieldCheck, ShieldX } from "lucide-react";
import { SectionTitle } from "../components/ui";
import { api } from "../lib/api";
import { fmtDate } from "../lib/format";

type Box = { x: number; y: number; w: number; h: number; title: string; lines: string[]; proposed?: boolean; tone?: "uc" | "app" | "ai" | "src" };
const TONE = { uc: ["#eef4fc", "#2a78d6"], app: ["#ecf7f3", "#0f7a5a"], ai: ["#f3f0fd", "#5b46c9"], src: ["#f5f5f3", "#77839a"] } as const;

function Node({ b }: { b: Box }) {
  const [fill, stroke] = b.proposed ? ["#ffffff", "#9aa3b2"] : TONE[b.tone ?? "src"];
  return (
    <g>
      <rect x={b.x} y={b.y} width={b.w} height={b.h} rx={10} fill={fill} stroke={stroke} strokeWidth={1.5} strokeDasharray={b.proposed ? "5 4" : undefined} />
      <text x={b.x + 12} y={b.y + 21} className="text-[12.5px] font-semibold" fill={b.proposed ? "#5f6b80" : "#0f1b2d"}>{b.title}</text>
      {b.lines.map((l, i) => <text key={i} x={b.x + 12} y={b.y + 39 + i * 15} className="text-[11px]" fill="#44516a">{l}</text>)}
    </g>
  );
}

function Arrow({ d, dashed }: { d: string; dashed?: boolean }) {
  return <path d={d} fill="none" stroke={dashed ? "#9aa3b2" : "#44516a"} strokeWidth={1.5} strokeDasharray={dashed ? "5 4" : undefined} markerEnd="url(#arrow)" />;
}

function Architecture() {
  const boxes: Box[] = [
    { x: 10, y: 40, w: 200, h: 92, title: "Synthetic source generator", tone: "src", lines: ["FHIR-style NDJSON (11 resources)", "Clinical PDFs (text + scanned)", "DICOM secondary capture"] },
    { x: 250, y: 40, w: 210, h: 92, title: "UC Volume · v5 raw drop", tone: "uc", lines: ["cliniq_v5_stage.raw · SHA-256 manifest", "23 PDFs · 10 DICOM objects", "Read-only to the app"] },
    { x: 500, y: 20, w: 250, h: 132, title: "Serverless ingestion notebook", tone: "uc", lines: ["PDF page extraction (text layer, no OCR)", "Page-level patient/encounter identity", "  check → quarantine on mismatch", "DICOM header verification", "Chunking + gte-large-en embeddings", "14 integrity checks (fail = no publish)"] },
    { x: 790, y: 40, w: 230, h: 92, title: "Delta · healthcare.cliniq_v5_stage", tone: "uc", lines: ["Curated clinical tables", "document_pages · knowledge_chunks", "chunk_embeddings · integrity_checks"] },
    { x: 790, y: 190, w: 230, h: 76, title: "Serverless SQL warehouse", tone: "uc", lines: ["2X-Small · parameterized,", "patient-bound reads (SELECT only)"] },
    { x: 250, y: 190, w: 500, h: 162, title: "Databricks App · cliniq-nexus (FastAPI + React)", tone: "app", lines: [
      "Read models: worklist · brief · journey · trends · medications · communications ·",
      "  documents · imaging · operations",
      "Assistant: policy router → deterministic answers from records, or",
      "  hybrid retrieval (BM25 + embedding RRF, patient-scoped) → grounded generation →",
      "  validation (schema, truncation, citation, numbers/dates, lexical support, advice/imaging",
      "  language) → independent verifier → answer or evidence-only fallback",
      "Files: PDFs and DICOM streamed from the volume after patient ownership check",
    ] },
    { x: 10, y: 190, w: 200, h: 76, title: "Physician · coordinator · ops", tone: "src", lines: ["Browser via Databricks Apps SSO", "Read-only workspace"] },
    { x: 250, y: 380, w: 500, h: 78, title: "Foundation Model APIs (pay-per-token, Free Edition quota)", tone: "ai", lines: ["gpt-oss-120b generator (20b fallback) · llama-3.3-70b verifier", "gte-large-en query embeddings"] },
    { x: 10, y: 300, w: 200, h: 76, title: "v4 Streamlit source (retained)", tone: "src", lines: ["Workspace folder + v4/Gold data", "One-command rollback target"] },
    { x: 790, y: 300, w: 230, h: 54, title: "Managed Vector Search", proposed: true, lines: ["Proposed when corpus grows"] },
    { x: 790, y: 364, w: 230, h: 54, title: "OCR for scanned PDFs", proposed: true, lines: ["Proposed (e.g. ai_parse_document)"] },
    { x: 790, y: 428, w: 230, h: 54, title: "De-identified real DICOM", proposed: true, lines: ["Proposed; licence review first"] },
    { x: 10, y: 410, w: 200, h: 72, title: "On-behalf-of-user auth", proposed: true, lines: ["Proposed: row-level security,", "MLflow tracing, FHIR API feed"] },
  ];
  return (
    <svg viewBox="0 0 1030 500" className="w-full" role="img" aria-label="ClinIQ Nexus v5 architecture: implemented components solid, proposed dashed">
      <defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="#44516a" /></marker></defs>
      <Arrow d="M210 86 H246" /><Arrow d="M460 86 H496" /><Arrow d="M750 86 H786" />
      <Arrow d="M905 132 V186" /><Arrow d="M786 228 H754" /><Arrow d="M210 228 H246" />
      <Arrow d="M500 352 V376" /><Arrow d="M355 132 V186" />
      <text x={362} y={165} className="text-[10.5px]" fill="#77839a">PDF / DICOM files</text>
      <Arrow d="M905 266 V296" dashed />
      {boxes.map((b) => <Node key={b.title} b={b} />)}
    </svg>
  );
}

const SAFETY = [
  ["Patient isolation", "Every patient read binds the patient ID as a SQL parameter, is re-checked row by row, and files are served only after ownership checks. The assistant's candidate pool is built only from the selected patient's rows.", "test_isolation · test_api_scope"],
  ["Misfiled documents", "Pages whose printed identifiers disagree with the index are quarantined at ingestion and never published.", "DQ-04, DQ-05, DQ-06"],
  ["Structured first", "Medications, vitals, labs, messages, follow-up, imaging inventory and gaps are answered directly from records — no model involved.", "test_router · test_structured"],
  ["Citations must resolve", "Generated claims may cite only retrieved sources (S1…Sn), which map to a note, PDF page, message, report, encounter or order.", "test_validator"],
  ["Citations must support", "Numbers and dates in each claim must appear in its cited text; lexical support threshold; no advice or image-finding language absent from sources; an independent verifier model must judge each claim supported.", "test_validator · eval suite"],
  ["Truncation rejected", "Responses ending for any reason other than a normal stop are rejected.", "test_validator"],
  ["Unknown ≠ negative", "Missing information is returned as an explicit 'Not documented' claim, never as a negative finding.", "prompt contract · eval suite"],
  ["Scope & advice policy", "Questions about other patients, requests for recommendations, and image interpretation are handled by policy before any retrieval or generation.", "test_router · eval suite"],
  ["Graceful failure", "Model, embedding or warehouse failures fall back to evidence-only answers or lexical retrieval with an explanation.", "test_fallbacks"],
];

export default function AboutPage() {
  const ev = useQuery({ queryKey: ["evaluation"], queryFn: api.evaluation });
  const meta = useQuery({ queryKey: ["meta"], queryFn: api.meta });
  const e = ev.data;
  return (
    <main id="main" className="min-h-0 flex-1 overflow-y-auto scroll-thin">
      <div className="mx-auto max-w-[1180px] space-y-9 px-8 py-8">
        <header className="max-w-3xl">
          <p className="eyebrow text-brand-700">How it works</p>
          <h1 className="mt-1 text-2xl font-semibold tracking-tight text-ink">Connected healthcare data → clinical context → evidence-grounded answers</h1>
          <p className="mt-2 text-[14px] leading-relaxed text-ink-2">
            ClinIQ Nexus is a technology demonstration built entirely on Databricks Free Edition with synthetic records. It shows how FHIR-style structured data,
            clinical notes, PDF documents, patient-portal communication and DICOM imaging can be unified in Unity Catalog and presented to a physician as one
            longitudinal, citable record. It is not a clinical decision-support system, an EHR, or HIPAA-validated software.
          </p>
        </header>

        <section className="card p-5">
          <SectionTitle title="Architecture (v5)" hint="Solid = implemented and running. Dashed = proposed future work, not implemented." />
          <Architecture />
        </section>

        <section>
          <SectionTitle icon={ShieldCheck} title="AI safety contract" hint="Each guard is enforced in code and covered by automated tests or ingestion checks." />
          <div className="card overflow-hidden">
            <table className="w-full text-[13px]">
              <tbody>
                {SAFETY.map(([g, how, test]) => (
                  <tr key={g} className="border-b border-line align-top last:border-0">
                    <td className="w-48 px-4 py-3 font-semibold text-ink">{g}</td>
                    <td className="px-4 py-3 text-ink-2">{how}</td>
                    <td className="w-52 px-4 py-3 text-[12px] text-ink-3">{test}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <section>
          <SectionTitle icon={FlaskConical} title="Evaluation scorecard" hint={e?.available === false ? "No evaluation results are bundled with this build." : e ? `Run ${fmtDate(e.run_at)} against ${e.environment} · models ${e.models?.generator}` : ""} />
          {e && e.available !== false && (
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              {e.metrics.map((m: any) => (
                <div key={m.name} className="card p-4">
                  <div className="flex items-center gap-1.5 text-[12.5px] text-ink-3">{m.passed ? <BadgeCheck className="h-4 w-4 text-evidence-600" /> : <ShieldX className="h-4 w-4 text-crit-600" />}{m.name}</div>
                  <div className="mt-1 text-2xl font-semibold text-ink">{m.value}</div>
                  <div className="text-[12px] text-ink-3">{m.detail}</div>
                </div>
              ))}
            </div>
          )}
        </section>

        <section className="grid gap-6 lg:grid-cols-2">
          <div className="card p-5">
            <SectionTitle title="Runtime configuration" />
            <dl className="space-y-1.5 text-[13px]">
              {meta.data && [
                ["Data source", meta.data.source.mode === "warehouse" ? `Unity Catalog via SQL warehouse (${meta.data.source.schema})` : "Local snapshot"],
                ["Dataset", `${meta.data.dataset.dataset_version} · records as of ${fmtDate(meta.data.dataset.as_of)}`],
                ["Generator model", meta.data.models.generator], ["Fallback model", meta.data.models.fallback],
                ["Verifier model", meta.data.models.verifier], ["Embeddings", meta.data.models.embedding],
              ].map(([k, v]) => <div key={k} className="grid grid-cols-[140px_1fr] gap-2"><dt className="text-ink-3">{k}</dt><dd className="text-ink">{v}</dd></div>)}
            </dl>
          </div>
          <div className="card p-5">
            <SectionTitle title="Known limitations" />
            <ul className="list-disc space-y-1.5 pl-5 text-[13px] text-ink-2">
              <li>Ten synthetic patients; metrics and trends are illustrative, not statistically meaningful.</li>
              <li>Imaging objects are synthetic test patterns; no image interpretation exists or is generated.</li>
              <li>Scanned PDFs are not OCR'd; their content is viewable but not searchable or citable.</li>
              <li>Retrieval embeddings are compared in-app; managed Vector Search is not provisioned.</li>
              <li>Automated grounding checks reduce but do not eliminate the need for human review.</li>
              <li>Free Edition apps stop after 24 hours and pay-per-token endpoints are rate-limited.</li>
            </ul>
          </div>
        </section>
      </div>
    </main>
  );
}
