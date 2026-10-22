import { useEffect, useState } from "react";
import type { ProjectSummary } from "./ProjectCard";

interface ProjectDetailProps {
  project: ProjectSummary;
  onBack: () => void;
}

interface WorkItemSummary {
  id: number;
  type: "task";
  title: string;
  description: string | null;
  status: string;
  priority: string;
  assignee_id: number | null;
  assignee_display_name: string | null;
}

type WorkItemsState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "loaded"; workItems: WorkItemSummary[] };

class WorkItemsRequestError extends Error {
  constructor(readonly statusCode: number) {
    super("Work item request failed.");
  }
}

class InvalidWorkItemsResponseError extends Error {}

function isWorkItemSummary(value: unknown): value is WorkItemSummary {
  if (typeof value !== "object" || value === null) {
    return false;
  }

  const workItem = value as Record<string, unknown>;
  return (
    typeof workItem.id === "number" &&
    workItem.type === "task" &&
    typeof workItem.title === "string" &&
    (typeof workItem.description === "string" ||
      workItem.description === null) &&
    typeof workItem.status === "string" &&
    typeof workItem.priority === "string" &&
    (typeof workItem.assignee_id === "number" ||
      workItem.assignee_id === null) &&
    (typeof workItem.assignee_display_name === "string" ||
      workItem.assignee_display_name === null)
  );
}

async function fetchWorkItems(
  projectId: number,
  signal: AbortSignal,
): Promise<WorkItemSummary[]> {
  const response = await fetch(
    `/api/projects/${projectId}/work-items/?type_filter=task`,
    {
      method: "GET",
      credentials: "include",
      signal,
    },
  );

  if (!response.ok) {
    throw new WorkItemsRequestError(response.status);
  }

  let responseBody: unknown;
  try {
    responseBody = await response.json();
  } catch {
    throw new InvalidWorkItemsResponseError();
  }

  if (
    !Array.isArray(responseBody) ||
    !responseBody.every(isWorkItemSummary)
  ) {
    throw new InvalidWorkItemsResponseError();
  }

  return responseBody;
}

function getWorkItemsErrorMessage(error: unknown): string {
  if (error instanceof WorkItemsRequestError) {
    if (error.statusCode === 401) {
      return "Tu sesión no es válida. Inicia sesión de nuevo para consultar las tareas.";
    }
    if (error.statusCode === 403) {
      return "No tienes permisos para consultar las tareas de este proyecto.";
    }
    if (error.statusCode === 404) {
      return "No se encontró el proyecto o ya no está disponible.";
    }
    return "No se pudieron cargar las tareas. Inténtalo de nuevo más tarde.";
  }

  if (error instanceof InvalidWorkItemsResponseError) {
    return "El servicio respondió con datos de tareas que no se pudieron validar.";
  }

  return "No se pudo conectar con el servicio para cargar las tareas. Comprueba la conexión e inténtalo de nuevo.";
}

const statusLabels: Record<string, string> = {
  open: "Abierta",
  in_progress: "En curso",
  resolved: "Resuelta",
  closed: "Cerrada",
};

const priorityLabels: Record<string, string> = {
  low: "Baja",
  medium: "Media",
  high: "Alta",
  urgent: "Urgente",
};

function ProjectDetail({ project, onBack }: ProjectDetailProps) {
  const [retryCount, setRetryCount] = useState(0);
  const [workItemsState, setWorkItemsState] = useState<WorkItemsState>({
    status: "loading",
  });

  useEffect(() => {
    const controller = new AbortController();
    setWorkItemsState({ status: "loading" });

    void fetchWorkItems(project.id, controller.signal)
      .then((workItems) => {
        if (!controller.signal.aborted) {
          setWorkItemsState({ status: "loaded", workItems });
        }
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted) {
          setWorkItemsState({
            status: "error",
            message: getWorkItemsErrorMessage(error),
          });
        }
      });

    return () => controller.abort();
  }, [project.id, retryCount]);

  const organizationName = project.organization_name?.trim();

  return (
    <div className="px-8 pb-12 lg:px-16">
      <button
        className="mb-6 min-h-10 rounded-sm border border-line bg-paper px-4 py-2 text-sm font-medium text-primary hover:bg-mist/50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brass-ink"
        onClick={onBack}
        type="button"
      >
        Volver a proyectos
      </button>

      <section
        aria-labelledby="project-detail-title"
        className="rounded-md border border-line bg-paper p-5 sm:p-7"
      >
        <p className="font-mono text-xs uppercase tracking-wide text-brass">
          {project.organization_id === null
            ? "Proyecto personal"
            : `Proyecto de ${organizationName || "una organización"}`}
        </p>
        <h1
          className="mt-2 break-words text-2xl font-semibold tracking-tight text-primary sm:text-3xl"
          id="project-detail-title"
        >
          {project.name}
        </h1>
        {project.description?.trim() && (
          <p className="mt-4 max-w-3xl whitespace-pre-wrap break-words text-sm leading-6 text-muted">
            {project.description}
          </p>
        )}
      </section>

      <section
        aria-labelledby="project-work-items-title"
        aria-live={workItemsState.status === "loading" ? "polite" : undefined}
        className="mt-8"
      >
        <h2
          className="text-lg font-semibold text-primary"
          id="project-work-items-title"
        >
          Tareas
        </h2>

        {workItemsState.status === "loading" && (
          <p className="mt-4 text-sm text-muted" role="status">
            Cargando tareas…
          </p>
        )}

        {workItemsState.status === "error" && (
          <div
            className="mt-4 rounded-md border border-error/30 bg-paper p-5"
            role="alert"
          >
            <p className="text-sm leading-6 text-error">
              {workItemsState.message}
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

        {workItemsState.status === "loaded" &&
          (workItemsState.workItems.length === 0 ? (
            <p className="mt-4 rounded-md border border-line bg-paper px-5 py-6 text-sm leading-6 text-muted">
              Este proyecto todavía no tiene tareas.
            </p>
          ) : (
            <ul className="mt-4 divide-y divide-line rounded-md border border-line bg-paper">
              {workItemsState.workItems.map((workItem) => (
                <li
                  className="flex flex-wrap items-center justify-between gap-3 px-5 py-4"
                  key={workItem.id}
                >
                  <span className="min-w-0 flex-1">
                    <span className="block break-words text-sm font-medium text-primary">
                      {workItem.title}
                    </span>
                    {workItem.description?.trim() && (
                      <span className="mt-1 block whitespace-pre-wrap break-words text-sm leading-6 text-muted">
                        {workItem.description}
                      </span>
                    )}
                  </span>
                  <span className="text-xs text-muted">
                    {workItem.assignee_id === null
                      ? "Sin asignar"
                      : workItem.assignee_display_name}
                  </span>
                  <span className="rounded-sm border border-line bg-mist/50 px-2 py-1 text-xs text-steel">
                    {statusLabels[workItem.status] || workItem.status}
                  </span>
                  <span className="rounded-sm border border-line px-2 py-1 text-xs text-muted">
                    Prioridad:{" "}
                    {priorityLabels[workItem.priority] || workItem.priority}
                  </span>
                </li>
              ))}
            </ul>
          ))}
      </section>
    </div>
  );
}

export default ProjectDetail;
