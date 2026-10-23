import { useEffect, useMemo, useState } from "react";
import type { ProjectSummary } from "./ProjectCard";

type Coverage = "reliable" | "partial" | "unavailable";
type Scope = "all" | "personal" | "organization" | "project";

interface OrganizationOption {
  id: number;
  name: string;
}

interface StatisticsCoverage {
  state_and_cycles: Coverage;
  assignments: Coverage;
  completions: Coverage;
  due_date_snapshots: Coverage;
}

interface StatisticsWarning {
  code: string;
  message: string;
}

interface WeeklyPoint {
  week_start: string;
  week_end: string;
  completed_cumulative: number | null;
  pending_at_cut: number | null;
  required_cumulative: number | null;
  required_per_week: number | null;
  coverage: Coverage;
}

interface QuarterlyStatistics {
  year: number;
  quarter: number;
  timezone: string;
  period_start: string;
  period_end_exclusive: string;
  as_of: string;
  period_complete: boolean;
  scope: Scope;
  organization_id: number | null;
  project_id: number | null;
  total_cycles: number | null;
  completed_cycles: number | null;
  pending_at_close: number | null;
  completed_on_time_percent: number | null;
  punctuality_comparable_count: number | null;
  completed_with_known_assignee: number | null;
  completed_unassigned: number | null;
  completed_assignee_unknown: number | null;
  pending_with_known_assignee: number | null;
  pending_unassigned: number | null;
  pending_assignee_unknown: number | null;
  load: { carried_in: number | null; new_cycles: number | null };
  coverage: StatisticsCoverage;
  warnings: StatisticsWarning[];
  weekly: WeeklyPoint[];
}

type StatisticsState =
  | { status: "loading"; key: string }
  | { status: "error"; key: string; message: string }
  | { status: "loaded"; key: string; value: QuarterlyStatistics };

interface QuarterlyStatisticsProps {
  active: boolean;
  organizations: OrganizationOption[];
  organizationsStatus: "loading" | "error" | "loaded";
  projects: ProjectSummary[];
  projectsStatus: "loading" | "error" | "loaded";
}

interface Filters {
  year: string;
  quarter: number;
  scope: Scope;
  organizationId: string;
  projectId: string;
}

class StatisticsRequestError extends Error {
  constructor(readonly statusCode: number) {
    super("Statistics request failed.");
  }
}

class InvalidStatisticsResponseError extends Error {}

const coverageLabels: Record<Coverage, string> = {
  reliable: "Completa",
  partial: "Parcial",
  unavailable: "No disponible",
};

function dateInMadrid(now = new Date()): { year: number; quarter: number; date: string } {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Europe/Madrid",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(now);
  const values = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  const year = Number(values.year);
  const month = Number(values.month);
  return { year, quarter: Math.floor((month - 1) / 3) + 1, date: `${values.year}-${values.month}-${values.day}` };
}

function isCoverage(value: unknown): value is Coverage {
  return value === "reliable" || value === "partial" || value === "unavailable";
}

function isNullableNumber(value: unknown): value is number | null {
  return value === null || (typeof value === "number" && Number.isFinite(value));
}

function isIntegerOrNull(value: unknown): value is number | null {
  return value === null || (typeof value === "number" && Number.isSafeInteger(value));
}

function isDate(value: unknown): value is string {
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const [year, month, day] = value.split("-").map(Number);
  const parsed = new Date(Date.UTC(year, month - 1, day));
  return parsed.getUTCFullYear() === year && parsed.getUTCMonth() === month - 1 && parsed.getUTCDate() === day;
}

function isWarning(value: unknown): value is StatisticsWarning {
  if (typeof value !== "object" || value === null) return false;
  const warning = value as Record<string, unknown>;
  return typeof warning.code === "string" && typeof warning.message === "string";
}

