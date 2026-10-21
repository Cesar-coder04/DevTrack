import type { UserProfile } from "./userProfile";

interface DashboardSidebarProps {
  profile: UserProfile;
}

const primaryNavigation = [
  { label: "Inicio", icon: "home", active: true },
  { label: "Mis proyectos", icon: "projects", active: false },
  { label: "Mis tareas", icon: "tasks", active: false },
  { label: "Incidencias", icon: "issues", active: false },
  { label: "Organizaciones", icon: "organizations", active: false },
] as const;

function NavigationIcon({ name }: { name: string }) {
  const paths: Record<string, React.ReactNode> = {
    home: (
      <>
        <path d="m3 10 9-7 9 7v10a1 1 0 0 1-1 1h-5v-6h-6v6H4a1 1 0 0 1-1-1z" />
      </>
    ),
    projects: (
      <>
        <rect x="3" y="4" width="18" height="16" rx="1" />
        <path d="M7 8h10M7 12h6M7 16h10" />
      </>
    ),
    tasks: (
      <>
        <rect x="4" y="3" width="16" height="18" rx="1" />
        <path d="m7 9 1.5 1.5L11 8m2 2h4m-10 5 1.5 1.5L11 14m2 2h4" />
      </>
    ),
    issues: (
      <>
        <path d="M12 3 2.8 20h18.4z" />
        <path d="M12 9v4m0 3h.01" />
      </>
    ),
    organizations: (
      <>
        <rect x="3" y="7" width="18" height="14" rx="1" />
        <path d="M8 7V4h8v3M3 12h18m-11 0v2h4v-2" />
      </>
    ),
    settings: (
      <>
        <circle cx="12" cy="12" r="3" />
        <path d="m19.4 15 .1.1 1.4 1.1-1.4 2.4-1.7-.7a8 8 0 0 1-1.5.9l-.3 1.8h-2.8l-.3-1.8a8 8 0 0 1-1.5-.9l-1.7.7-1.4-2.4 1.4-1.1a7 7 0 0 1 0-1.8l-1.4-1.1 1.4-2.4 1.7.7a8 8 0 0 1 1.5-.9l.3-1.8h2.8l.3 1.8a8 8 0 0 1 1.5.9l1.7-.7 1.4 2.4-1.4 1.1a7 7 0 0 1 0 1.7Z" />
      </>
    ),
  };

  return (
    <svg
      aria-hidden="true"
      className="size-5 shrink-0"
      fill="none"
      stroke="currentColor"
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth="1.5"
      viewBox="0 0 24 24"
    >
      {paths[name]}
    </svg>
  );
}

function DashboardSidebar({ profile }: DashboardSidebarProps) {
  const displayName =
    profile.display_name.trim() || profile.username.trim();
  const nameParts = displayName.split(/\s+/).filter(Boolean);
  const initials =
    nameParts.length > 1
      ? nameParts
          .slice(0, 2)
          .map((part) => part[0])
          .join("")
      : (nameParts[0] ?? "").slice(0, 2);

  return (
    <aside className="flex h-screen w-[220px] shrink-0 flex-col bg-graphite text-ivory">
      <header className="border-b border-ivory/10 px-5 py-6">
        <div className="flex items-center gap-3">
          <span className="grid size-9 shrink-0 place-items-center rounded-sm bg-brass">
            <svg
              aria-hidden="true"
              className="size-5 text-graphite"
              fill="none"
              stroke="currentColor"
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth="1.5"
              viewBox="0 0 24 24"
            >
              <path d="m12 3 8 4-8 4-8-4 8-4Z" />
              <path d="m4 12 8 4 8-4M4 17l8 4 8-4" />
            </svg>
          </span>
          <p className="text-lg font-semibold tracking-tight">DevTrack</p>
        </div>
        <p className="mt-1 font-mono text-[10px] tracking-[0.14em] text-ivory/55">
          PROJECT WORKSPACE
        </p>
      </header>

      <nav aria-label="Navegación principal" className="px-3 py-5">
        <ul className="space-y-1">
          {primaryNavigation.map((item) => (
            <li key={item.label}>
              {item.active ? (
                <a
                  aria-current="page"
                  className="relative flex min-h-11 items-center gap-3 rounded-sm bg-ivory/10 px-3 text-sm font-medium text-ivory before:absolute before:inset-y-1 before:left-0 before:w-[3px] before:bg-brass focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brass"
                  href="/"
                >
                  <NavigationIcon name={item.icon} />
                  <span>{item.label}</span>
                </a>
              ) : (
                <span
                  aria-disabled="true"
                  className="flex min-h-11 cursor-default items-center gap-3 rounded-sm px-3 text-sm text-ivory/40"
                >
                  <NavigationIcon name={item.icon} />
                  <span>{item.label}</span>
                </span>
              )}
            </li>
          ))}
        </ul>
      </nav>

      <div className="mt-auto px-3">
        <div className="border-t border-ivory/10 py-4">
          <span
            aria-disabled="true"
            className="flex min-h-11 cursor-default items-center gap-3 rounded-sm px-3 text-sm text-ivory/40"
          >
            <NavigationIcon name="settings" />
            <span>Ajustes</span>
          </span>
        </div>
      </div>

      <footer className="border-t border-ivory/10 px-5 py-4">
        <div className="flex min-w-0 items-center gap-3">
          <div
            aria-hidden="true"
            className="grid size-9 shrink-0 place-items-center rounded-full bg-brass text-sm font-semibold uppercase text-graphite"
          >
            {initials}
          </div>
          <div className="min-w-0">
            <p
              className="truncate text-sm font-medium text-ivory"
              title={displayName}
            >
              {displayName}
            </p>
            <p
              className="mt-1 truncate font-mono text-xs text-ivory/55"
              title={profile.username}
            >
              {profile.username}
            </p>
          </div>
        </div>
      </footer>
    </aside>
  );
}

export default DashboardSidebar;
