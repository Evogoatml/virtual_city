import Link from "next/link";

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const links = [
    ["/", "Overview"],
    ["/chat", "Chat"],
    ["/actions", "Actions"],
    ["/approvals", "Approvals"],
    ["/analytics", "Analytics"],
    ["/tasks", "Tasks"],
    ["/settings", "Settings"],
  ];
  return (
    <div style={{ display: "flex", minHeight: "100vh" }}>
      <nav
        style={{
          width: 180,
          borderRight: "1px solid #222a3d",
          padding: "1rem 0.6rem",
          background: "#0a0c14",
        }}
      >
        <div style={{ color: "#39ff14", fontWeight: 700, letterSpacing: 2, padding: "0.4rem 0.5rem" }}>
          EFFATA PICKS
        </div>
        {links.map(([href, label]) => (
          <Link
            key={href}
            href={href}
            style={{
              display: "block",
              padding: "0.45rem 0.5rem",
              color: "#c7d2e0",
              borderRadius: 6,
            }}
          >
            {label}
          </Link>
        ))}
      </nav>
      <main style={{ flex: 1, padding: "1.2rem", overflow: "auto" }}>{children}</main>
    </div>
  );
}
