import { useEffect, useRef, useState, type ChangeEvent, type CSSProperties } from "react";
import { api } from "../services/api";

interface ErrorLogAnalyzerProps {
  onClose: () => void;
}

interface DiagnosticFinding {
  category: string;
  title: string;
  summary: string;
  confidence: number;
  confidence_basis: string;
  evidence: string[];
  hypotheses: string[];
  alternatives: string[];
  troubleshooting: string[];
  verification: string[];
}

interface LocalModelHypothesis {
  hypothesis?: string;
  evidence_quotes?: string[];
  confidence?: "low" | "medium";
  alternatives?: string[];
  checks?: string[];
}

interface DiagnosticReport {
  filename: string;
  input_format: string;
  truncated: boolean;
  summary: {
    record_count: number;
    timestamp_count: number;
    error_count: number;
    exception_count: number;
    stack_frame_count: number;
    severity_counts: Record<string, number>;
    services: string[];
  };
  events: Array<{
    line: number;
    timestamp: string | null;
    severity: string | null;
    error_code: string | null;
    exception: string | null;
    stack_frame: boolean;
    service: string | null;
    text: string;
  }>;
  correlation: {
    status: "supported" | "insufficient_history" | "not_established";
    message: string;
  };
  findings: DiagnosticFinding[];
  local_model_configured: boolean;
  local_model_hypotheses?: {
    hypotheses: LocalModelHypothesis[];
    missing_context: string[];
    notice: string;
  };
}

const MAX_FILE_BYTES = 5 * 1024 * 1024;
const MAX_TEXT_CHARS = 200_000;
const ACCEPTED_EXTENSIONS = new Set([
  "log", "txt", "json", "xml", "sarif", "junit",
]);

function formatReportForCopy(report: DiagnosticReport): string {
  const lines = [
    `Diagnostic report: ${report.filename}`,
    `Format: ${report.input_format.toUpperCase()} · ${report.summary.record_count} records · ${report.summary.error_count} errors · ${report.summary.exception_count} exceptions · ${report.summary.stack_frame_count} stack frames`,
    `Correlation: ${report.correlation.message}`,
  ];

  for (const finding of report.findings) {
    lines.push(
      "",
      finding.title,
      finding.summary,
      `Heuristic score: ${finding.confidence}/100. ${finding.confidence_basis}`,
      "Observed evidence:",
      ...(finding.evidence.length ? finding.evidence.map((item) => `- ${item}`) : ["- No direct matching log line was found."]),
      "Hypotheses, not confirmed causes:",
      ...finding.hypotheses.map((item) => `- ${item}`),
      ...(finding.alternatives.length ? ["Alternative explanations:", ...finding.alternatives.map((item) => `- ${item}`)] : []),
      "Troubleshooting:",
      ...finding.troubleshooting.map((item) => `- ${item}`),
      "How to verify:",
      ...finding.verification.map((item) => `- ${item}`),
    );
  }
  if (report.local_model_hypotheses) {
    lines.push("", "Unverified local-model hypotheses", report.local_model_hypotheses.notice);
    for (const item of report.local_model_hypotheses.hypotheses) {
      lines.push(
        `- ${item.hypothesis ?? "Hypothesis not provided"} (model confidence: ${item.confidence ?? "low"}; not calibrated)`,
        ...(item.evidence_quotes?.length ? item.evidence_quotes.map((quote) => `  Evidence: ${quote}`) : []),
        ...(item.alternatives?.map((alternative) => `  Alternative: ${alternative}`) ?? []),
        ...(item.checks?.map((check) => `  Check: ${check}`) ?? []),
      );
    }
    if (report.local_model_hypotheses.missing_context.length) {
      lines.push(
        "Additional context requested:",
        ...report.local_model_hypotheses.missing_context.map((item) => `- ${item}`),
      );
    }
  }
  return lines.join("\n");
}

