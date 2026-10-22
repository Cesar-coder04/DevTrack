import { useEffect, useMemo, useState } from "react";

type IssueStatus = "open" | "in_progress" | "resolved" | "closed";
type IssuePriority = "low" | "medium" | "high" | "urgent";
type IssueSort = "priority" | "created_at" | "updated_at";

export interface Issue {
  id: number;
  type: "issue";
  title: string;
  description: string | null;
  status: IssueStatus;
  priority: IssuePriority;
  assignee_id: number | null;
  assignee_display_name: string | null;
  project_id: number;
  project_name: string;
  organization_id: number | null;
  organization_name: string | null;
  created_at: string;
  updated_at: string;
}

interface IssueDetail extends Issue {
  reporter_id: number;
  due_date: string | null;
}

type LoadState<T> =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "loaded"; value: T };

interface Filters {
  status: string;
  priority: string;
  assignee: string;
  sortBy: IssueSort;
  sortOrder: "asc" | "desc";
}

class IssueRequestError extends Error {
  constructor(readonly statusCode: number) {
    super("Issue request failed.");
  }
}

class InvalidIssueResponseError extends Error {}

const initialFilters: Filters = {
  status: "",
  priority: "",
  assignee: "",
  sortBy: "priority",
  sortOrder: "desc",
};

const statusLabels: Record<IssueStatus, string> = {
  open: "Abierta",
  in_progress: "En curso",
  resolved: "Resuelta",
  closed: "Cerrada",
};

const priorityLabels: Record<IssuePriority, string> = {
  low: "Baja",
  medium: "Media",
  high: "Alta",
  urgent: "Urgente",
};

export function isIssue(value: unknown): value is Issue {
  if (typeof value !== "object" || value === null) return false;
  const issue = value as Record<string, unknown>;
  return (
    Number.isSafeInteger(issue.id) &&
    issue.type === "issue" &&
    typeof issue.title === "string" &&
    (typeof issue.description === "string" || issue.description === null) &&
    (issue.status === "open" ||
      issue.status === "in_progress" ||
      issue.status === "resolved" ||
      issue.status === "closed") &&
    (issue.priority === "low" ||
      issue.priority === "medium" ||
      issue.priority === "high" ||
      issue.priority === "urgent") &&
    (issue.assignee_id === null || Number.isSafeInteger(issue.assignee_id)) &&
    (typeof issue.assignee_display_name === "string" ||
      issue.assignee_display_name === null) &&
    Number.isSafeInteger(issue.project_id) &&
    typeof issue.project_name === "string" &&
    (issue.organization_id === null ||
      Number.isSafeInteger(issue.organization_id)) &&
    (typeof issue.organization_name === "string" ||
      issue.organization_name === null) &&
    typeof issue.created_at === "string" &&
    Number.isFinite(Date.parse(issue.created_at)) &&
    typeof issue.updated_at === "string" &&
    Number.isFinite(Date.parse(issue.updated_at))
  );
}

function isIssueDetail(value: unknown): value is IssueDetail {
  if (!isIssue(value)) return false;
  const detail = value as unknown as Record<string, unknown>;
  return (
    Number.isSafeInteger(detail.reporter_id) &&
    (detail.due_date === null ||
      (typeof detail.due_date === "string" &&
        Number.isFinite(Date.parse(detail.due_date))))
  );
}

function errorMessage(error: unknown): string {
  if (error instanceof IssueRequestError && error.statusCode === 401) return "Tu sesión no es válida. Inicia sesión de nuevo.";
  if (error instanceof IssueRequestError && error.statusCode === 403) return "No tienes permisos para consultar estas incidencias.";
  if (error instanceof IssueRequestError && error.statusCode === 404) return "La incidencia o su proyecto ya no están disponibles.";
  if (error instanceof IssueRequestError && error.statusCode === 422) return "Revisa los filtros seleccionados.";
  if (error instanceof IssueRequestError) return "No se pudieron cargar las incidencias. Inténtalo de nuevo.";
  if (error instanceof InvalidIssueResponseError) return "El servicio respondió con datos de incidencias que no se pudieron validar.";
  return "No se pudo conectar con el servicio. Comprueba la conexión e inténtalo de nuevo.";
}

function formatDate(value: string): string {
  return new Intl.DateTimeFormat("es", { dateStyle: "medium" }).format(
    new Date(value),
  );
}

interface IssuesProps {
  active?: boolean;
  initialIssue?: Issue | null;
}

