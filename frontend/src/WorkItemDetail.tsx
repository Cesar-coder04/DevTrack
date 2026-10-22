import { useEffect, useState } from "react";

interface WorkItemDetailData {
  id: number;
  project_id: number;
  type: "task";
  title: string;
  description: string | null;
  status: string;
  priority: string;
  assignee_id: number | null;
  assignee_display_name: string | null;
  project_name: string;
  organization_name: string | null;
  due_date: string | null;
  created_at: string;
  updated_at: string;
}

type DetailState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "loaded"; item: WorkItemDetailData };

interface WorkItemDetailProps {
  projectId: number;
  workItemId: number;
  onBack: () => void;
}

function isDateValue(value: unknown): value is string | null {
  return value === null || (typeof value === "string" && Number.isFinite(Date.parse(value)));
}

function isWorkItemDetail(value: unknown): value is WorkItemDetailData {
  if (typeof value !== "object" || value === null) return false;
  const item = value as Record<string, unknown>;
  return Number.isSafeInteger(item.id) && Number.isSafeInteger(item.project_id) &&
    item.type === "task" && typeof item.title === "string" &&
    (typeof item.description === "string" || item.description === null) &&
    typeof item.status === "string" && typeof item.priority === "string" &&
    (item.assignee_id === null || Number.isSafeInteger(item.assignee_id)) &&
    (typeof item.assignee_display_name === "string" || item.assignee_display_name === null) &&
    typeof item.project_name === "string" &&
    (typeof item.organization_name === "string" || item.organization_name === null) &&
    isDateValue(item.due_date) && isDateValue(item.created_at) && isDateValue(item.updated_at);
}

function displayDate(value: string | null): string {
  if (!value) return "Sin fecha";
  const dateOnly = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  const date = dateOnly ? new Date(+dateOnly[1], +dateOnly[2] - 1, +dateOnly[3]) : new Date(value);
  return new Intl.DateTimeFormat("es", { dateStyle: "medium" }).format(date);
}

function WorkItemDetail({ projectId, workItemId, onBack }: WorkItemDetailProps) {
  const [retryCount, setRetryCount] = useState(0);
  const [state, setState] = useState<DetailState>({ status: "loading" });

  useEffect(() => {
    const controller = new AbortController();
    setState({ status: "loading" });
    void fetch(`/api/projects/${projectId}/work-items/${workItemId}`, {
      method: "GET", credentials: "include", signal: controller.signal,
    }).then(async (response) => {
      if (!response.ok) throw new Error(response.status === 404 ? "La tarea o su proyecto ya no están disponibles." : `No se pudo cargar la tarea (${response.status}).`);
      let body: unknown;
      try { body = await response.json(); } catch { throw new Error("El servicio devolvió una respuesta no válida."); }
      if (!isWorkItemDetail(body)) throw new Error("El servicio devolvió datos de tarea que no se pudieron validar.");
      if (!controller.signal.aborted) setState({ status: "loaded", item: body });
    }).catch((error: unknown) => {
      if (!controller.signal.aborted) setState({ status: "error", message: error instanceof Error ? error.message : "No se pudo conectar con el servicio." });
    });
    return () => controller.abort();
  }, [projectId, workItemId, retryCount]);

  return (
    <section aria-labelledby="work-item-detail-title" className="px-8 pb-12 lg:px-16">
      <button className="mb-5 min-h-10 rounded-sm border border-line px-4 text-sm font-medium text-primary hover:bg-mist/50 focus-visible:outline-2 focus-visible:outline-brass-ink" onClick={onBack} type="button">Volver</button>
      {state.status === "loading" && <p className="rounded-md border border-line bg-paper p-5 text-sm text-muted" role="status">Cargando tarea…</p>}
      {state.status === "error" && <div className="rounded-md border border-error/30 bg-paper p-5" role="alert"><p className="text-sm text-error">{state.message}</p><button className="mt-4 min-h-10 rounded border border-line px-4 text-sm" onClick={() => setRetryCount((count) => count + 1)} type="button">Reintentar</button></div>}
      {state.status === "loaded" && <article className="rounded-md border border-line bg-paper p-5 sm:p-7"><p className="text-sm text-muted">{state.item.project_name}{state.item.organization_name ? ` · ${state.item.organization_name}` : ""}</p><h1 className="mt-2 break-words text-3xl font-semibold text-primary" id="work-item-detail-title">{state.item.title}</h1><dl className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-3"><div><dt className="text-xs text-muted">Estado</dt><dd className="mt-1 text-sm text-primary">{state.item.status}</dd></div><div><dt className="text-xs text-muted">Prioridad</dt><dd className="mt-1 text-sm text-primary">{state.item.priority}</dd></div><div><dt className="text-xs text-muted">Responsable</dt><dd className="mt-1 text-sm text-primary">{state.item.assignee_id === null ? "Sin asignar" : state.item.assignee_display_name ?? "Nombre no disponible"}</dd></div><div><dt className="text-xs text-muted">Vencimiento</dt><dd className="mt-1 text-sm text-primary">{displayDate(state.item.due_date)}</dd></div><div><dt className="text-xs text-muted">Creada</dt><dd className="mt-1 text-sm text-primary">{displayDate(state.item.created_at)}</dd></div><div><dt className="text-xs text-muted">Actualizada</dt><dd className="mt-1 text-sm text-primary">{displayDate(state.item.updated_at)}</dd></div></dl><section className="mt-6 border-t border-line pt-5"><h2 className="text-sm font-semibold text-primary">Descripción</h2><p className="mt-2 whitespace-pre-wrap break-words text-sm leading-6 text-muted">{state.item.description || "Sin descripción."}</p></section></article>}
    </section>
  );
}

export default WorkItemDetail;
