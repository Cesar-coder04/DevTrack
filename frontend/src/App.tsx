function BlueprintMark() {
  return (
    <svg
      aria-hidden="true"
      className="size-7 shrink-0"
      fill="none"
      viewBox="0 0 28 28"
    >
      <path
        d="M4 4h20v20H4zM9 4v20M4 9h20"
        stroke="currentColor"
        strokeWidth="1.5"
      />
      <path d="M9 9h10v10H9z" stroke="currentColor" strokeWidth="1.5" />
      <path d="M14 9v10m-5-5h10" stroke="currentColor" strokeWidth="1" />
    </svg>
  );
}

function App() {
  return (
    <div className="min-h-screen bg-canvas text-ink">
      <header className="mx-auto flex w-full max-w-6xl items-center justify-between px-6 py-6 sm:px-8">
        <a
          aria-label="DevTrack, inicio"
          className="inline-flex items-center gap-3 rounded-md text-primary focus-visible:outline-2 focus-visible:outline-offset-4"
          href="/"
        >
          <span className="text-brass">
            <BlueprintMark />
          </span>
          <span className="text-lg font-semibold tracking-tight">DevTrack</span>
        </a>
        <span className="font-mono text-xs tracking-[0.12em] text-muted">
          TECHNICAL PRECISION
        </span>
      </header>

      <main className="mx-auto grid w-full max-w-6xl flex-1 content-center gap-10 px-6 pb-16 pt-8 sm:px-8 lg:grid-cols-[minmax(0,1.2fr)_minmax(18rem,0.8fr)] lg:gap-16">
        <section
          aria-labelledby="welcome-title"
          className="flex flex-col justify-center"
        >
          <p className="mb-5 font-mono text-xs font-medium tracking-[0.16em] text-muted">
            WORKSPACE / 001
          </p>
          <h1
            className="max-w-2xl text-5xl font-semibold tracking-[-0.045em] text-primary sm:text-6xl"
            id="welcome-title"
          >
            Trabajo técnico,
            <br />
            <span className="text-brass-ink">con claridad.</span>
          </h1>
          <p className="mt-6 max-w-xl text-base leading-7 text-muted sm:text-lg">
            Una base precisa y ordenada para la experiencia DevTrack. La
            interfaz está preparada para conectarse con el backend.
          </p>
        </section>

        <section
          aria-label="Estado de la aplicación"
          className="self-center rounded-[10px] border border-line bg-surface p-6 sm:p-8"
        >
          <div className="flex items-center gap-3">
            <span
              aria-hidden="true"
              className="size-2 rounded-full bg-success"
            />
            <p className="text-sm font-medium text-primary">
              Frontend preparado
            </p>
          </div>
          <div className="my-6 border-t border-line" />
          <dl className="space-y-4">
            <div className="flex items-baseline justify-between gap-4">
              <dt className="text-sm text-muted">Interfaz</dt>
              <dd className="font-mono text-xs text-primary">
                React / TypeScript
              </dd>
            </div>
            <div className="flex items-baseline justify-between gap-4">
              <dt className="text-sm text-muted">Desarrollo</dt>
              <dd className="font-mono text-xs text-primary">
                Vite / Tailwind
              </dd>
            </div>
            <div className="flex items-baseline justify-between gap-4">
              <dt className="text-sm text-muted">API local</dt>
              <dd className="font-mono text-xs text-primary">
                /api
              </dd>
            </div>
          </dl>
        </section>
      </main>

      <footer className="mx-auto w-full max-w-6xl px-6 pb-6 sm:px-8">
        <p className="border-t border-line pt-4 text-xs text-muted">
          DevTrack · Base de interfaz
        </p>
      </footer>
    </div>
  );
}

export default App;
