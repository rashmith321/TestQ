export default function UrlForm({ value, onChange, onSubmit, busy }) {
  return (
    <form
      className="url-form"
      onSubmit={(e) => {
        e.preventDefault();
        if (!busy) onSubmit();
      }}
    >
      <label htmlFor="profile-url">Profile URL</label>
      <div className="url-row">
        <input
          id="profile-url"
          type="text"
          inputMode="url"
          autoComplete="off"
          spellCheck="false"
          placeholder="https://leetcode.com/u/username/"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          disabled={busy}
        />
        <button className="btn" type="submit" disabled={busy}>
          {busy ? "Analyzing…" : "Analyze profile"}
        </button>
      </div>
    </form>
  );
}