function Issues({ active = true, initialIssue = null }: IssuesProps) {
  const [filters, setFilters] = useState(initialFilters);
  const [listRetry, setListRetry] = useState(0);
  const [issuesState, setIssuesState] = useState<LoadState<Issue[]>>({
    status: "loading",
  });
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [fullDetail, setFullDetail] = useState(false);
  const [detailRetry, setDetailRetry] = useState(0);
  const [detailState, setDetailState] =
    useState<LoadState<IssueDetail> | null>(null);
  const [assigneeOptions, setAssigneeOptions] = useState<Map<number, string>>(
    new Map(),
  );

  useEffect(() => {
    if (!active) return;
    const controller = new AbortController();
    const query = new URLSearchParams({
      sort_by: filters.sortBy,
      sort_order: filters.sortOrder,
    });
    if (filters.status) query.set("status_filter", filters.status);
    if (filters.priority) query.set("priority_filter", filters.priority);
    if (filters.assignee === "unassigned") query.set("unassigned", "true");
    else if (filters.assignee) query.set("assignee_id", filters.assignee);

    setIssuesState({ status: "loading" });
    void fetch(`/api/users/me/issues/?${query}`, {
      method: "GET",
      credentials: "include",
      signal: controller.signal,
    })
      .then(async (response) => {
        if (!response.ok) throw new IssueRequestError(response.status);
        let body: unknown;
        try {
          body = await response.json();
        } catch {
          throw new InvalidIssueResponseError();
        }
        if (!Array.isArray(body) || !body.every(isIssue)) {
          throw new InvalidIssueResponseError();
        }
        if (!controller.signal.aborted) {
          setAssigneeOptions((current) => {
            const next = new Map(current);
            for (const issue of body) {
              if (issue.assignee_id !== null && issue.assignee_display_name) {
                next.set(issue.assignee_id, issue.assignee_display_name);
              }
            }
            return next;
          });
          setIssuesState({ status: "loaded", value: body });
          if (selectedId !== null && !body.some((issue) => issue.id === selectedId) && initialIssue?.id !== selectedId) {
            setSelectedId(null);
            setFullDetail(false);
            setDetailState(null);
          }
        }
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted) {
          setIssuesState({
            status: "error",
            message: errorMessage(error),
          });
        }
      });
    return () => controller.abort();
  }, [active, filters, initialIssue, listRetry]);

  useEffect(() => {
    if (active && initialIssue) {
      setSelectedId(initialIssue.id);
      setFullDetail(true);
    }
  }, [active, initialIssue]);

  const selectedIssue = useMemo(
    () =>
      (issuesState.status === "loaded"
        ? issuesState.value.find((issue) => issue.id === selectedId)
        : undefined) ??
        (initialIssue?.id === selectedId ? initialIssue : null),
    [initialIssue, issuesState, selectedId],
  );

  useEffect(() => {
    if (!active || !fullDetail || selectedIssue === null) {
      setDetailState(null);
      return;
    }
    const controller = new AbortController();
    setDetailState({ status: "loading" });
    void fetch(
      `/api/projects/${selectedIssue.project_id}/work-items/${selectedIssue.id}`,
      { method: "GET", credentials: "include", signal: controller.signal },
    )
      .then(async (response) => {
        if (!response.ok) throw new IssueRequestError(response.status);
        let body: unknown;
        try {
          body = await response.json();
        } catch {
          throw new InvalidIssueResponseError();
        }
        if (!isIssueDetail(body)) throw new InvalidIssueResponseError();
        if (!controller.signal.aborted) setDetailState({ status: "loaded", value: body });
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted) {
          setDetailState({
            status: "error",
            message: errorMessage(error),
          });
        }
      });
    return () => controller.abort();
  }, [active, fullDetail, selectedIssue, detailRetry]);

  const isFiltered =
    filters.status !== "" ||
    filters.priority !== "" ||
    filters.assignee !== "";

  return (
    <section
      hidden={!active}
      aria-labelledby="issues-title"
      aria-live={issuesState.status === "loading" ? "polite" : undefined}
      className="px-8 pb-12 lg:px-16"
    >
      <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight text-primary sm:text-4xl" id="issues-title">
            Incidencias
          </h1>
          <p className="mt-2 text-sm leading-6 text-muted">
            Incidencias de tus proyectos personales y de organizaciones.
          </p>
        </div>
        <button
          className="min-h-10 rounded-sm border border-line px-4 py-2 text-sm font-medium text-primary hover:bg-mist/50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brass-ink disabled:opacity-50"
          disabled={!isFiltered}
          onClick={() => setFilters({ ...initialFilters })}
          type="button"
        >
          Limpiar filtros
        </button>
      </div>

      <div className="mb-6 grid gap-3 rounded-md border border-line bg-paper p-4 sm:grid-cols-2 xl:grid-cols-4">
        <label className="grid gap-1 text-xs font-medium text-muted">
          Estado
          <select className="min-h-10 rounded-sm border border-line bg-paper px-3 text-sm text-primary" value={filters.status} onChange={(event) => setFilters((current) => ({ ...current, status: event.target.value }))}>
            <option value="">Todos</option>
            {Object.entries(statusLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
        </label>
        <label className="grid gap-1 text-xs font-medium text-muted">
          Prioridad
          <select className="min-h-10 rounded-sm border border-line bg-paper px-3 text-sm text-primary" value={filters.priority} onChange={(event) => setFilters((current) => ({ ...current, priority: event.target.value }))}>
            <option value="">Todas</option>
            {Object.entries(priorityLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
        </label>
        <label className="grid gap-1 text-xs font-medium text-muted">
          Responsable
          <select className="min-h-10 rounded-sm border border-line bg-paper px-3 text-sm text-primary" value={filters.assignee} onChange={(event) => setFilters((current) => ({ ...current, assignee: event.target.value }))}>
            <option value="">Todos</option>
            <option value="unassigned">Sin asignar</option>
            {[...assigneeOptions.entries()].sort((a, b) => a[1].localeCompare(b[1], "es")).map(([id, name]) => <option key={id} value={id}>{name}</option>)}
          </select>
        </label>
        <div className="grid grid-cols-2 gap-2">
          <label className="grid gap-1 text-xs font-medium text-muted">
            Ordenar por
            <select className="min-h-10 rounded-sm border border-line bg-paper px-3 text-sm text-primary" value={filters.sortBy} onChange={(event) => setFilters((current) => ({ ...current, sortBy: event.target.value as IssueSort }))}>
              <option value="priority">Prioridad</option>
              <option value="created_at">Creación</option>
              <option value="updated_at">Actualización</option>
            </select>
          </label>
          <label className="grid gap-1 text-xs font-medium text-muted">
            Dirección
            <select className="min-h-10 rounded-sm border border-line bg-paper px-3 text-sm text-primary" value={filters.sortOrder} onChange={(event) => setFilters((current) => ({ ...current, sortOrder: event.target.value as Filters["sortOrder"] }))}>
              <option value="desc">Descendente</option>
              <option value="asc">Ascendente</option>
            </select>
          </label>
        </div>
      </div>

      {issuesState.status === "loading" && <p className="rounded-md border border-line bg-paper px-5 py-6 text-sm text-muted" role="status">Cargando incidencias…</p>}
      {issuesState.status === "error" && <div className="rounded-md border border-error/30 bg-paper p-5" role="alert"><p className="text-sm leading-6 text-error">{issuesState.message}</p><button className="mt-4 min-h-10 rounded-sm border border-line px-4 py-2 text-sm font-medium text-primary" onClick={() => setListRetry((count) => count + 1)} type="button">Reintentar</button></div>}
      {issuesState.status === "loaded" && issuesState.value.length === 0 && <p className="rounded-md border border-line bg-paper px-5 py-6 text-sm leading-6 text-muted">{isFiltered ? "No hay incidencias que coincidan con los filtros." : "No hay incidencias disponibles."}</p>}
      {issuesState.status === "loaded" && issuesState.value.length === 0 && selectedIssue && (
        <aside aria-label="Detalle de incidencia seleccionada" className="mt-5 rounded-md border border-line bg-paper p-5">
          <h2 className="break-words text-lg font-semibold text-primary">{selectedIssue.title}</h2>
          <p className="mt-2 text-sm text-muted">{selectedIssue.project_name}{selectedIssue.organization_name ? ` · ${selectedIssue.organization_name}` : ""}</p>
          {detailState?.status === "loading" && <p className="mt-4 text-sm text-muted" role="status">Cargando detalle…</p>}
          {detailState?.status === "error" && <div className="mt-4" role="alert"><p className="text-sm text-error">{detailState.message}</p><button className="mt-2 min-h-9 rounded-sm border border-line px-3 text-sm" onClick={() => setDetailRetry((count) => count + 1)} type="button">Reintentar</button></div>}
          {detailState?.status === "loaded" && <dl className="mt-4 grid gap-3 text-sm"><div><dt className="text-xs text-muted">Estado</dt><dd className="mt-1 text-primary">{statusLabels[detailState.value.status]}</dd></div><div><dt className="text-xs text-muted">Prioridad</dt><dd className="mt-1 text-primary">{priorityLabels[detailState.value.priority]}</dd></div><div><dt className="text-xs text-muted">Responsable</dt><dd className="mt-1 text-primary">{detailState.value.assignee_id === null ? "Sin asignar" : detailState.value.assignee_display_name}</dd></div><div><dt className="text-xs text-muted">Descripción</dt><dd className="mt-1 whitespace-pre-wrap text-primary">{detailState.value.description || "Sin descripción"}</dd></div><div><dt className="text-xs text-muted">Vencimiento</dt><dd className="mt-1 text-primary">{detailState.value.due_date ? formatDate(detailState.value.due_date) : "Sin vencimiento"}</dd></div></dl>}
        </aside>
      )}
      {issuesState.status === "loaded" && issuesState.value.length > 0 && (
        <div className="grid items-start gap-5 xl:grid-cols-[minmax(0,1fr)_minmax(18rem,0.7fr)]">
          <ul aria-label="Lista de incidencias" className="divide-y divide-line rounded-md border border-line bg-paper">
            {issuesState.value.map((issue) => (
              <li key={issue.id}>
                <button aria-pressed={selectedId === issue.id} className={`flex min-h-16 w-full flex-wrap items-center gap-x-4 gap-y-2 px-4 py-4 text-left hover:bg-mist/40 focus-visible:outline-2 focus-visible:outline-inset focus-visible:outline-brass-ink ${selectedId === issue.id ? "bg-mist/50" : ""}`} onClick={() => { setSelectedId(issue.id); setFullDetail(false); setDetailState(null); }} type="button">
                  <span className="min-w-44 flex-1 break-words text-sm font-medium text-primary">{issue.title}</span>
                  <span className="rounded-sm border border-line bg-mist/50 px-2 py-1 text-xs text-steel">{statusLabels[issue.status]}</span>
                  <span className="text-xs text-muted">Prioridad: {priorityLabels[issue.priority]}</span>
                  <span className="max-w-48 break-words text-xs text-muted">{issue.assignee_id === null ? "Sin asignar" : issue.assignee_display_name}</span>
                  <span className="max-w-48 break-words text-xs text-muted">{issue.project_name}{issue.organization_name ? ` · ${issue.organization_name}` : ""}</span>
                </button>
              </li>
            ))}
          </ul>
          {selectedIssue && (
            <aside aria-label="Detalle rápido de incidencia" className="rounded-md border border-line bg-paper p-5">
              <div className="flex items-start justify-between gap-3">
                <h2 className="break-words text-lg font-semibold text-primary">{selectedIssue.title}</h2>
                <button aria-label="Cerrar detalle" className="min-h-9 shrink-0 rounded-sm border border-line px-3 text-sm text-primary" onClick={() => { setSelectedId(null); setFullDetail(false); }} type="button">Cerrar</button>
              </div>
              <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-2">
                <div><dt className="text-xs text-muted">Estado</dt><dd className="mt-1 text-primary">{statusLabels[selectedIssue.status]}</dd></div>
                <div><dt className="text-xs text-muted">Prioridad</dt><dd className="mt-1 text-primary">{priorityLabels[selectedIssue.priority]}</dd></div>
                <div><dt className="text-xs text-muted">Responsable</dt><dd className="mt-1 text-primary">{selectedIssue.assignee_id === null ? "Sin asignar" : selectedIssue.assignee_display_name}</dd></div>
                <div><dt className="text-xs text-muted">Proyecto</dt><dd className="mt-1 text-primary">{selectedIssue.project_name}{selectedIssue.organization_name ? ` · ${selectedIssue.organization_name}` : ""}</dd></div>
                <div><dt className="text-xs text-muted">Creada</dt><dd className="mt-1 text-primary">{formatDate(selectedIssue.created_at)}</dd></div>
                <div><dt className="text-xs text-muted">Actualizada</dt><dd className="mt-1 text-primary">{formatDate(selectedIssue.updated_at)}</dd></div>
              </dl>
              {selectedIssue.description && <p className="mt-4 whitespace-pre-wrap break-words text-sm leading-6 text-muted">{selectedIssue.description}</p>}
              <button className="mt-5 min-h-10 rounded-sm border border-line px-4 py-2 text-sm font-medium text-primary hover:bg-mist/50" onClick={() => setFullDetail(true)} type="button">Ver detalle completo</button>
              {fullDetail && (
                <div aria-live="polite" className="mt-4 border-t border-line pt-4">
                  {detailState?.status === "loading" && <p className="text-sm text-muted" role="status">Cargando detalle…</p>}
                  {detailState?.status === "error" && <div role="alert"><p className="text-sm text-error">{detailState.message}</p><button className="mt-2 min-h-9 rounded-sm border border-line px-3 text-sm" onClick={() => setDetailRetry((count) => count + 1)} type="button">Reintentar</button></div>}
                  {detailState?.status === "loaded" && <dl className="grid gap-3 text-sm"><div><dt className="text-xs text-muted">Descripción</dt><dd className="mt-1 whitespace-pre-wrap break-words text-primary">{detailState.value.description || "Sin descripción"}</dd></div><div><dt className="text-xs text-muted">Vencimiento</dt><dd className="mt-1 text-primary">{detailState.value.due_date ? formatDate(detailState.value.due_date) : "Sin vencimiento"}</dd></div><div><dt className="text-xs text-muted">Identificador</dt><dd className="mt-1 text-primary">#{detailState.value.id}</dd></div></dl>}
                </div>
              )}
            </aside>
          )}
        </div>
      )}
    </section>
  );
}

export default Issues;