function isWeeklyPoint(value: unknown): value is WeeklyPoint {
  if (typeof value !== "object" || value === null) return false;
  const point = value as Record<string, unknown>;
  return isDate(point.week_start) && isDate(point.week_end) &&
    isIntegerOrNull(point.completed_cumulative) && isIntegerOrNull(point.pending_at_cut) &&
    isNullableNumber(point.required_cumulative) && isNullableNumber(point.required_per_week) &&
    isCoverage(point.coverage);
}

function isStatisticsCoverage(value: unknown): value is StatisticsCoverage {
  if (typeof value !== "object" || value === null) return false;
  const coverage = value as Record<string, unknown>;
  return isCoverage(coverage.state_and_cycles) && isCoverage(coverage.assignments) &&
    isCoverage(coverage.completions) && isCoverage(coverage.due_date_snapshots);
}

function isQuarterlyStatistics(value: unknown): value is QuarterlyStatistics {
  if (typeof value !== "object" || value === null) return false;
  const item = value as Record<string, unknown>;
  if (typeof item.load !== "object" || item.load === null) return false;
  const load = item.load as Record<string, unknown>;
  return Number.isSafeInteger(item.year) && Number.isSafeInteger(item.quarter) &&
    typeof item.timezone === "string" && isDate(item.period_start) && isDate(item.period_end_exclusive) &&
    typeof item.as_of === "string" && Number.isFinite(Date.parse(item.as_of)) &&
    typeof item.period_complete === "boolean" &&
    (item.scope === "all" || item.scope === "personal" || item.scope === "organization" || item.scope === "project") &&
    isIntegerOrNull(item.organization_id) && isIntegerOrNull(item.project_id) &&
    isIntegerOrNull(item.total_cycles) && isIntegerOrNull(item.completed_cycles) &&
    isIntegerOrNull(item.pending_at_close) && isNullableNumber(item.completed_on_time_percent) &&
    isIntegerOrNull(item.punctuality_comparable_count) &&
    isIntegerOrNull(item.completed_with_known_assignee) && isIntegerOrNull(item.completed_unassigned) &&
    isIntegerOrNull(item.completed_assignee_unknown) && isIntegerOrNull(item.pending_with_known_assignee) &&
    isIntegerOrNull(item.pending_unassigned) && isIntegerOrNull(item.pending_assignee_unknown) &&
    isIntegerOrNull(load.carried_in) && isIntegerOrNull(load.new_cycles) &&
    isStatisticsCoverage(item.coverage) && Array.isArray(item.warnings) && item.warnings.every(isWarning) &&
    Array.isArray(item.weekly) && item.weekly.every(isWeeklyPoint);
}

function errorMessage(error: unknown): string {
  if (error instanceof StatisticsRequestError) {
    if (error.statusCode === 401) return "Tu sesión no es válida. Inicia sesión de nuevo para consultar las estadísticas.";
    if (error.statusCode === 403) return "No tienes permisos para consultar las estadísticas de ese ámbito.";
    if (error.statusCode === 404) return "La organización o el proyecto seleccionado ya no está disponible.";
    if (error.statusCode === 422) return "El periodo o el ámbito seleccionado no es válido.";
    return `No se pudieron cargar las estadísticas (${error.statusCode}). Inténtalo de nuevo.`;
  }
  if (error instanceof InvalidStatisticsResponseError) return "El servicio devolvió estadísticas con un formato no válido.";
  return "No se pudo conectar con el servicio. Comprueba la conexión e inténtalo de nuevo.";
}

async function fetchStatistics(filters: Filters, signal: AbortSignal): Promise<QuarterlyStatistics> {
  const query = new URLSearchParams({ year: filters.year, quarter: String(filters.quarter), scope: filters.scope });
  if (filters.scope === "organization") query.set("organization_id", filters.organizationId);
  if (filters.scope === "project") query.set("project_id", filters.projectId);
  const response = await fetch(`/api/users/me/dashboard/statistics?${query.toString()}`, {
    method: "GET",
    credentials: "include",
    signal,
  });
  if (!response.ok) throw new StatisticsRequestError(response.status);
  let body: unknown;
  try {
    body = await response.json();
  } catch {
    throw new InvalidStatisticsResponseError();
  }
  if (!isQuarterlyStatistics(body) || body.year !== Number(filters.year) || body.quarter !== filters.quarter || body.scope !== filters.scope) {
    throw new InvalidStatisticsResponseError();
  }
  return body;
}