export default function ErrorLogAnalyzer({ onClose }: ErrorLogAnalyzerProps) {
  const reportRef = useRef<HTMLDivElement>(null);
  const [text, setText] = useState("");
  const [filename, setFilename] = useState("pasted text");
  const [report, setReport] = useState<DiagnosticReport | null>(null);
  const [localModelAvailable, setLocalModelAvailable] = useState(false);
  const [useLocalModel, setUseLocalModel] = useState(false);
  const [inputTruncated, setInputTruncated] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [copyStatus, setCopyStatus] = useState("");

  useEffect(() => {
    let active = true;
    api.get<{ available: boolean }>("/diagnostics/local-model")
      .then(({ data }) => {
        if (active) setLocalModelAvailable(data.available);
      })
      .catch(() => {
        if (active) setLocalModelAvailable(false);
      });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    if (report) {
      reportRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }, [report]);

  async function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    setReport(null);
    setError("");
    setCopyStatus("");
    setInputTruncated(false);
    if (!file) return;

    const extension = file.name.split(".").pop()?.toLowerCase() ?? "";
    if (!ACCEPTED_EXTENSIONS.has(extension)) {
      setError("Choose a supported text, JSON, XML, SARIF, or JUnit report.");
      event.target.value = "";
      return;
    }
    if (file.size > MAX_FILE_BYTES) {
      setError("Choose a supported text file smaller than 5 MB.");
      event.target.value = "";
      return;
    }

    try {
      const contents = await file.text();
      setInputTruncated(contents.length > MAX_TEXT_CHARS);
      setText(contents.slice(0, MAX_TEXT_CHARS));
      setFilename(file.name);
    } catch {
      setError("This file could not be read as text. Export binary event logs as XML first.");
    }
  }

  async function handleAnalyze() {
    setError("");
    setCopyStatus("");
    setReport(null);
    const content = text.trim().slice(0, MAX_TEXT_CHARS);
    if (!content) {
      setError("Paste an error message or select a supported report first.");
      return;
    }
    if (useLocalModel && !localModelAvailable) {
      setError("No local model is configured. Rules-only analysis is still available.");
      return;
    }

    setBusy(true);
    try {
      const { data } = await api.post<DiagnosticReport>(
        "/diagnostics/analyze",
        { content, filename, use_local_model: useLocalModel },
        { timeout: useLocalModel ? 50_000 : 15_000 },
      );
      setReport(data);
    } catch {
      setError(
        useLocalModel
          ? "Analysis failed. Check that the local Ollama model is running, or turn off local-model analysis and retry."
          : "Analysis failed. Check the backend connection and retry.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function handleCopyReport() {
    if (!report) return;
    try {
      await navigator.clipboard.writeText(formatReportForCopy(report));
      setCopyStatus("Diagnostic report copied.");
    } catch {
      setCopyStatus("Could not copy automatically. Select the report text and copy it manually.");
    }
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="error-log-title"
      style={styles.backdrop}
    >
      <section style={styles.panel}>
        <header style={styles.header}>
          <div>
            <h2 id="error-log-title" style={styles.title}>Analyze Error Logs</h2>
            <p style={styles.subtle}>
              Logs are processed by the configured CVIS backend. If it is hosted on another machine, the log text is sent to that host. CVIS does not send logs to external AI services.
            </p>
          </div>
          <button type="button" onClick={onClose} style={styles.close}>Close</button>
        </header>

        <label style={styles.label}>
          Select a supported log or structured report (.log, .txt, .json, .xml, .sarif, .junit)
          <input
            type="file"
            accept=".log,.txt,.json,.xml,.sarif,.junit,application/json,application/xml,text/plain"
            onChange={handleFileChange}
            style={styles.file}
          />
        </label>

        <label htmlFor="error-log-input" style={styles.label}>
          Or paste error messages, stack traces, or surrounding events
        </label>
        <textarea
          id="error-log-input"
          value={text}
          onChange={(event) => {
            setText(event.target.value.slice(0, MAX_TEXT_CHARS));
            setInputTruncated(event.target.value.length > MAX_TEXT_CHARS);
            setFilename("pasted text");
            setReport(null);
            setError("");
            setCopyStatus("");
          }}
          placeholder="Paste relevant timestamped logs, an exception, or a complete stack trace..."
          style={styles.textarea}
        />
        <div style={styles.note}>
            Supports plain text, JSON/JSONL, XML/JUnit, and SARIF. Binary Windows .evtx files must first be exported as XML. Analysis uses signatures, exception/stack-frame parsing, and cautious correlation when request IDs or service dependencies support a link. Correlation does not establish causation.
        </div>

        {localModelAvailable && (
          <label style={styles.modelChoice}>
            <input
              type="checkbox"
              checked={useLocalModel}
              onChange={(event) => setUseLocalModel(event.target.checked)}
            />
            <span>
              Use the optional local Ollama model for unfamiliar errors
              <small>Sent only to Ollama on the CVIS backend host. Its output is shown as unverified hypotheses.</small>
            </span>
          </label>
        )}
        {!localModelAvailable && (
          <p style={styles.subtle}>
            Optional local-model reasoning is not configured. Rules and parsers still work.
          </p>
        )}

        {error && <p role="alert" style={styles.error}>{error}</p>}
        <button type="button" onClick={() => void handleAnalyze()} disabled={busy} style={styles.action}>
          {busy ? "Analyzing…" : "Analyze"}
        </button>

        {report && (
          <div ref={reportRef} aria-live="polite" style={styles.report}>
            <div style={styles.reportHeading}>
              <h3 style={styles.resultTitle}>Diagnostic report</h3>
              <button type="button" onClick={() => void handleCopyReport()} style={styles.copy}>
                Copy full report
              </button>
            </div>
            {copyStatus && <p role="status" style={styles.subtle}>{copyStatus}</p>}
            <p style={styles.subtle}>Scroll within this dialog to reach all findings and verification steps.</p>
            <p style={styles.resultText}>
              {report.filename} · {report.input_format.toUpperCase()} · {report.summary.record_count} records · {report.summary.error_count} errors · {report.summary.exception_count} exceptions · {report.summary.stack_frame_count} stack frames
            </p>
            {(report.truncated || inputTruncated) && (
              <p style={styles.warning}>Input was truncated to 200,000 characters; findings may omit later events.</p>
            )}
            {report.summary.services.length > 0 && (
              <p style={styles.resultText}>Services detected: {report.summary.services.join(", ")}</p>
            )}
            {report.correlation.message && (
              <p role="status" style={styles.correlation}>{report.correlation.message}</p>
            )}

            {report.findings.map((finding, index) => (
              <article key={`${finding.category}-${index}`} style={styles.finding}>
                <h4 style={styles.findingTitle}>{finding.title}</h4>
                <p style={styles.resultText}>{finding.summary}</p>
                <p style={styles.confidence}>
                  Heuristic score: {finding.confidence}/100 — {finding.confidence_basis}
                </p>
                <h5 style={styles.sectionTitle}>Observed evidence</h5>
                <ul style={styles.list}>
                  {finding.evidence.map((item, evidenceIndex) => (
                    <li key={`${evidenceIndex}-${item}`}>{item}</li>
                  ))}
                  {finding.evidence.length === 0 && <li>No direct matching log line was found.</li>}
                </ul>
                <h5 style={styles.sectionTitle}>Hypotheses, not confirmed causes</h5>
                <ul style={styles.list}>
                  {finding.hypotheses.map((item) => <li key={item}>{item}</li>)}
                </ul>
                {finding.alternatives.length > 0 && (
                  <>
                    <h5 style={styles.sectionTitle}>Alternative explanations</h5>
                    <ul style={styles.list}>
                      {finding.alternatives.map((item) => <li key={item}>{item}</li>)}
                    </ul>
                  </>
                )}
                <h5 style={styles.sectionTitle}>Troubleshooting</h5>
                <ul style={styles.list}>
                  {finding.troubleshooting.map((item) => <li key={item}>{item}</li>)}
                </ul>
                <h5 style={styles.sectionTitle}>How to verify</h5>
                <ul style={styles.list}>
                  {finding.verification.map((item) => <li key={item}>{item}</li>)}
                </ul>
              </article>
            ))}

            {report.local_model_hypotheses && (
              <article style={styles.modelReport}>
                <h4 style={styles.findingTitle}>Unverified local-model hypotheses</h4>
                <p style={styles.warning}>{report.local_model_hypotheses.notice}</p>
                {report.local_model_hypotheses.hypotheses.map((item, index) => (
                  <div key={`${item.hypothesis}-${index}`} style={styles.modelHypothesis}>
                    <strong>{item.hypothesis ?? "Hypothesis not provided"}</strong>
                    <p style={styles.confidence}>Model confidence label: {item.confidence ?? "low"}; not calibrated.</p>
                    {item.evidence_quotes?.length ? (
                      <>
                        <h5 style={styles.sectionTitle}>Validated evidence quotes</h5>
                        <ul style={styles.list}>
                          {item.evidence_quotes.map((quote) => <li key={quote}>{quote}</li>)}
                        </ul>
                      </>
                    ) : (
                      <p style={styles.subtle}>The model did not provide a verifiable quote from the supplied logs.</p>
                    )}
                    {item.alternatives?.length ? (
                      <ul style={styles.list}>
                        {item.alternatives.map((alternative) => <li key={alternative}>{alternative}</li>)}
                      </ul>
                    ) : null}
                    {item.checks?.length ? (
                      <ul style={styles.list}>
                        {item.checks.map((check) => <li key={check}>{check}</li>)}
                      </ul>
                    ) : null}
                  </div>
                ))}
                {report.local_model_hypotheses.missing_context.length > 0 && (
                  <>
                    <h5 style={styles.sectionTitle}>Additional context requested</h5>
                    <ul style={styles.list}>
                      {report.local_model_hypotheses.missing_context.map((item) => <li key={item}>{item}</li>)}
                    </ul>
                  </>
                )}
              </article>
            )}
          </div>
        )}
      </section>
    </div>
  );
}

const styles: Record<string, CSSProperties> = {
  backdrop: {
    position: "fixed", inset: 0, zIndex: 1100, background: "rgba(1, 5, 15, .88)",
    display: "grid", placeItems: "center", padding: 20,
  },
  panel: {
    width: "min(900px, 100%)", maxHeight: "90vh", overflowY: "auto", padding: 24,
    color: "#ddeeff", background: "#081426", border: "1px solid rgba(0, 212, 255, .35)",
    borderRadius: 10, boxShadow: "0 20px 80px rgba(0,0,0,.55)", fontFamily: "system-ui, sans-serif",
  },
  header: { display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 16 },
  title: { margin: "0 0 6px", color: "#00d4ff" },
  subtle: { color: "#9ab1c9", fontSize: 13, lineHeight: 1.5 },
  close: { color: "#ddeeff", background: "#13263d", border: "1px solid #38506b", padding: "8px 12px", cursor: "pointer" },
  label: { display: "block", margin: "18px 0 8px", color: "#c3d9ef", fontSize: 13 },
  file: { display: "block", marginTop: 8, color: "#c3d9ef" },
  textarea: {
    width: "100%", minHeight: 180, resize: "vertical", padding: 12, color: "#e9f4ff",
    background: "#020914", border: "1px solid #38506b", borderRadius: 4,
    font: "12px/1.5 ui-monospace, monospace",
  },
  note: { marginTop: 8, color: "#92a8bf", fontSize: 12, lineHeight: 1.5 },
  modelChoice: { display: "flex", alignItems: "flex-start", gap: 10, marginTop: 14, color: "#c3d9ef", fontSize: 13 },
  error: { color: "#ff8e9e", fontSize: 13 },
  action: { marginTop: 14, padding: "10px 16px", color: "#001018", background: "#00d4ff", border: 0, borderRadius: 4, fontWeight: 700, cursor: "pointer" },
  report: { marginTop: 18, userSelect: "text", cursor: "text", scrollMarginTop: 8 },
  reportHeading: { display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, flexWrap: "wrap" },
  finding: { marginTop: 14, padding: 16, background: "#0c1d2f", border: "1px solid #26425e", borderRadius: 6, userSelect: "text" },
  modelReport: { marginTop: 14, padding: 16, background: "#17172a", border: "1px solid #55478a", borderRadius: 6 },
  modelHypothesis: { padding: "12px 0", borderTop: "1px solid #55478a" },
  resultTitle: { margin: "0 0 8px", color: "#7ce4ff" },
  copy: { color: "#ddeeff", background: "#13263d", border: "1px solid #38506b", borderRadius: 4, padding: "8px 12px", cursor: "pointer" },
  correlation: { color: "#a9d9f0", background: "#10283a", borderLeft: "3px solid #00d4ff", padding: "10px 12px", lineHeight: 1.5, userSelect: "text" },
  findingTitle: { margin: "0 0 8px", color: "#a5ddff" },
  resultText: { color: "#d6e6f5", lineHeight: 1.5, overflowWrap: "anywhere" },
  confidence: { color: "#ffd27c", fontSize: 12, lineHeight: 1.5 },
  warning: { color: "#ffcf83", fontSize: 13, lineHeight: 1.5 },
  sectionTitle: { margin: "14px 0 5px", color: "#b7d4eb" },
  list: { margin: 0, paddingLeft: 20, color: "#c4d6e6", lineHeight: 1.6, overflowWrap: "anywhere", userSelect: "text" },
};
