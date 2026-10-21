export interface ProjectSummary {
  id: number;
  organization_id: number | null;
  name: string;
  description: string | null;
  status: string;
  created_at: string;
  organization_name: string | null;
}

interface ProjectCardProps {
  project: ProjectSummary;
  onSelect: (project: ProjectSummary) => void;
}

const statusLabels: Record<string, string> = {
  active: "Activo",
  in_progress: "En curso",
  completed: "Completado",
};

function ProjectCard({ project, onSelect }: ProjectCardProps) {
  const formattedCreatedAt = new Intl.DateTimeFormat("es", {
    dateStyle: "medium",
  }).format(new Date(project.created_at));
  const rawStatus = project.status.trim();
  const statusLabel =
    statusLabels[rawStatus] || rawStatus || "Estado no informado";
  const organizationName = project.organization_name?.trim();

  return (
    <article className="h-full min-h-56">
      <button
        aria-label={`Abrir proyecto ${project.name}`}
        className="flex h-full min-h-56 w-full flex-col rounded-md border border-line bg-paper p-5 text-left transition-colors hover:border-steel/40 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brass-ink"
        onClick={() => onSelect(project)}
        type="button"
      >
        <span className="flex w-full items-start justify-between gap-4">
          <span className="line-clamp-2 min-w-0 break-words text-lg font-semibold leading-6 text-primary">
            {project.name}
          </span>
          <span className="shrink-0 rounded-sm border border-line bg-mist/50 px-2 py-1 text-xs text-steel">
            {statusLabel}
          </span>
        </span>

        <span className="mt-4 line-clamp-3 w-full break-words text-sm leading-6 text-muted">
          {project.description?.trim() || "Sin descripción."}
        </span>

        <span className="mt-4 flex w-full min-w-0 items-center gap-2 text-xs text-brass">
          {organizationName ? (
            <>
              <svg
                aria-hidden="true"
                className="size-4 shrink-0 text-steel"
                fill="none"
                stroke="currentColor"
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth="1.5"
                viewBox="0 0 24 24"
              >
                <rect x="3" y="7" width="18" height="14" rx="1" />
                <path d="M8 7V4h8v3M3 12h18m-11 0v2h4v-2" />
              </svg>
              <span
                className="min-w-0 flex-1 break-words"
                title={organizationName}
              >
                {organizationName}
              </span>
            </>
          ) : (
            <span className="min-w-0 break-words">Proyecto personal</span>
          )}
        </span>

        <span className="mt-auto w-full border-t border-line pt-4 text-xs text-muted">
          Creado{" "}
          <time dateTime={project.created_at}>{formattedCreatedAt}</time>
        </span>
      </button>
    </article>
  );
}

export default ProjectCard;
