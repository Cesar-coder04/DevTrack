import { useEffect, useMemo, useState } from "react";
import type { ProjectSummary } from "./ProjectCard";
import { isMyTask, type MyTask } from "./MyTasks";
import { isIssue, type Issue } from "./Issues";
import QuarterlyStatistics from "./QuarterlyStatistics";

type SectionState<T> =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "loaded"; items: T[] };

interface DashboardHomeProps {
  active: boolean;
  projects: ProjectSummary[];
  organizations: { id: number; name: string }[];
  organizationsStatus: "loading" | "error" | "loaded";
  projectsStatus: "loading" | "error" | "loaded";
  projectsError?: string;
  onRetryProjects: () => void;
  onViewAllProjects: () => void;
  onViewAllTasks: () => void;
  onViewAllIssues: () => void;
  onSelectProject: (project: ProjectSummary) => void;
  onOpenTask: (task: MyTask) => void;
  onOpenIssue: (issue: Issue) => void;
}

class SummaryRequestError extends Error {}
class InvalidSummaryError extends Error {}

function dateSortDesc(left: { created_at: string; id: number }, right: { created_at: string; id: number }) {
  return Date.parse(right.created_at) - Date.parse(left.created_at) || left.id - right.id;
}

function formatDate(value: string): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  const date = match
    ? new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]))
    : new Date(value);
  return new Intl.DateTimeFormat("es", { dateStyle: "medium" }).format(date);
}

function statusLabel(value: string): string {
  const labels: Record<string, string> = {
    open: "Abierta",
    in_progress: "En curso",
    resolved: "Resuelta",
    closed: "Cerrada",
  };
  return labels[value] ?? value;
}

function priorityLabel(value: string): string {
  const labels: Record<string, string> = {
    low: "Baja",
    medium: "Media",
    high: "Alta",
    urgent: "Urgente",
  };
  return labels[value] ?? value;
}

async function fetchSummary<T>(url: string, validate: (value: unknown) => value is T, signal: AbortSignal): Promise<T[]> {
  const response = await fetch(url, { method: "GET", credentials: "include", signal });
  if (!response.ok) throw new SummaryRequestError(`No se pudieron cargar los datos (${response.status}).`);
  let body: unknown;
  try {
    body = await response.json();
  } catch {
    throw new InvalidSummaryError("El servicio devolvió una respuesta no válida.");
  }
  if (!Array.isArray(body) || !body.every(validate)) {
    throw new InvalidSummaryError("El servicio devolvió datos que no se pudieron validar.");
  }
  return body;
}

function errorText(error: unknown): string {
  return error instanceof Error ? error.message : "No se pudo conectar con el servicio.";
}

