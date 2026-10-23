import { useEffect, useRef, useState, type FormEvent } from "react";
import type { UserProfile } from "./userProfile";
import DashboardSidebar from "./DashboardSidebar";
import { type DashboardView } from "./DashboardSidebar";
import ProjectCard, { type ProjectSummary } from "./ProjectCard";
import ProjectDetail from "./ProjectDetail";
import MyTasks from "./MyTasks";
import Issues, { type Issue } from "./Issues";
import DashboardHome from "./DashboardHome";
import WorkItemDetail from "./WorkItemDetail";
import type { MyTask } from "./MyTasks";

interface DashboardProps {
  profile: UserProfile;
}

type ProjectsState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "loaded"; projects: ProjectSummary[] };

interface OrganizationSummary {
  id: number;
  name: string;
  slug: string;
  description: string | null;
  status: string;
  created_at: string;
}

type OrganizationsState =
  | { status: "not_loaded" | "loading" }
  | { status: "error"; message: string }
  | { status: "loaded"; organizations: OrganizationSummary[] };

type ProjectScope = "personal" | "organization";
type ProjectTypeFilter = "all" | ProjectScope;

interface ProjectFilters {
  name: string;
  type: ProjectTypeFilter;
  organizationId: string;
}

const emptyProjectFilters: ProjectFilters = {
  name: "",
  type: "all",
  organizationId: "",
};

class ProjectRequestError extends Error {
  constructor(readonly statusCode: number) {
    super("Project request failed.");
  }
}

class InvalidProjectResponseError extends Error {}

class OrganizationRequestError extends Error {
  constructor(readonly statusCode: number) {
    super("Organization request failed.");
  }
}

class CreateProjectRequestError extends Error {
  constructor(readonly statusCode: number) {
    super("Project creation failed.");
  }
}

let projectsRequestInFlight: Promise<ProjectSummary[]> | null = null;
let organizationsRequestInFlight: Promise<OrganizationSummary[]> | null = null;

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
      project.organization_name === null) &&
    (project.organization_id === undefined ||
      project.organization_id === null ||
      (typeof project.organization_id === "number" &&
        Number.isSafeInteger(project.organization_id)))
  );
}

function isOrganizationSummary(value: unknown): value is OrganizationSummary {
  if (typeof value !== "object" || value === null) {
    return false;
  }

  const organization = value as Record<string, unknown>;

  return (
    typeof organization.id === "number" &&
    typeof organization.name === "string" &&
    typeof organization.slug === "string" &&
    (typeof organization.description === "string" ||
      organization.description === null) &&
    typeof organization.status === "string" &&
    typeof organization.created_at === "string" &&
    Number.isFinite(Date.parse(organization.created_at))
  );
}

function isOrganizationProject(
  value: unknown,
  organizationId: number,
): value is Record<string, unknown> & {
  id: number;
  name: string;
  description: string | null;
  status: string;
  organization_id: number;
  visibility: string;
  created_at: string;
  archived_at: string | null;
} {
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
    project.organization_id === organizationId &&
    typeof project.visibility === "string" &&
    typeof project.created_at === "string" &&
    Number.isFinite(Date.parse(project.created_at)) &&
    (typeof project.archived_at === "string" ||
      project.archived_at === null)
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

      return responseBody.map((project) => ({
        ...project,
        organization_id: null,
      }));
    })().finally(() => {
      projectsRequestInFlight = null;
    });
    projectsRequestInFlight = request;
  }

  return projectsRequestInFlight;
}

function fetchOrganizations(): Promise<OrganizationSummary[]> {
  if (!organizationsRequestInFlight) {
    const request = (async () => {
      const response = await fetch("/api/organizations/", {
        method: "GET",
        credentials: "include",
      });

      if (!response.ok) {
        throw new OrganizationRequestError(response.status);
      }

      let responseBody: unknown;
      try {
        responseBody = await response.json();
      } catch {
        throw new InvalidProjectResponseError();
      }

      if (
        !Array.isArray(responseBody) ||
        !responseBody.every(isOrganizationSummary)
      ) {
        throw new InvalidProjectResponseError();
      }

      return responseBody;
    })().finally(() => {
      organizationsRequestInFlight = null;
    });
    organizationsRequestInFlight = request;
  }

  return organizationsRequestInFlight;
}