function formatMetric(value: number | null): string {
  return value === null ? "No disponible" : new Intl.NumberFormat("es-ES", { maximumFractionDigits: 2 }).format(value);
}

function formatDate(value: string): string {
  const [year, month, day] = value.split("-").map(Number);
  return new Intl.DateTimeFormat("es-ES", { day: "2-digit", month: "short", timeZone: "UTC" }).format(new Date(Date.UTC(year, month - 1, day)));
}

function coverageText(value: Coverage): string {
  return coverageLabels[value];
}

function splitPath(points: WeeklyPoint[], field: "completed_cumulative" | "required_cumulative", x: (index: number) => number, y: (value: number) => number): string[] {
  const segments: string[] = [];
  let current: string[] = [];
  points.forEach((point, index) => {
    const value = point[field];
    if (value === null) {
      if (current.length) segments.push(current.join(" "));
      current = [];
      return;
    }
    current.push(`${current.length ? "L" : "M"} ${x(index)} ${y(value)}`);
  });
  if (current.length) segments.push(current.join(" "));
  return segments;
}

function QuarterlyChart({ points, today }: { points: WeeklyPoint[]; today: string }) {
  const width = 760;
  const height = 300;
  const left = 52;
  const right = 20;
  const top = 18;
  const bottom = 48;
  const plotWidth = width - left - right;
  const plotHeight = height - top - bottom;
  const numericValues = points.flatMap((point) => [point.completed_cumulative, point.required_cumulative]).filter((value): value is number => value !== null);
  const max = Math.max(1, ...numericValues);
  const x = (index: number) => left + (points.length <= 1 ? plotWidth / 2 : (index / (points.length - 1)) * plotWidth);
  const y = (value: number) => top + plotHeight - (value / max) * plotHeight;
  const actualSegments = splitPath(points, "completed_cumulative", x, y);
  const requiredSegments = splitPath(points, "required_cumulative", x, y);
  const futureIndex = points.findIndex((point) => point.week_start > today);
  const actualCount = points.filter((point) => point.completed_cumulative !== null).length;
  const requiredCount = points.filter((point) => point.required_cumulative !== null).length;

  return (
    <>
      {actualCount < 2 && <p className="mb-2 text-xs text-muted">La serie real tiene menos de dos puntos disponibles para trazar una línea.</p>}
      {requiredCount < 2 && <p className="mb-2 text-xs text-muted">La referencia de ritmo tiene menos de dos puntos disponibles para trazar una línea.</p>}
      {!points.length ? <p className="text-sm text-muted">El servicio no devolvió puntos semanales.</p> : (
        <>
          <div className="overflow-x-auto">
            <svg aria-labelledby="quarterly-chart-title quarterly-chart-description" className="min-w-[640px] w-full" role="img" viewBox={`0 0 ${width} ${height}`}>
              <title id="quarterly-chart-title">Finalizaciones acumuladas y referencia matemática de ritmo</title>
              <desc id="quarterly-chart-description">Las líneas muestran las series semanales recibidas del backend. Los huecos corresponden a valores no disponibles. El área sombreada indica semanas futuras.</desc>
              {futureIndex >= 0 && <rect fill="currentColor" className="text-mist/60" x={x(futureIndex) - (points.length > 1 ? plotWidth / (points.length - 1) / 2 : 0)} y={top} width={width - right - (x(futureIndex) - (points.length > 1 ? plotWidth / (points.length - 1) / 2 : 0))} height={plotHeight} />}
              {[0, 1, 2, 3, 4].map((tick) => {
                const value = (max * tick) / 4;
                const tickY = y(value);
                return <g key={tick}><line x1={left} x2={width - right} y1={tickY} y2={tickY} stroke="currentColor" className="text-line" strokeDasharray={tick === 0 ? undefined : "2 4"} /><text x={left - 8} y={tickY + 4} textAnchor="end" className="fill-muted text-[11px]">{new Intl.NumberFormat("es-ES", { maximumFractionDigits: 1 }).format(value)}</text></g>;
              })}
              {actualSegments.map((segment, index) => <path key={`actual-${index}`} d={segment} fill="none" stroke="currentColor" className="text-primary" strokeWidth="3" />)}
              {requiredSegments.map((segment, index) => <path key={`required-${index}`} d={segment} fill="none" stroke="currentColor" className="text-brass-ink" strokeWidth="2.5" strokeDasharray="7 5" />)}
              {points.map((point, index) => <g key={`${point.week_start}-${index}`}>
                {point.completed_cumulative !== null && <circle cx={x(index)} cy={y(point.completed_cumulative)} r="4" fill="currentColor" className="text-primary" />}
                {point.required_cumulative !== null && <rect x={x(index) - 3.5} y={y(point.required_cumulative) - 3.5} width="7" height="7" fill="currentColor" className="text-brass-ink" />}
                {(index === 0 || index === points.length - 1 || index % 3 === 0) && <text x={x(index)} y={height - 17} textAnchor="middle" className="fill-muted text-[10px]">{formatDate(point.week_start)}</text>}
              </g>)}
            </svg>
          </div>
          <div className="mt-2 flex flex-wrap gap-x-6 gap-y-2 text-xs text-muted" aria-label="Leyenda del gráfico">
            <span className="inline-flex items-center gap-2"><span aria-hidden="true" className="inline-block h-0.5 w-6 bg-primary" /><span aria-hidden="true" className="size-2 rounded-full bg-primary" />Finalizaciones reales acumuladas</span>
            <span className="inline-flex items-center gap-2"><span aria-hidden="true" className="inline-block h-0.5 w-6 border-t-2 border-dashed border-brass-ink" /><span aria-hidden="true" className="size-2 bg-brass-ink" />Referencia matemática de ritmo acumulado</span>
            {futureIndex >= 0 && <span>Área sombreada: semanas futuras</span>}
          </div>
          <div className="mt-5 overflow-x-auto">
            <table className="w-full min-w-[680px] border-collapse text-left text-xs">
              <caption className="mb-2 text-left font-medium text-primary">Detalle semanal (los intervalos corresponden a week_start y week_end del servicio)</caption>
              <thead><tr className="border-b border-line text-muted"><th className="px-2 py-2">Semana</th><th className="px-2 py-2">Finalizadas acumuladas</th><th className="px-2 py-2">Pendientes en corte</th><th className="px-2 py-2">Referencia acumulada</th><th className="px-2 py-2">Ritmo semanal restante</th><th className="px-2 py-2">Cobertura</th></tr></thead>
              <tbody>{points.map((point) => <tr className="border-b border-line/70" key={`${point.week_start}-${point.week_end}`}><th className="px-2 py-2 font-normal text-primary">{formatDate(point.week_start)} – {formatDate(point.week_end)}{point.week_start > today ? " (futura)" : ""}</th><td className="px-2 py-2">{formatMetric(point.completed_cumulative)}</td><td className="px-2 py-2">{formatMetric(point.pending_at_cut)}</td><td className="px-2 py-2">{formatMetric(point.required_cumulative)}</td><td className="px-2 py-2">{formatMetric(point.required_per_week)}</td><td className="px-2 py-2">{coverageText(point.coverage)}</td></tr>)}</tbody>
            </table>
          </div>
        </>
      )}
    </>
  );
}