function DashboardHome(props: DashboardHomeProps) {
  const [tasksState, setTasksState] = useState<SectionState<MyTask>>({ status: "loading" });
  const [issuesState, setIssuesState] = useState<SectionState<Issue>>({ status: "loading" });
  const [taskRetry, setTaskRetry] = useState(0);
  const [issueRetry, setIssueRetry] = useState(0);

  useEffect(() => {
    if (!props.active) return;
    const controller = new AbortController();
    setTasksState({ status: "loading" });
    void fetchSummary("/api/users/me/work-items/", isMyTask, controller.signal)
      .then((items) => {
        if (!controller.signal.aborted) setTasksState({ status: "loaded", items: items.sort(dateSortDesc).slice(0, 3) });
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted) setTasksState({ status: "error", message: errorText(error) });
      });
    return () => controller.abort();
  }, [props.active, taskRetry]);

  useEffect(() => {
    if (!props.active) return;
    const controller = new AbortController();
    setIssuesState({ status: "loading" });
    void fetchSummary("/api/users/me/issues/?sort_by=created_at&sort_order=desc", isIssue, controller.signal)
      .then((items) => {
        if (!controller.signal.aborted) setIssuesState({ status: "loaded", items: items.sort(dateSortDesc).slice(0, 3) });
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted) setIssuesState({ status: "error", message: errorText(error) });
      });
    return () => controller.abort();
  }, [props.active, issueRetry]);

  const recentProjects = useMemo(
    () => [...props.projects].sort(dateSortDesc).slice(0, 3),
    [props.projects],
  );

  const sectionClass = "rounded-md border border-line bg-paper p-5";
  const linkClass = "min-h-9 rounded-sm px-2 text-sm font-medium text-brass underline underline-offset-4 focus-visible:outline-2 focus-visible:outline-brass-ink";

  return (
    <section aria-labelledby="home-title" className="px-8 pb-12 lg:px-16">
      <h1 className="mb-6 text-3xl font-semibold tracking-tight text-primary sm:text-4xl" id="home-title">Inicio</h1>
      <div className="mb-5">
        <QuarterlyStatistics
          active={props.active}
          organizations={props.organizations}
          organizationsStatus={props.organizationsStatus}
          projects={props.projects}
          projectsStatus={props.projectsStatus}
        />
      </div>
      <div className="grid gap-5 xl:grid-cols-3">
        <section aria-labelledby="recent-projects-title" className={sectionClass}>
          <div className="mb-4 flex items-center justify-between gap-3">
            <h2 className="text-lg font-semibold text-primary" id="recent-projects-title">Proyectos recientes</h2>
            <button className={linkClass} onClick={props.onViewAllProjects} type="button">Ver todos</button>
          </div>
          {props.projectsStatus === "loading" && <p className="text-sm text-muted" role="status">Cargando proyectos…</p>}
          {props.projectsStatus === "error" && <div role="alert"><p className="text-sm text-error">{props.projectsError}</p><button className="mt-3 min-h-9 rounded border border-line px-3 text-sm" onClick={props.onRetryProjects} type="button">Reintentar</button></div>}
          {props.projectsStatus === "loaded" && (recentProjects.length ? <ul className="divide-y divide-line">{recentProjects.map((project) => <li key={project.id}><button className="w-full py-3 text-left hover:bg-mist/30 focus-visible:outline-2 focus-visible:outline-brass-ink" onClick={() => props.onSelectProject(project)} type="button"><span className="block break-words text-sm font-medium text-primary">{project.name}</span><span className="mt-1 block text-xs text-muted">{project.organization_name || "Proyecto personal"} · {formatDate(project.created_at)}</span></button></li>)}</ul> : <p className="text-sm text-muted">No hay proyectos disponibles.</p>)}
        </section>

        <section aria-labelledby="recent-tasks-title" className={sectionClass}>
          <div className="mb-4 flex items-center justify-between gap-3"><h2 className="text-lg font-semibold text-primary" id="recent-tasks-title">Mis tareas</h2><button className={linkClass} onClick={props.onViewAllTasks} type="button">Ver todas</button></div>
          {tasksState.status === "loading" && <p className="text-sm text-muted" role="status">Cargando tareas…</p>}
          {tasksState.status === "error" && <div role="alert"><p className="text-sm text-error">{tasksState.message}</p><button className="mt-3 min-h-9 rounded border border-line px-3 text-sm" onClick={() => setTaskRetry((count) => count + 1)} type="button">Reintentar</button></div>}
          {tasksState.status === "loaded" && (tasksState.items.length ? <ul className="divide-y divide-line">{tasksState.items.map((task) => <li key={task.id}><button className="w-full py-3 text-left hover:bg-mist/30 focus-visible:outline-2 focus-visible:outline-brass-ink" onClick={() => props.onOpenTask(task)} type="button"><span className="block break-words text-sm font-medium text-primary">{task.title}</span><span className="mt-1 block text-xs text-muted">{statusLabel(task.status)} · {priorityLabel(task.priority)} · {task.project_name}</span>{task.due_date && <time className="mt-1 block text-xs text-muted" dateTime={task.due_date}>Vence {formatDate(task.due_date)}</time>}</button></li>)}</ul> : <p className="text-sm text-muted">No tienes tareas asignadas.</p>)}
        </section>

        <section aria-labelledby="recent-issues-title" className={sectionClass}>
          <div className="mb-4 flex items-center justify-between gap-3"><h2 className="text-lg font-semibold text-primary" id="recent-issues-title">Incidencias recientes</h2><button className={linkClass} onClick={props.onViewAllIssues} type="button">Ver todas</button></div>
          {issuesState.status === "loading" && <p className="text-sm text-muted" role="status">Cargando incidencias…</p>}
          {issuesState.status === "error" && <div role="alert"><p className="text-sm text-error">{issuesState.message}</p><button className="mt-3 min-h-9 rounded border border-line px-3 text-sm" onClick={() => setIssueRetry((count) => count + 1)} type="button">Reintentar</button></div>}
          {issuesState.status === "loaded" && (issuesState.items.length ? <ul className="divide-y divide-line">{issuesState.items.map((issue) => <li key={issue.id}><button className="w-full py-3 text-left hover:bg-mist/30 focus-visible:outline-2 focus-visible:outline-brass-ink" onClick={() => props.onOpenIssue(issue)} type="button"><span className="block break-words text-sm font-medium text-primary">{issue.title}</span><span className="mt-1 block text-xs text-muted">{statusLabel(issue.status)} · {priorityLabel(issue.priority)} · {issue.project_name}</span><span className="mt-1 block text-xs text-muted">{issue.assignee_id === null ? "Sin asignar" : issue.assignee_display_name}</span></button></li>)}</ul> : <p className="text-sm text-muted">No hay incidencias disponibles.</p>)}
        </section>
      </div>
    </section>
  );
}

export default DashboardHome;
