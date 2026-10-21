import { useEffect, useState } from "react";
import type { UserProfile } from "./userProfile";
import DashboardSidebar from "./DashboardSidebar";
import ProjectCard, { type ProjectSummary } from "./ProjectCard";

interface DashboardProps {
  profile: UserProfile;
}

type ProjectsState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "loaded"; projects: ProjectSummary[] };

class ProjectRequestError extends Error {
  constructor(readonly statusCode: number) {
    super("Project request failed.");
  }
}

class InvalidProjectResponseError extends Error {}

let projectsRequestInFlight: Promise<ProjectSummary[]> | null = null;

function isProjectSummary(value: unknown): value is ProjectSummary {
  if (typeof value !== "object" || value === null) {
    return false;
  }

  const project = value as Record<string, unknown>;

  return (
    typeof project.id === "number" &&
    typeof project.name === "string" &&
    (typeof project.description === "string" ||
      project.description === null) &&
    typeof project.status === "string" &&
    typeof project.created_at === "string" &&
    Number.isFinite(Date.parse(project.created_at)) &&
    (typeof project.organization_name === "string" ||
      project.organization_name === null)
  );
}

function fetchProjects(): Promise<ProjectSummary[]> {
  if (!projectsRequestInFlight) {
    const request = (async () => {
      const response = await fetch("/api/projects/", {
        method: "GET",
        credentials: "include",
      });

      if (!response.ok) {
        throw new ProjectRequestError(response.status);
      }

      let responseBody: unknown;
      try {
        responseBody = await response.json();
      } catch {
        throw new InvalidProjectResponseError();
      }

      if (
        !Array.isArray(responseBody) ||
        !responseBody.every(isProjectSummary)
      ) {
        throw new InvalidProjectResponseError();
      }

      return responseBody;
    })().finally(() => {
      projectsRequestInFlight = null;
    });
    projectsRequestInFlight = request;
  }

  return projectsRequestInFlight;
}

function getProjectsErrorMessage(error: unknown): string {
  if (error instanceof ProjectRequestError) {
    if (error.statusCode === 401) {
      return "La sesión ya no permite consultar los proyectos. Recarga la aplicación e inicia sesión de nuevo.";
    }
    if (error.statusCode === 403) {
      return "No tienes permiso para consultar estos proyectos.";
    }
    return "No se pudieron cargar los proyectos. Inténtalo de nuevo más tarde.";
  }

  if (error instanceof InvalidProjectResponseError) {
    return "El servicio respondió con datos de proyectos que no se pudieron validar.";
  }

  return "No se pudo conectar con el servicio para cargar los proyectos. Comprueba la conexión e inténtalo de nuevo.";
}

function Dashboard({ profile }: DashboardProps) {
  const displayName = profile.display_name.trim() || profile.username;
  const [projectsState, setProjectsState] = useState<ProjectsState>({
    status: "loading",
  });
  const [retryCount, setRetryCount] = useState(0);

  useEffect(() => {
    let isMounted = true;
    setProjectsState({ status: "loading" });

    void fetchProjects()
      .then((projects) => {
        if (isMounted) {
          setProjectsState({ status: "loaded", projects });
        }
      })
      .catch((error: unknown) => {
        if (isMounted) {
          setProjectsState({
            status: "error",
            message: getProjectsErrorMessage(error),
          });
        }
      });

    return () => {
      isMounted = false;
    };
  }, [retryCount]);

  return (
    <div className="flex min-h-screen bg-canvas text-ink">
      <DashboardSidebar profile={profile} />
      <main className="flex min-w-0 flex-1 flex-col">
        <header className="mx-6 mt-6 mb-4 flex h-14 shrink-0 items-center justify-end rounded-md bg-graphite px-4 text-ivory lg:mx-8 lg:mt-8">
          <span
            aria-label="Notificaciones"
            className="grid size-10 place-items-center"
            role="img"
          >
            <svg
              aria-hidden="true"
              className="size-5"
              fill="none"
              stroke="currentColor"
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth="1.6"
              viewBox="0 0 24 24"
            >
              <path d="M18 9a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9" />
              <path d="M10 21h4" />
            </svg>
          </span>
        </header>
        <section
          aria-labelledby="dashboard-title"
          className="flex-1 px-8 py-10 lg:px-16 lg:py-12"
        >
          <div className="flex flex-wrap items-start justify-between gap-6">
            <div>
              <h1
                className="text-3xl font-semibold tracking-tight text-primary sm:text-4xl"
                id="dashboard-title"
              >
                Mis proyectos
              </h1>
              <p className="mt-3 text-sm leading-6 text-muted sm:text-base">
                Hola, {displayName}. Aquí tienes el resumen de tu trabajo.
              </p>
            </div>
            <span
              aria-disabled="true"
              aria-label="Nuevo proyecto, pendiente de implementar"
              className="inline-flex min-h-11 cursor-default items-center rounded-md bg-brass px-5 py-3 text-sm font-semibold text-graphite focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-brass-ink"
              role="button"
              tabIndex={0}
              title="Función pendiente de implementar"
            >
              + Nuevo proyecto
            </span>
          </div>
        </section>
        <section
          aria-label="Proyectos personales"
          aria-live={projectsState.status === "loading" ? "polite" : undefined}
          className="px-8 pb-12 lg:px-16"
        >
          {projectsState.status === "loading" && (
            <p className="text-sm text-muted" role="status">
              Cargando proyectos…
            </p>
          )}

          {projectsState.status === "error" && (
            <div
              className="rounded-md border border-error/30 bg-paper p-5"
              role="alert"
            >
              <p className="text-sm leading-6 text-error">
                {projectsState.message}
              </p>
              <button
                className="mt-4 min-h-10 rounded-sm border border-line px-4 py-2 text-sm font-medium text-primary hover:bg-mist/50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brass-ink"
                onClick={() => setRetryCount((count) => count + 1)}
                type="button"
              >
                Reintentar
              </button>
            </div>
          )}

          {projectsState.status === "loaded" &&
            (projectsState.projects.length === 0 ? (
              <p className="rounded-md border border-line bg-paper px-5 py-6 text-sm leading-6 text-muted">
                Todavía no tienes proyectos personales. Cuando la creación de
                proyectos esté habilitada, podrás crear el primero desde aquí.
              </p>
            ) : (
              <div className="grid grid-cols-1 items-stretch gap-5 md:grid-cols-2 xl:grid-cols-3">
                {projectsState.projects.map((project) => (
                  <ProjectCard key={project.id} project={project} />
                ))}
              </div>
            ))}
        </section>
      </main>
    </div>
  );
}

export default Dashboard;
