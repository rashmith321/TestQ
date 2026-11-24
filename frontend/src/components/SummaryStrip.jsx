export default function SummaryStrip({ result }) {
  const m = result.metadata;
  const rows = [
    ["Fundamental skills", m.skills_by_category.fundamentals],
    ["Intermediate skills", m.skills_by_category.intermediate],
    ["Advanced skills", m.skills_by_category.advanced],
    ["Total skills", m.total_skills],
    ["Activity records", m.total_activity_records],
    ["Batches requested", m.pages_processed],
  ];
  const counts = { Easy: 0, Medium: 0, Hard: 0, Unknown: 0 };
  result.recent_activity.forEach((r) => (counts[r.difficulty || "Unknown"] += 1));
  const total = result.recent_activity.length || 1;

  return (
    <section className="summary">
      <dl>
        {rows.map(([label, value]) => (
          <div key={label}>
            <dt>{label}</dt>
            <dd className="num">{value}</dd>
          </div>
        ))}
      </dl>
      {result.recent_activity.length > 0 && (
        <figure className="mix">
          <div className="mix-bar" role="img" aria-label={`Activity by difficulty: ${Object.entries(counts).map(([k, v]) => `${k} ${v}`).join(", ")}`}>
            {Object.entries(counts).filter(([, v]) => v).map(([k, v]) => (
              <span key={k} className={`seg seg-${k.toLowerCase()}`} style={{ flexGrow: v / total }} />
            ))}
          </div>
          <figcaption>
            {Object.entries(counts).filter(([, v]) => v).map(([k, v]) => (
              <span key={k} className="legend"><i className={`dot seg-${k.toLowerCase()}`} />{k} {v}</span>
            ))}
          </figcaption>
        </figure>
      )}
    </section>
  );
}
