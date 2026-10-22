import { useEffect, useMemo, useState } from "react";
import type { ProjectSummary } from "./ProjectCard";

export interface MyTask {
  id: number;
  type: "task";
  title: string;
  status: "open" | "in_progress" | "resolved" | "closed";
  priority: "low" | "medium" | "high" | "urgent";
  project_id: number;
  project_name: string;
  organization_id: number | null;
  organization_name: string | null;
  due_date: string | null;
  created_at: string;
  updated_at: string;
}

interface MyTasksProps {
  projects: ProjectSummary[];
  active?: boolean;
  onOpenTask?: (task: MyTask) => void;
}

interface TaskFilters {
  status: string;
  priority: string;
  projectId: string;
  organizationId: string;
  dueDateFrom: string;
  dueDateTo: string;
}

type MyTasksState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "loaded"; tasks: MyTask[] };

class MyTasksRequestError extends Error {
  constructor(readonly statusCode: number) {
    super("My tasks request failed.");
  }
}

class InvalidMyTasksResponseError extends Error {}

const emptyFilters: TaskFilters = {
  status: "",
  priority: "",
  projectId: "",
  organizationId: "",
  dueDateFrom: "",
  dueDateTo: "",
};

const statusLabels: Record<MyTask["status"], string> = {
  open: "Abierta",
  in_progress: "En curso",
  resolved: "Resuelta",
  closed: "Cerrada",
};

const priorityLabels: Record<MyTask["priority"], string> = {
  low: "Baja",
  medium: "Media",
  high: "Alta",
  urgent: "Urgente",
};

function isDateOnly(value: unknown): value is string {
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value)) {
    return false;
  }

  const [year, month, day] = value.split("-").map(Number);
  const parsed = new Date(year, month - 1, day);
  return (
    parsed.getFullYear() === year &&
    parsed.getMonth() === month - 1 &&
    parsed.getDate() === day
  );
}

export function isMyTask(value: unknown): value is MyTask {
  if (typeof value !== "object" || value === null) {
    return false;
  }

  const task = value as Record<string, unknown>;
  return (
    typeof task.id === "number" &&
    Number.isSafeInteger(task.id) &&
    task.type === "task" &&
    typeof task.title === "string" &&
    (task.status === "open" ||
      task.status === "in_progress" ||
      task.status === "resolved" ||
      task.status === "closed") &&
    (task.priority === "low" ||
      task.priority === "medium" ||
      task.priority === "high" ||
      task.priority === "urgent") &&
    typeof task.project_id === "number" &&
    Number.isSafeInteger(task.project_id) &&
    typeof task.project_name === "string" &&
    (task.organization_id === null ||
      (typeof task.organization_id === "number" &&
        Number.isSafeInteger(task.organization_id))) &&
    (task.organization_name === null ||
      typeof task.organization_name === "string") &&
    (task.due_date === null || isDateOnly(task.due_date)) &&
    typeof task.created_at === "string" &&
    Number.isFinite(Date.parse(task.created_at)) &&
    typeof task.updated_at === "string" &&
    Number.isFinite(Date.parse(task.updated_at))
  );
}

async function fetchMyTasks(
  filters: TaskFilters,
  signal: AbortSignal,
): Promise<MyTask[]> {
  const query = new URLSearchParams();
  if (filters.status) query.set("status_filter", filters.status);
  if (filters.priority) query.set("priority_filter", filters.priority);
  if (filters.projectId) query.set("project_id", filters.projectId);
  if (filters.organizationId) {
    query.set("organization_id", filters.organizationId);
  }
  if (filters.dueDateFrom) query.set("due_date_from", filters.dueDateFrom);
  if (filters.dueDateTo) query.set("due_date_to", filters.dueDateTo);

  const queryString = query.toString();
  const response = await fetch(
    `/api/users/me/work-items/${queryString ? `?${queryString}` : ""}`,
    {
      method: "GET",
      credentials: "include",
      signal,
    },
  );

  if (!response.ok) {
    throw new MyTasksRequestError(response.status);
  }

  let body: unknown;
  try {
    body = await response.json();
  } catch {
    throw new InvalidMyTasksResponseError();
  }

  if (!Array.isArray(body) || !body.every(isMyTask)) {
    throw new InvalidMyTasksResponseError();
  }
  return body;
}

