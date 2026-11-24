export default function ProgressPanel({ job }) {
  return (
    <section className="progress" aria-live="polite">
      <div className="progress-top">
        <span>{job.stage || "Starting"}</span>
        <span className="num">{job.progress}%</span>
      </div>
      <div className="track" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={job.progress}>
        <div className="fill" style={{ width: `${job.progress}%` }} />
      </div>
      {job.log?.length > 1 && (
        <ol className="log">
          {job.log.slice(-5).map((line, i) => <li key={i}>{line}</li>)}
        </ol>
      )}
    </section>
  );
}