async function fetchOrganizationProjects(
  organization: OrganizationSummary,
): Promise<ProjectSummary[]> {
  const response = await fetch(
    `/api/organizations/${organization.id}/projects/`,
    {
      method: "GET",
      credentials: "include",
    },
  );

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
    !responseBody.every((project) =>
      isOrganizationProject(project, organization.id),
    )
  ) {
    throw new InvalidProjectResponseError();
  }

  return responseBody
    .filter((project) => project.archived_at === null)
    .map((project) => ({
      id: project.id,
      name: project.name,
      description: project.description,
      status: project.status,
      created_at: project.created_at,
      organization_id: organization.id,
      organization_name: organization.name,
    }));
}

async function fetchDashboardProjects(): Promise<{
  organizations: OrganizationSummary[];
  projects: ProjectSummary[];
}> {
  const [personalProjects, organizations] = await Promise.all([
    fetchProjects(),
    fetchOrganizations(),
  ]);
  const organizationProjects = await Promise.all(
    organizations.map(fetchOrganizationProjects),
  );
  const uniqueProjects = new Map<number, ProjectSummary>();

  for (const project of [...personalProjects, ...organizationProjects.flat()]) {
    uniqueProjects.set(project.id, project);
  }

  return {
    organizations,
    projects: [...uniqueProjects.values()],
  };
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
    return "El servicio respondió con datos de proyectos u organizaciones que no se pudieron validar.";
  }

  return "No se pudo conectar con el servicio para cargar los proyectos. Comprueba la conexión e inténtalo de nuevo.";
}

function getOrganizationsErrorMessage(error: unknown): string {
  if (error instanceof OrganizationRequestError) {
    if (error.statusCode === 401) {
      return "Tu sesión ya no permite consultar las organizaciones. Inicia sesión de nuevo.";
    }
    if (error.statusCode === 403) {
      return "No tienes permiso para consultar tus organizaciones.";
    }
    return "No se pudieron cargar las organizaciones. Inténtalo de nuevo más tarde.";
  }

  if (error instanceof InvalidProjectResponseError) {
    return "El servicio respondió con datos de organizaciones que no se pudieron validar.";
  }

  return "No se pudo conectar con el servicio para cargar las organizaciones. Comprueba la conexión e inténtalo de nuevo.";
}

function getCreateProjectErrorMessage(error: unknown): string {
  if (error instanceof CreateProjectRequestError) {
    if (error.statusCode === 401) {
      return "Tu sesión ha caducado. Inicia sesión de nuevo para crear un proyecto.";
    }
    if (error.statusCode === 403) {
      return "No tienes permiso para crear este proyecto.";
    }
    if (error.statusCode === 409) {
      return "Ya existe un proyecto no archivado ni eliminado con ese nombre en este ámbito. Prueba con otro nombre.";
    }
    if (error.statusCode === 422) {
      return "Revisa el nombre y la descripción e inténtalo de nuevo.";
    }
    return "No se pudo crear el proyecto. Inténtalo de nuevo más tarde.";
  }

  if (error instanceof InvalidProjectResponseError) {
    return "El servicio creó el proyecto, pero la respuesta no se pudo validar.";
  }

  return "No se pudo conectar con el servicio para crear el proyecto. Comprueba la conexión e inténtalo de nuevo.";
}

