import type { UserProfile } from "./userProfile";
import DashboardSidebar from "./DashboardSidebar";

interface DashboardProps {
  profile: UserProfile;
}

function Dashboard({ profile }: DashboardProps) {
  const displayName = profile.display_name.trim() || profile.username;

  return (
    <div className="flex min-h-screen bg-canvas text-ink">
      <DashboardSidebar profile={profile} />
      <main className="flex min-w-0 flex-1 flex-col">
        <section
          aria-labelledby="dashboard-title"
          className="flex min-h-screen items-center px-8 py-12 lg:px-16"
        >
          <div>
            <p className="mb-4 font-mono text-xs tracking-[0.14em] text-muted">
              SESIÓN CONFIRMADA
            </p>
            <h1
              className="text-4xl font-semibold tracking-tight text-primary sm:text-5xl"
              id="dashboard-title"
            >
              Bienvenido, {displayName}
            </h1>
          </div>
        </section>
      </main>
    </div>
  );
}

export default Dashboard;
