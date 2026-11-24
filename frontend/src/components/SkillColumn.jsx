export default function SkillColumn({ title, items }) {
  const max = Math.max(1, ...items.map((s) => s.problems_solved || 0));
  return (
    <div className="skill-col">
      <h3>
        {title} <span className="muted num">{items.length}</span>
      </h3>
      {items.length === 0 ? (
        <p className="muted small">No skills listed in this section.</p>
      ) : (
        <ul className="skills">
          {items.map((s) => (
            <li key={s.skill_slug || s.skill_name}>
              <div className="skill-line">
                <span>{s.skill_name}</span>
                <span className="num muted">{s.problems_solved ?? "–"}</span>
              </div>
              <div className="skill-bar">
                <div style={{ width: `${((s.problems_solved || 0) / max) * 100}%` }} />
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
