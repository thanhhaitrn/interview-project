import { NavLink } from "react-router-dom";

const LINKS = [
  { to: "/", label: "Home", end: true },
  { to: "/resume", label: "Resume" },
  { to: "/profiles", label: "Profiles" },
  { to: "/reviews", label: "Past Interviews" },
  { to: "/mock", label: "Mock Interview" },
];

export function NavBar() {
  return (
    <nav className="mx-auto mt-6 flex max-w-6xl items-center justify-between rounded-2xl bg-navy px-6 py-3 text-white shadow-lg ring-1 ring-white/5">
      <div className="flex items-center gap-2 font-bold tracking-tight">
        <span className="h-3 w-3 rounded-full bg-brand-500" />
        Candidly
      </div>
      <div className="flex items-center gap-1">
        {LINKS.map((link) => (
          <NavLink
            key={link.to}
            to={link.to}
            end={link.end}
            className={({ isActive }) =>
              `rounded-lg px-4 py-2 text-sm font-medium transition ${
                isActive
                  ? "bg-brand text-white"
                  : "text-white/70 hover:bg-white/10 hover:text-white"
              }`
            }
          >
            {link.label}
          </NavLink>
        ))}
      </div>
    </nav>
  );
}
