export default function StatusBanner({ tone = "info", title, children }) {
  return (
    <div className={`banner banner-${tone}`} role={tone === "error" ? "alert" : "status"}>
      <strong className="banner-title">{title}</strong>
      <div>{children}</div>
    </div>
  );
}
