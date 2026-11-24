import { useEffect, useRef, useState } from "react";
import { ApiError, downloadJson, getJob, quickValidate, startAnalysis } from "../services/api.js";
import UrlForm from "../components/UrlForm.jsx";
import ProgressPanel from "../components/ProgressPanel.jsx";
import StatusBanner from "../components/StatusBanner.jsx";
import SummaryStrip from "../components/SummaryStrip.jsx";
import SkillColumn from "../components/SkillColumn.jsx";
import ActivityTable from "../components/ActivityTable.jsx";

const POLL_MS = 800;

export default function AnalyzerPage() {
  const [url, setUrl] = useState("");
  const [job, setJob] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [downloadError, setDownloadError] = useState(null);
  const timer = useRef(null);

  useEffect(() => () => clearTimeout(timer.current), []);

  async function poll(jobId) {
    try {
      const next = await getJob(jobId);
      setJob(next);
      if (next.status === "done" || next.status === "error") {
        setBusy(false);
        if (next.status === "error") setError(next.error?.message || "The analysis failed.");
        return;
      }
      timer.current = setTimeout(() => poll(jobId), POLL_MS);
    } catch (e) {
      setBusy(false);
      setError(e instanceof ApiError ? e.message : "Lost contact with the backend.");
    }
  }

  async function handleSubmit() {
    clearTimeout(timer.current);
    setError(null);
    setDownloadError(null);
    const problem = quickValidate(url);
    if (problem) {
      setError(problem);
      return;
    }
    setBusy(true);
    setJob(null);
    try {
      const accepted = await startAnalysis(url);
      setJob({ job_id: accepted.job_id, username: accepted.username, status: "queued", progress: 0, stage: "Queued", log: [] });
      poll(accepted.job_id);
    } catch (e) {
      setBusy(false);
      setError(e.message);
    }
  }

  async function handleDownload() {
    setDownloadError(null);
    try {
      await downloadJson(job.download_filename);
    } catch (e) {
      setDownloadError(e.message);
    }
  }

  const result = job?.status === "done" ? job.result : null;

  return (
    <div className="page">
      <header className="masthead">
        <h1>LeetCode Profile Analyzer</h1>
        <p className="lede">
          Paste a public LeetCode profile link. The analyzer reads its skills and Recent Activity and gives you the
          data as a JSON file.
        </p>
        <UrlForm value={url} onChange={setUrl} onSubmit={handleSubmit} busy={busy} />
      </header>

      <main>
        {error && <StatusBanner tone="error" title="Analysis stopped">{error}</StatusBanner>}
        {busy && job && <ProgressPanel job={job} />}

        {result && (
          <>
            <section className="result-head" aria-labelledby="result-title">
              <div>
                <h2 id="result-title">
                  <a href={result.profile.profile_url} target="_blank" rel="noreferrer">{result.profile.username}</a>
                </h2>
                {result.profile.real_name && <p className="muted">{result.profile.real_name}</p>}
              </div>
              <button className="btn" onClick={handleDownload}>Download JSON</button>
            </section>
            {downloadError && <StatusBanner tone="error" title="Download failed">{downloadError}</StatusBanner>}
            <StatusBanner
              tone={result.metadata.scraping_status === "completed" ? "success" : "warning"}
              title={result.metadata.scraping_status === "completed" ? "Extraction completed" : "Extraction partially completed"}
            >
              <SectionNotes metadata={result.metadata} />
            </StatusBanner>
            <SummaryStrip result={result} />

            <section aria-labelledby="skills-title" className="block">
              <h2 id="skills-title">Skills</h2>
              <div className="skill-grid">
                <SkillColumn title="Fundamental" items={result.skills.fundamentals} />
                <SkillColumn title="Intermediate" items={result.skills.intermediate} />
                <SkillColumn title="Advanced" items={result.skills.advanced} />
              </div>
            </section>

            <section aria-labelledby="activity-title" className="block">
              <h2 id="activity-title">Recent Activity</h2>
              <p className="note">{result.metadata.history_coverage}</p>
              <ActivityTable records={result.recent_activity} />
            </section>
          </>
        )}

        {!busy && !result && !error && (
          <p className="empty">
            Profile links look like <code>https://leetcode.com/u/username/</code>. Only public data is read; nothing is
            sent to LeetCode on your behalf beyond what its profile page itself requests.
          </p>
        )}
      </main>
    </div>
  );
}

function SectionNotes({ metadata }) {
  const { sections, errors, warnings } = metadata;
  return (
    <>
      <ul className="section-list">
        {Object.entries(sections).map(([name, s]) => (
          <li key={name}>
            <strong>{name === "skills" ? "Skills" : "Recent Activity"}:</strong> {s.status}
            {s.missing?.length > 0 && <> (no data for {s.missing.join(", ")})</>}
          </li>
        ))}
      </ul>
      {errors.length > 0 && (
        <details>
          <summary>{errors.length} problem{errors.length > 1 ? "s" : ""} during extraction</summary>
          <ul>{errors.map((e, i) => <li key={i}>{e}</li>)}</ul>
        </details>
      )}
      {warnings.length > 0 && (
        <details>
          <summary>{warnings.length} note{warnings.length > 1 ? "s" : ""} about missing fields</summary>
          <ul>{warnings.slice(0, 40).map((w, i) => <li key={i}>{w}</li>)}</ul>
        </details>
      )}
    </>
  );
}