function getErrorMessage(error: unknown): string {
  if (error instanceof MyTasksRequestError) {
    if (error.statusCode === 401) {
      return "Tu sesión no es válida. Inicia sesión de nuevo para consultar tus tareas.";
    }
    if (error.statusCode === 403) {
      return "No tienes permisos para consultar estas tareas.";
    }
    if (error.statusCode === 422) {
      return "Revisa los filtros de estado y fechas e inténtalo de nuevo.";
    }
    return "No se pudieron cargar tus tareas. Inténtalo de nuevo más tarde.";
  }
  if (error instanceof InvalidMyTasksResponseError) {
    return "El servicio respondió con datos de tareas que no se pudieron validar.";
  }
  return "No se pudo conectar con el servicio para cargar tus tareas. Comprueba la conexión e inténtalo de nuevo.";
}

function utcDateKey(date: Date): string {
  return date.toISOString().slice(0, 10);
}

function formatDate(value: string): string {
  const [year, month, day] = value.split("-").map(Number);
  return new Intl.DateTimeFormat("es", { dateStyle: "medium" }).format(
    new Date(year, month - 1, day),
  );
}

function MyTasks({ projects, active = true, onOpenTask }: MyTasksProps) {
  const [filters, setFilters] = useState<TaskFilters>(emptyFilters);
  const [retryCount, setRetryCount] = useState(0);
  const [state, setState] = useState<MyTasksState>({ status: "loading" });
  const organizationOptions = useMemo(() => {
    const organizations = new Map<number, string>();
    for (const project of projects) {
      if (project.organization_id !== null && project.organization_name) {
        organizations.set(project.organization_id, project.organization_name);
      }
    }
    return [...organizations.entries()].sort((left, right) =>
      left[1].localeCompare(right[1], "es"),
    );
  }, [projects]);

  useEffect(() => {
    if (!active) return;
    const controller = new AbortController();
    setState({ status: "loading" });
    void fetchMyTasks(filters, controller.signal)
      .then((tasks) => {
        if (!controller.signal.aborted) {
          setState({ status: "loaded", tasks });
        }
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted) {
          setState({ status: "error", message: getErrorMessage(error) });
        }
      });
    return () => controller.abort();
  }, [active, filters, retryCount]);

  const hasFilters = Object.values(filters).some(Boolean);
  const visibleProjects = filters.organizationId
    ? projects.filter(
        (project) =>
          String(project.organization_id) === filters.organizationId,
      )
    : projects;

  function updateFilter<K extends keyof TaskFilters>(
    key: K,
    value: TaskFilters[K],
  ) {
    setFilters((current) => ({ ...current, [key]: value }));
  }

  return (
    <section
      hidden={!active}
      aria-labelledby="my-tasks-title"
      aria-live={state.status === "loading" ? "polite" : undefined}
      className="px-8 pb-12 lg:px-16"
    >
      <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1
            className="text-3xl font-semibold tracking-tight text-primary sm:text-4xl"
            id="my-tasks-title"
          >
            Mis tareas
          </h1>
          <p className="mt-2 text-sm leading-6 text-muted">
            Tareas asignadas a tu usuario en tus proyectos.
          </p>
        </div>
        <button
          className="min-h-10 rounded-sm border border-line px-4 py-2 text-sm font-medium text-primary hover:bg-mist/50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brass-ink disabled:cursor-not-allowed disabled:opacity-50"
          disabled={!hasFilters}
          onClick={() => setFilters(emptyFilters)}
          type="button"
        >
          Limpiar filtros
        </button>
      </div>

      <div className="mb-6 grid gap-3 rounded-md border border-line bg-paper p-4 sm:grid-cols-2 xl:grid-cols-3">
        <label className="grid gap-1 text-xs font-medium text-muted">
          Estado
          <select
            className="min-h-10 rounded-sm border border-line bg-paper px-3 text-sm text-primary"
            onChange={(event) => updateFilter("status", event.target.value)}
            value={filters.status}
          >
            <option value="">Todos</option>
            <option value="open">Abierta</option>
            <option value="in_progress">En curso</option>
            <option value="resolved">Resuelta</option>
            <option value="closed">Cerrada</option>
          </select>
        </label>
        <label className="grid gap-1 text-xs font-medium text-muted">
          Prioridad
          <select
            className="min-h-10 rounded-sm border border-line bg-paper px-3 text-sm text-primary"
            onChange={(event) => updateFilter("priority", event.target.value)}
            value={filters.priority}
          >
            <option value="">Todas</option>
            <option value="low">Baja</option>
            <option value="medium">Media</option>
            <option value="high">Alta</option>
            <option value="urgent">Urgente</option>
          </select>
        </label>
        <label className="grid gap-1 text-xs font-medium text-muted">
          Organización
          <select
            className="min-h-10 rounded-sm border border-line bg-paper px-3 text-sm text-primary"
            onChange={(event) => {
              updateFilter("organizationId", event.target.value);
              updateFilter("projectId", "");
            }}
            value={filters.organizationId}
          >
            <option value="">Todas</option>
            {organizationOptions.map(([id, name]) => (
              <option key={id} value={id}>
                {name}
              </option>
            ))}
          </select>
        </label>
        <label className="grid gap-1 text-xs font-medium text-muted">
          Proyecto
          <select
            className="min-h-10 rounded-sm border border-line bg-paper px-3 text-sm text-primary"
            onChange={(event) => updateFilter("projectId", event.target.value)}
            value={filters.projectId}
          >
            <option value="">Todos</option>
            {visibleProjects.map((project) => (
              <option key={project.id} value={project.id}>
                {project.name}
              </option>
            ))}
          </select>
        </label>
        <label className="grid gap-1 text-xs font-medium text-muted">
          Vencimiento desde
          <input
            className="min-h-10 rounded-sm border border-line bg-paper px-3 text-sm text-primary"
            onChange={(event) =>
              updateFilter("dueDateFrom", event.target.value)
            }
            type="date"
            value={filters.dueDateFrom}
          />
        </label>
        <label className="grid gap-1 text-xs font-medium text-muted">
          Vencimiento hasta
          <input
            className="min-h-10 rounded-sm border border-line bg-paper px-3 text-sm text-primary"
            onChange={(event) => updateFilter("dueDateTo", event.target.value)}
            type="date"
            value={filters.dueDateTo}
          />
        </label>
      </div>

      {state.status === "loading" && (
        <p className="rounded-md border border-line bg-paper px-5 py-6 text-sm text-muted" role="status">
          Cargando tus tareas…
        </p>
      )}

      {state.status === "error" && (
        <div className="rounded-md border border-error/30 bg-paper p-5" role="alert">
          <p className="text-sm leading-6 text-error">{state.message}</p>
          <button
            className="mt-4 min-h-10 rounded-sm border border-line px-4 py-2 text-sm font-medium text-primary hover:bg-mist/50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brass-ink"
            onClick={() => setRetryCount((count) => count + 1)}
            type="button"
          >
            Reintentar
          </button>
        </div>
      )}

      {state.status === "loaded" &&
        (state.tasks.length === 0 ? (
          <p className="rounded-md border border-line bg-paper px-5 py-6 text-sm leading-6 text-muted">
            {hasFilters
              ? "No hay tareas que coincidan con los filtros seleccionados."
              : "No tienes tareas asignadas."}
          </p>
        ) : (
          <ul className="divide-y divide-line rounded-md border border-line bg-paper">
            {state.tasks.map((task) => {
              const overdue =
                task.due_date !== null &&
                task.due_date < utcDateKey(new Date()) &&
                task.status !== "resolved" &&
                task.status !== "closed";
              return (
                <li className="px-4 py-4 sm:px-5" key={task.id}>
                  <button
                    className="flex w-full flex-wrap items-center gap-x-5 gap-y-2 text-left focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brass-ink"
                    onClick={() => onOpenTask?.(task)}
                    type="button"
                  >
                  <span className="min-w-44 flex-1 break-words text-sm font-medium text-primary">
                    {task.title}
                  </span>
                  <span className="rounded-sm border border-line bg-mist/50 px-2 py-1 text-xs text-steel">
                    {statusLabels[task.status]}
                  </span>
                  <span className="text-xs text-muted">
                    Prioridad: {priorityLabels[task.priority]}
                  </span>
                  <span className="max-w-48 break-words text-xs text-muted">
                    {task.project_name}
                    {task.organization_name && ` · ${task.organization_name}`}
                  </span>
                  <span className="text-xs text-muted">
                    {task.due_date === null ? (
                      "Sin vencimiento"
                    ) : (
                      <>
                        Vence {formatDate(task.due_date)}
                        {overdue && (
                          <span className="ml-2 font-semibold text-error">
                            Vencida
                          </span>
                        )}
                      </>
                    )}
                  </span>
                  </button>
                </li>
              );
            })}
          </ul>
        ))}
    </section>
  );
}

export default MyTasks;