function Dashboard({ profile }: DashboardProps) {
  const displayName = profile.display_name.trim() || profile.username;
  const [projectsState, setProjectsState] = useState<ProjectsState>({
    status: "loading",
  });
  const [organizationsState, setOrganizationsState] =
    useState<OrganizationsState>({ status: "not_loaded" });
  const [retryCount, setRetryCount] = useState(0);
  const [isCreateFormOpen, setIsCreateFormOpen] = useState(false);
  const [projectScope, setProjectScope] = useState<ProjectScope>("personal");
  const [selectedOrganizationId, setSelectedOrganizationId] = useState("");
  const [isCreatingProject, setIsCreatingProject] = useState(false);
  const [createProjectError, setCreateProjectError] = useState<string | null>(
    null,
  );
  const [createProjectNotice, setCreateProjectNotice] = useState<
    string | null
  >(null);
  const [selectedProject, setSelectedProject] =
    useState<ProjectSummary | null>(null);
  const [activeView, setActiveView] = useState<DashboardView>("home");
  const [projectFilters, setProjectFilters] =
    useState<ProjectFilters>(emptyProjectFilters);
  const [selectedTask, setSelectedTask] = useState<MyTask | null>(null);
  const [initialIssue, setInitialIssue] = useState<Issue | null>(null);
  const [detailReturnView, setDetailReturnView] = useState<DashboardView>("home");
  const mainRef = useRef<HTMLElement | null>(null);
  const dashboardScrollTop = useRef(0);
  const createRequestInFlight = useRef(false);

  const projectOrganizationOptions =
    projectsState.status === "loaded"
      ? [...
          new Map(
            projectsState.projects
              .filter(
                (project) =>
                  project.organization_id !== null &&
                  project.organization_name !== null,
              )
              .map((project) => [
                project.organization_id as number,
                project.organization_name as string,
              ]),
          ).entries(),
        ].sort((left, right) => left[1].localeCompare(right[1], "es"))
      : [];
  const filteredProjects =
    projectsState.status === "loaded"
      ? projectsState.projects.filter((project) => {
          const searchName = projectFilters.name.trim().toLocaleLowerCase();
          const matchesName = project.name
            .toLocaleLowerCase()
            .includes(searchName);
          const matchesType =
            projectFilters.type === "all" ||
            (projectFilters.type === "personal"
              ? project.organization_id === null
              : project.organization_id !== null);
          const matchesOrganization =
            !projectFilters.organizationId ||
            String(project.organization_id) === projectFilters.organizationId;
          return matchesName && matchesType && matchesOrganization;
        })
      : [];
  const hasProjectFilters =
    projectFilters.name.trim() !== "" ||
    projectFilters.type !== "all" ||
    projectFilters.organizationId !== "";

  useEffect(() => {
    let isMounted = true;
    setProjectsState({ status: "loading" });
    setOrganizationsState({ status: "loading" });

    void fetchDashboardProjects()
      .then(({ projects, organizations }) => {
        if (isMounted) {
          setProjectsState({ status: "loaded", projects });
          setOrganizationsState({ status: "loaded", organizations });
        }
      })
      .catch((error: unknown) => {
        if (isMounted) {
          setProjectsState({
            status: "error",
            message: getProjectsErrorMessage(error),
          });
          setOrganizationsState({
            status: "error",
            message: getOrganizationsErrorMessage(error),
          });
        }
      });

    return () => {
      isMounted = false;
    };
  }, [retryCount]);

  useEffect(() => {
    mainRef.current?.scrollTo({
      top: selectedProject ? 0 : dashboardScrollTop.current,
    });
  }, [selectedProject]);

  function loadOrganizations() {
    setOrganizationsState({ status: "loading" });
    void fetchOrganizations()
      .then((organizations) => {
        setOrganizationsState({ status: "loaded", organizations });
      })
      .catch((error: unknown) => {
        setOrganizationsState({
          status: "error",
          message: getOrganizationsErrorMessage(error),
        });
      });
  }

  async function handleCreateProject(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (createRequestInFlight.current || projectsState.status !== "loaded") {
      return;
    }

    const formData = new FormData(event.currentTarget);
    const name = String(formData.get("name") ?? "");
    const description = String(formData.get("description") ?? "");

    if (!name.trim()) {
      setCreateProjectError("El nombre del proyecto no puede estar vacío.");
      return;
    }
    if (name.length > 100) {
      setCreateProjectError("El nombre no puede superar los 100 caracteres.");
      return;
    }
    if (description.length > 500) {
      setCreateProjectError(
        "La descripción no puede superar los 500 caracteres.",
      );
      return;
    }

    let selectedOrganization: OrganizationSummary | null = null;
    if (projectScope === "organization") {
      if (organizationsState.status !== "loaded") {
        setCreateProjectError(
          "Espera a que se carguen las organizaciones antes de continuar.",
        );
        return;
      }

      selectedOrganization =
        organizationsState.organizations.find(
          (organization) =>
            String(organization.id) === selectedOrganizationId,
        ) ?? null;
      if (!selectedOrganization) {
        setCreateProjectError("Selecciona una organización válida.");
        return;
      }
    }

    createRequestInFlight.current = true;
    setIsCreatingProject(true);
    setCreateProjectError(null);
    setCreateProjectNotice(null);

    try {
      const endpoint = selectedOrganization
        ? `/api/organizations/${selectedOrganization.id}/projects/`
        : "/api/projects/";
      const response = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({
          name,
          description: description.trim() ? description : null,
        }),
      });

      if (response.status !== 201) {
        throw new CreateProjectRequestError(response.status);
      }

      let responseBody: unknown;
      try {
        responseBody = await response.json();
      } catch {
        throw new InvalidProjectResponseError();
      }

      let createdProject: ProjectSummary;
      if (selectedOrganization) {
        if (!isOrganizationProject(responseBody, selectedOrganization.id)) {
          throw new InvalidProjectResponseError();
        }
        createdProject = {
          id: responseBody.id,
          name: responseBody.name,
          description: responseBody.description,
          status: responseBody.status,
          created_at: responseBody.created_at,
          organization_id: selectedOrganization.id,
          organization_name: selectedOrganization.name,
        };
      } else {
        if (!isProjectSummary(responseBody)) {
          throw new InvalidProjectResponseError();
        }
        createdProject = {
          ...responseBody,
          organization_id: null,
        };
      }

      setProjectsState((currentState) => {
        if (currentState.status !== "loaded") {
          return currentState;
        }

        return {
          status: "loaded",
          projects: currentState.projects.some(
            (project) => project.id === createdProject.id,
          )
            ? currentState.projects
            : [createdProject, ...currentState.projects],
        };
      });
      setIsCreateFormOpen(false);
      setProjectScope("personal");
      setSelectedOrganizationId("");
      setProjectFilters(emptyProjectFilters);
      setCreateProjectNotice("Proyecto creado correctamente.");
    } catch (error: unknown) {
      setCreateProjectError(getCreateProjectErrorMessage(error));
    } finally {
      createRequestInFlight.current = false;
      setIsCreatingProject(false);
    }
  }

  return (
    <div className="flex h-screen overflow-hidden bg-canvas text-ink">
      <DashboardSidebar
        activeView={activeView}
        onNavigate={(view) => {
          setSelectedProject(null);
          setSelectedTask(null);
          setInitialIssue(null);
          setActiveView(view);
          if (view === "home") setRetryCount((count) => count + 1);
        }}
        profile={profile}
      />
      <main
        className="flex min-h-0 min-w-0 flex-1 flex-col overflow-y-auto"
        ref={mainRef}
      >
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
        <>
            <div hidden={activeView !== "home" || Boolean(selectedProject || selectedTask)}>

              <DashboardHome
                active={activeView === "home" && !selectedProject && !selectedTask}
                onOpenIssue={(issue) => {
                  setInitialIssue(issue);
                  setActiveView("issues");
                }}
                onOpenTask={(task) => {
                  setDetailReturnView("home");
                  setSelectedTask(task);
                }}
                onRetryProjects={() => setRetryCount((count) => count + 1)}
                onSelectProject={(project) => {
                  dashboardScrollTop.current = mainRef.current?.scrollTop ?? 0;
                  setSelectedProject(project);
                }}
                onViewAllIssues={() => {
                  setInitialIssue(null);
                  setActiveView("issues");
                }}
                onViewAllProjects={() => setActiveView("projects")}
                onViewAllTasks={() => setActiveView("tasks")}
                projects={projectsState.status === "loaded" ? projectsState.projects : []}
                projectsError={projectsState.status === "error" ? projectsState.message : undefined}
                projectsStatus={projectsState.status}
                organizations={organizationsState.status === "loaded" ? organizationsState.organizations : []}
                organizationsStatus={organizationsState.status === "loaded" ? "loaded" : organizationsState.status === "error" ? "error" : "loading"}
              />
            </div>
            <div hidden={activeView !== "tasks" || Boolean(selectedProject || selectedTask)}>
              <MyTasks
                active={activeView === "tasks" && !selectedProject && !selectedTask}
                onOpenTask={(task) => {
                  setDetailReturnView("tasks");
                  setSelectedTask(task);
                }}
                projects={projectsState.status === "loaded" ? projectsState.projects : []}
              />
            </div>
            <div hidden={activeView !== "issues" || Boolean(selectedProject || selectedTask)}>
              <Issues
                active={activeView === "issues" && !selectedProject && !selectedTask}
                initialIssue={initialIssue}
              />
            </div>
            <div hidden={activeView !== "projects" || Boolean(selectedProject || selectedTask)}>
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
                Hola, {displayName}. Consulta y crea tus proyectos personales y de organizaciones.
              </p>
            </div>
            <button
              className="inline-flex min-h-11 items-center rounded-md bg-brass px-5 py-3 text-sm font-semibold text-graphite hover:bg-brass/90 focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-brass-ink disabled:cursor-not-allowed disabled:opacity-60"
              disabled={projectsState.status !== "loaded"}
              onClick={() => {
                setCreateProjectError(null);
                setCreateProjectNotice(null);
                setProjectScope("personal");
                setSelectedOrganizationId("");
                setIsCreateFormOpen(true);
              }}
              type="button"
            >
              + Nuevo proyecto
            </button>
          </div>
        </section>
        {projectsState.status === "loaded" && (
          <section
            aria-label="Filtros de proyectos"
            className="mx-8 mb-8 grid gap-3 rounded-md border border-line bg-paper p-4 sm:grid-cols-2 xl:mx-16 xl:grid-cols-4"
          >
            <label className="grid gap-1 text-xs font-medium text-muted">
              Buscar por nombre
              <input
                autoComplete="off"
                className="min-h-10 rounded-sm border border-line bg-paper px-3 text-sm text-primary"
                onChange={(event) =>
                  setProjectFilters((current) => ({
                    ...current,
                    name: event.target.value,
                  }))
                }
                placeholder="Nombre del proyecto"
                type="search"
                value={projectFilters.name}
              />
            </label>
            <label className="grid gap-1 text-xs font-medium text-muted">
              Tipo de proyecto
              <select
                className="min-h-10 rounded-sm border border-line bg-paper px-3 text-sm text-primary"
                onChange={(event) => {
                  const type = event.target.value as ProjectTypeFilter;
                  setProjectFilters((current) => ({
                    ...current,
                    type,
                    organizationId:
                      type === "personal" ? "" : current.organizationId,
                  }));
                }}
                value={projectFilters.type}
              >
                <option value="all">Todos</option>
                <option value="personal">Personales</option>
                <option value="organization">De organización</option>
              </select>
            </label>
            {projectOrganizationOptions.length > 0 &&
              projectFilters.type !== "personal" && (
                <label className="grid gap-1 text-xs font-medium text-muted">
                  Organización
                  <select
                    className="min-h-10 rounded-sm border border-line bg-paper px-3 text-sm text-primary"
                    onChange={(event) =>
                      setProjectFilters((current) => ({
                        ...current,
                        organizationId: event.target.value,
                      }))
                    }
                    value={projectFilters.organizationId}
                  >
                    <option value="">Todas</option>
                    {projectOrganizationOptions.map(([id, name]) => (
                      <option key={id} value={id}>
                        {name}
                      </option>
                    ))}
                  </select>
                </label>
              )}
            <div className="flex items-end">
              <button
                className="min-h-10 rounded-sm border border-line px-4 py-2 text-sm font-medium text-primary hover:bg-mist/50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brass-ink disabled:cursor-not-allowed disabled:opacity-50"
                disabled={!hasProjectFilters}
                onClick={() => setProjectFilters(emptyProjectFilters)}
                type="button"
              >
                Limpiar filtros
              </button>
            </div>
          </section>
        )}
        {isCreateFormOpen && projectsState.status === "loaded" && (
          <section
            aria-labelledby="create-project-title"
            className="mx-8 mb-8 rounded-md border border-line bg-paper p-5 lg:mx-16"
          >
            <div className="flex items-start justify-between gap-4">
              <div>
                <h2
                  className="text-lg font-semibold text-primary"
                  id="create-project-title"
                >
                  Crear proyecto
                </h2>
                <p className="mt-2 text-sm leading-6 text-muted">
                  El nombre es obligatorio. La descripción es opcional.
                </p>
              </div>
              <button
                className="min-h-10 shrink-0 rounded-sm border border-line px-4 py-2 text-sm font-medium text-primary hover:bg-mist/50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brass-ink disabled:cursor-not-allowed disabled:opacity-60"
                disabled={isCreatingProject}
                onClick={() => setIsCreateFormOpen(false)}
                type="button"
              >
                Cancelar
              </button>
            </div>
            <form
              aria-busy={isCreatingProject}
              className="mt-5 grid gap-4"
              onSubmit={(event) => void handleCreateProject(event)}
            >
              <div className="grid gap-2">
                <label
                  className="text-sm font-medium text-primary"
                  htmlFor="project-name"
                >
                  Nombre
                </label>
                <input
                  autoComplete="off"
                  className="min-h-11 w-full rounded-md border border-steel/50 bg-paper px-4 py-2 text-sm text-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brass-ink disabled:cursor-not-allowed disabled:opacity-60"
                  disabled={isCreatingProject}
                  id="project-name"
                  maxLength={100}
                  name="name"
                  required
                />
              </div>
              <fieldset className="grid gap-3">
                <legend className="text-sm font-medium text-primary">
                  Ámbito del proyecto
                </legend>
                <div className="flex flex-wrap gap-4">
                  <label className="inline-flex min-h-10 items-center gap-2 text-sm text-primary">
                    <input
                      checked={projectScope === "personal"}
                      disabled={isCreatingProject}
                      name="project-scope"
                      onChange={() => {
                        setProjectScope("personal");
                        setCreateProjectError(null);
                      }}
                      type="radio"
                    />
                    Personal
                  </label>
                  <label className="inline-flex min-h-10 items-center gap-2 text-sm text-primary">
                    <input
                      checked={projectScope === "organization"}
                      disabled={isCreatingProject}
                      name="project-scope"
                      onChange={() => {
                        setProjectScope("organization");
                        setCreateProjectError(null);
                        if (organizationsState.status === "not_loaded") {
                          loadOrganizations();
                        }
                      }}
                      type="radio"
                    />
                    Organización
                  </label>
                </div>
              </fieldset>
              {projectScope === "organization" && (
                <div className="grid gap-2">
                  <label
                    className="text-sm font-medium text-primary"
                    htmlFor="project-organization"
                  >
                    Organización
                  </label>
                  {organizationsState.status === "loading" && (
                    <p className="text-sm text-muted" role="status">
                      Cargando organizaciones…
                    </p>
                  )}
                  {organizationsState.status === "error" && (
                    <div className="grid gap-3" role="alert">
                      <p className="text-sm leading-6 text-error">
                        {organizationsState.message}
                      </p>
                      <button
                        className="min-h-10 w-fit rounded-sm border border-line px-4 py-2 text-sm font-medium text-primary hover:bg-mist/50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brass-ink"
                        onClick={loadOrganizations}
                        type="button"
                      >
                        Reintentar carga de organizaciones
                      </button>
                    </div>
                  )}
                  {organizationsState.status === "loaded" &&
                    (organizationsState.organizations.length > 0 ? (
                      <select
                        className="min-h-11 w-full rounded-md border border-steel/50 bg-paper px-4 py-2 text-sm text-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brass-ink disabled:cursor-not-allowed disabled:opacity-60"
                        disabled={isCreatingProject}
                        id="project-organization"
                        onChange={(event) =>
                          setSelectedOrganizationId(event.target.value)
                        }
                        required
                        value={selectedOrganizationId}
                      >
                        <option value="">Selecciona una organización</option>
                        {organizationsState.organizations.map((organization) => (
                          <option
                            key={organization.id}
                            value={organization.id}
                          >
                            {organization.name}
                          </option>
                        ))}
                      </select>
                    ) : (
                      <p className="text-sm leading-6 text-muted">
                        No perteneces a ninguna organización disponible para
                        crear proyectos.
                      </p>
                    ))}
                </div>
              )}
              <div className="grid gap-2">
                <label
                  className="text-sm font-medium text-primary"
                  htmlFor="project-description"
                >
                  Descripción <span className="font-normal text-muted">(opcional)</span>
                </label>
                <textarea
                  className="min-h-24 w-full resize-y rounded-md border border-steel/50 bg-paper px-4 py-3 text-sm leading-6 text-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brass-ink disabled:cursor-not-allowed disabled:opacity-60"
                  disabled={isCreatingProject}
                  id="project-description"
                  maxLength={500}
                  name="description"
                  rows={3}
                />
              </div>
              <p className="text-sm leading-6 text-muted">
                Visibilidad: privada (valor predeterminado del servidor).
              </p>
              {createProjectError && (
                <p
                  className="rounded-md border border-error/40 bg-paper px-4 py-3 text-sm leading-6 text-error"
                  role="alert"
                >
                  {createProjectError}
                </p>
              )}
              <div className="flex flex-wrap items-center gap-3">
                <button
                  className="inline-flex min-h-11 items-center rounded-md bg-graphite px-5 py-3 text-sm font-semibold text-ivory hover:bg-graphite/90 focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-brass-ink disabled:cursor-wait disabled:opacity-65"
                  disabled={
                    isCreatingProject ||
                    (projectScope === "organization" &&
                      (organizationsState.status !== "loaded" ||
                        organizationsState.organizations.length === 0 ||
                        !selectedOrganizationId))
                  }
                  type="submit"
                >
                  {isCreatingProject ? "Creando…" : "Crear proyecto"}
                </button>
              </div>
            </form>
          </section>
        )}
        {createProjectNotice && (
          <p
            className="mx-8 mb-4 text-sm text-success lg:mx-16"
            role="status"
          >
            {createProjectNotice}
          </p>
        )}
        <section
          aria-label="Proyectos"
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
                Todavía no tienes proyectos. Puedes crear el primero desde
                aquí.
              </p>
            ) : filteredProjects.length === 0 ? (
              <p className="rounded-md border border-line bg-paper px-5 py-6 text-sm leading-6 text-muted">
                No hay proyectos que coincidan con los filtros seleccionados.
              </p>
            ) : (
              <div className="grid grid-cols-1 items-stretch gap-5 md:grid-cols-2 xl:grid-cols-3">
                {filteredProjects.map((project) => (
                  <ProjectCard
                    key={project.id}
                    onSelect={(selected) => {
                      dashboardScrollTop.current =
                        mainRef.current?.scrollTop ?? 0;
                      setSelectedProject(selected);
                    }}
                    project={project}
                  />
                ))}
              </div>
            ))}
        </section>
            </div>
            {selectedProject && (
              <ProjectDetail
                onBack={() => {
                  setSelectedProject(null);
                  if (activeView === "home") setRetryCount((count) => count + 1);
                }}
                project={selectedProject}
              />
            )}
            {selectedTask && (
              <WorkItemDetail
                onBack={() => {
                  setSelectedTask(null);
                  setActiveView(detailReturnView);
                  if (detailReturnView === "home") setRetryCount((count) => count + 1);
                }}
                projectId={selectedTask.project_id}
                workItemId={selectedTask.id}
              />
            )}
          </>
      </main>
    </div>
  );
}

export default Dashboard;