function QuarterlyStatistics({ active, organizations, organizationsStatus, projects, projectsStatus }: QuarterlyStatisticsProps) {
  const [currentPeriod, setCurrentPeriod] = useState(dateInMadrid);
  const [filters, setFilters] = useState<Filters>({ year: String(currentPeriod.year), quarter: currentPeriod.quarter, scope: "all", organizationId: "", projectId: "" });
  const [retryCount, setRetryCount] = useState(0);
  const [state, setState] = useState<StatisticsState>({ status: "loading", key: "" });
  const [today, setToday] = useState(currentPeriod.date);
  const organizationOptions = useMemo(() => [...organizations].sort((a, b) => a.name.localeCompare(b.name, "es")), [organizations]);
  const projectOptions = useMemo(() => [...projects].sort((a, b) => a.name.localeCompare(b.name, "es")), [projects]);
  const yearValue = Number(filters.year);
  const validYear = /^\d{4}$/.test(filters.year) && Number.isInteger(yearValue) && yearValue >= 1900 && yearValue <= currentPeriod.year;
  const futureQuarter = validYear && yearValue === currentPeriod.year && filters.quarter > currentPeriod.quarter;
  const needsOrganization = filters.scope === "organization";
  const needsProject = filters.scope === "project";
  const orgOptionsReady = organizationsStatus === "loaded";
  const projectOptionsReady = projectsStatus === "loaded";
  const missingScopeOption = (needsOrganization && !filters.organizationId) || (needsProject && !filters.projectId);
  const waitingForScopeOptions = (needsOrganization && organizationsStatus === "loading") || (needsProject && projectsStatus === "loading");
  const validSelection = !needsOrganization || organizationOptions.some((org) => String(org.id) === filters.organizationId);
  const validProjectSelection = !needsProject || projectOptions.some((project) => String(project.id) === filters.projectId);
  const canRequest = active && validYear && !futureQuarter && !waitingForScopeOptions && !missingScopeOption && validSelection && validProjectSelection && (needsOrganization ? orgOptionsReady : true) && (needsProject ? projectOptionsReady : true);
  const requestKey = [filters.year, filters.quarter, filters.scope, needsOrganization ? filters.organizationId : "", needsProject ? filters.projectId : ""].join(":");
  const visibleState = state.key === requestKey ? state : { status: "loading" as const, key: requestKey };

  useEffect(() => {
    const now = dateInMadrid();
    setCurrentPeriod(now);
    setToday(now.date);
    if (active) setState({ status: "loading", key: requestKey });
  }, [active, requestKey, retryCount]);

  useEffect(() => {
    if (!canRequest) {
      if (active && !waitingForScopeOptions) setState({ status: "loading", key: requestKey });
      return;
    }
    const controller = new AbortController();
    setState({ status: "loading", key: requestKey });
    void fetchStatistics(filters, controller.signal)
      .then((value) => {
        if (!controller.signal.aborted) setState({ status: "loaded", key: requestKey, value });
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted) setState({ status: "error", key: requestKey, message: errorMessage(error) });
      });
    return () => controller.abort();
  }, [canRequest, filters, requestKey, retryCount]);

  function update<K extends keyof Filters>(key: K, value: Filters[K]) {
    setFilters((current) => ({ ...current, [key]: value }));
  }

  function updateScope(scope: Scope) {
    setFilters((current) => ({ ...current, scope, organizationId: "", projectId: "" }));
  }

  const sectionClass = "rounded-md border border-line bg-paper p-5";
  const metricCards = visibleState.status === "loaded" ? [
    { label: "Ciclos totales", value: visibleState.value.total_cycles },
    { label: "Ciclos completados", value: visibleState.value.completed_cycles },
    { label: visibleState.value.period_complete ? "Pendientes al cierre" : "Pendientes al corte", value: visibleState.value.pending_at_close },
    { label: "Finalizaciones a tiempo", value: visibleState.value.completed_on_time_percent === null ? null : `${formatMetric(visibleState.value.completed_on_time_percent)}%` },
  ] : [];

  return (
    <section aria-labelledby="quarterly-statistics-title" className={sectionClass}>
      <div className="mb-4">
        <h2 className="text-xl font-semibold text-primary" id="quarterly-statistics-title">Estadísticas trimestrales</h2>
        <p className="mt-1 text-sm text-muted">Periodos naturales calculados en {state.status === "loaded" ? state.value.timezone : "Europe/Madrid"}.</p>
      </div>
      <div className="mb-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
        <label className="text-xs font-medium text-muted">Año
          <input aria-label="Año de estadísticas" className="mt-1 min-h-10 w-full rounded-sm border border-line bg-white px-3 text-sm text-primary focus-visible:outline-2 focus-visible:outline-brass-ink" max={currentPeriod.year} min={1900} onChange={(event) => update("year", event.target.value)} type="number" value={filters.year} />
        </label>
        <label className="text-xs font-medium text-muted">Trimestre
          <select aria-label="Trimestre de estadísticas" className="mt-1 min-h-10 w-full rounded-sm border border-line bg-white px-3 text-sm text-primary focus-visible:outline-2 focus-visible:outline-brass-ink" onChange={(event) => update("quarter", Number(event.target.value))} value={filters.quarter}>
            {[1, 2, 3, 4].map((quarter) => <option disabled={validYear && yearValue === currentPeriod.year && quarter > currentPeriod.quarter} key={quarter} value={quarter}>T{quarter}</option>)}
          </select>
        </label>
        <label className="text-xs font-medium text-muted">Ámbito
          <select aria-label="Ámbito de estadísticas" className="mt-1 min-h-10 w-full rounded-sm border border-line bg-white px-3 text-sm text-primary focus-visible:outline-2 focus-visible:outline-brass-ink" onChange={(event) => updateScope(event.target.value as Scope)} value={filters.scope}>
            <option value="all">Todas las tareas accesibles</option><option value="personal">Proyectos personales</option><option value="organization">Organización</option><option value="project">Proyecto</option>
          </select>
        </label>
        {needsOrganization && <label className="text-xs font-medium text-muted">Organización
          <select aria-label="Organización de estadísticas" className="mt-1 min-h-10 w-full rounded-sm border border-line bg-white px-3 text-sm text-primary focus-visible:outline-2 focus-visible:outline-brass-ink" disabled={!orgOptionsReady || organizationOptions.length === 0} onChange={(event) => update("organizationId", event.target.value)} value={filters.organizationId}>
            <option value="">Selecciona una organización</option>{organizationOptions.map((organization) => <option key={organization.id} value={organization.id}>{organization.name}</option>)}
          </select>
        </label>}
        {needsProject && <label className="text-xs font-medium text-muted">Proyecto
          <select aria-label="Proyecto de estadísticas" className="mt-1 min-h-10 w-full rounded-sm border border-line bg-white px-3 text-sm text-primary focus-visible:outline-2 focus-visible:outline-brass-ink" disabled={!projectOptionsReady || projectOptions.length === 0} onChange={(event) => update("projectId", event.target.value)} value={filters.projectId}>
            <option value="">Selecciona un proyecto</option>{projectOptions.map((project) => <option key={project.id} value={project.id}>{project.name}{project.organization_name ? ` · ${project.organization_name}` : " · Personal"}</option>)}
          </select>
        </label>}
      </div>

      {!validYear && <p className="mb-4 text-sm text-error" role="alert">Introduce un año válido entre 1900 y {currentPeriod.year}.</p>}
      {futureQuarter && <p className="mb-4 text-sm text-error" role="alert">No se pueden consultar trimestres futuros.</p>}
      {needsOrganization && organizationsStatus === "error" && <p className="mb-4 text-sm text-error" role="alert">No se pudieron cargar las organizaciones disponibles.</p>}
      {needsProject && projectsStatus === "error" && <p className="mb-4 text-sm text-error" role="alert">No se pudieron cargar los proyectos accesibles.</p>}
      {needsOrganization && organizationsStatus === "loading" && <p className="mb-4 text-sm text-muted" role="status">Cargando opciones de organización…</p>}
      {needsProject && projectsStatus === "loading" && <p className="mb-4 text-sm text-muted" role="status">Cargando opciones de proyecto…</p>}
      {needsOrganization && orgOptionsReady && organizationOptions.length > 0 && !filters.organizationId && <p className="mb-4 text-sm text-muted">Selecciona una organización para consultar sus estadísticas.</p>}
      {needsProject && projectOptionsReady && projectOptions.length > 0 && !filters.projectId && <p className="mb-4 text-sm text-muted">Selecciona un proyecto para consultar sus estadísticas.</p>}
      {needsOrganization && orgOptionsReady && organizationOptions.length === 0 && <p className="mb-4 text-sm text-muted">No hay organizaciones con opciones disponibles para este ámbito.</p>}
      {needsProject && projectOptionsReady && projectOptions.length === 0 && <p className="mb-4 text-sm text-muted">No hay proyectos accesibles disponibles para este ámbito.</p>}

      {active && canRequest && visibleState.status === "loading" && <p className="rounded border border-line px-4 py-5 text-sm text-muted" role="status">Cargando estadísticas…</p>}
      {active && canRequest && visibleState.status === "error" && <div className="rounded border border-error/30 p-4" role="alert"><p className="text-sm text-error">{visibleState.message}</p><button className="mt-3 min-h-9 rounded border border-line px-3 text-sm text-primary focus-visible:outline-2 focus-visible:outline-brass-ink" onClick={() => setRetryCount((count) => count + 1)} type="button">Reintentar</button></div>}
      {active && canRequest && visibleState.status === "loaded" && <>
        {!visibleState.value.period_complete && <p className="mb-4 rounded border border-brass/40 bg-mist/40 px-3 py-2 text-sm text-primary">El trimestre está en curso. Las cifras llegan hasta {new Intl.DateTimeFormat("es-ES", { dateStyle: "medium", timeStyle: "short", timeZone: visibleState.value.timezone }).format(new Date(visibleState.value.as_of))}.</p>}
        {visibleState.value.warnings.length > 0 && <ul aria-label="Advertencias sobre las estadísticas" className="mb-4 space-y-2" role="status">{visibleState.value.warnings.map((warning, index) => <li className="rounded border border-brass/40 bg-mist/40 px-3 py-2 text-sm text-primary" key={`${warning.code}-${index}`}>{warning.message}</li>)}</ul>}
        <div aria-label="Cobertura histórica" className="mb-4 flex flex-wrap gap-2 text-xs">{Object.entries(visibleState.value.coverage).map(([dimension, coverage]) => <span className={`rounded border px-2 py-1 ${coverage === "reliable" ? "border-line text-muted" : "border-brass/50 bg-mist/40 text-primary"}`} key={dimension}>{dimension.replaceAll("_", " ")}: {coverageText(coverage)}</span>)}</div>
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">{metricCards.map((metric) => <article className="rounded border border-line bg-canvas/40 p-4" key={metric.label}><h3 className="text-xs font-medium text-muted">{metric.label}</h3><p className="mt-2 text-2xl font-semibold text-primary">{metric.value === null ? "No disponible" : typeof metric.value === "string" ? metric.value : formatMetric(metric.value)}</p>{metric.label === "Finalizaciones a tiempo" && <p className="mt-1 text-xs text-muted">Comparables: {formatMetric(state.value.punctuality_comparable_count)} · Cobertura: {coverageText(state.value.coverage.due_date_snapshots)}</p>}</article>)}</div>
        {visibleState.value.total_cycles === 0 && visibleState.value.coverage.state_and_cycles === "reliable" && <p className="mt-4 text-sm text-muted">No hay ciclos elegibles en este ámbito y periodo.</p>}
        <div className="mt-5 grid gap-2 text-sm text-muted sm:grid-cols-2"><p>Carga arrastrada al inicio: <strong className="font-medium text-primary">{formatMetric(visibleState.value.load.carried_in)}</strong></p><p>Ciclos nuevos del periodo: <strong className="font-medium text-primary">{formatMetric(visibleState.value.load.new_cycles)}</strong></p></div>
        <section aria-labelledby="weekly-statistics-title" className="mt-6 border-t border-line pt-5"><h3 className="mb-3 text-base font-semibold text-primary" id="weekly-statistics-title">Evolución semanal</h3><QuarterlyChart points={visibleState.value.weekly} today={today} /></section>
      </>}
    </section>
  );
}

export default QuarterlyStatistics;
