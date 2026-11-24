import { useMemo, useState } from "react";

function formatDate(iso) {
  if (!iso) return "–";
  const d = new Date(iso);
  return d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

export default function ActivityTable({ records }) {
  const [filter, setFilter] = useState("all");
  const statuses = useMemo(() => [...new Set(records.map((r) => r.status).filter(Boolean))], [records]);
  const shown = filter === "all" ? records : records.filter((r) => r.status === filter);

  if (records.length === 0) {
    return <p className="muted">LeetCode shows no recent submissions for this profile.</p>;
  }

  return (
    <>
      <div className="table-tools">
        <label htmlFor="status-filter">Status</label>
        <select id="status-filter" value={filter} onChange={(e) => setFilter(e.target.value)}>
          <option value="all">All ({records.length})</option>
          {statuses.map((s) => (
            <option key={s} value={s}>
              {s} ({records.filter((r) => r.status === s).length})
            </option>
          ))}
        </select>
      </div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th scope="col">Problem</th>
              <th scope="col">Difficulty</th>
              <th scope="col">Status</th>
              <th scope="col">Language</th>
              <th scope="col">Submitted</th>
              <th scope="col">Submission ID</th>
            </tr>
          </thead>
          <tbody>
            {shown.map((r, i) => (
              <tr key={`${r.submission_id || r.problem_slug}-${r.submission_timestamp}-${i}`}>
                <td>{r.problem_url ? <a href={r.problem_url} target="_blank" rel="noreferrer">{r.problem_name || r.problem_slug}</a> : r.problem_name}</td>
                <td>{r.difficulty ? <span className={`diff diff-${r.difficulty.toLowerCase()}`}>{r.difficulty}</span> : <span className="muted">–</span>}</td>
                <td className={r.status === "Accepted" ? "ok" : "bad"}>{r.status || "–"}</td>
                <td>{r.language || <span className="muted">–</span>}</td>
                <td className="nowrap">{formatDate(r.submission_date)}</td>
                <td className="mono">{r.submission_id || <span className="muted">–</span>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
