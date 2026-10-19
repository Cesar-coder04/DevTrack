import { useState, type FormEvent } from "react";
import { isUserProfile, type UserProfile } from "./userProfile";

interface LoginPageProps {
  onAuthenticated: (profile: UserProfile) => void;
}

function BlueprintIllustration() {
  return (
    <svg
      aria-hidden="true"
      className="h-auto w-full max-w-md text-brass"
      fill="none"
      viewBox="0 0 480 300"
    >
      <g opacity="0.58" stroke="currentColor" strokeWidth="1">
        <path d="M72 236h322M110 255h270M132 236V89l108-50 108 50v147" />
        <path d="M132 89h216M186 64v172M240 39v197M294 64v172" />
        <path d="m132 89 108 50 108-50M132 163l108 50 108-50" />
        <path d="m186 64 108 50M294 64l-108 50" />
        <path d="M99 89h-14m263 0h14M240 25V13m0 239v13" />
        <path d="M120 78 108 66m240 12 12-12M120 247l-12 12m240-12 12 12" />
        <path d="M99 89v147m-5-147h10m-10 147h10" />
        <path d="M360 89v147m-5-147h10m-10 147h10" />
        <path d="M156 108v41m168-41v41M156 149h168" />
        <path d="M173 236v-50l67 31 67-31v50" />
        <path d="M216 125v44m48-44v44" />
        <circle cx="240" cy="139" r="3" fill="currentColor" stroke="none" />
        <circle cx="240" cy="213" r="3" fill="currentColor" stroke="none" />
      </g>
      <g
        fill="currentColor"
        fontFamily="monospace"
        fontSize="9"
        letterSpacing="1.2"
      >
        <text x="60" y="165" transform="rotate(-90 60 165)">
          ELEVATION / 01
        </text>
        <text x="202" y="284">SECTION A—A</text>
        <text x="365" y="77">+ 04.20</text>
      </g>
      <path
        d="M214 139h52M240 113v52"
        stroke="currentColor"
        strokeWidth="1.5"
      />
    </svg>
  );
}

function LoginPage({ onAuthenticated }: LoginPageProps) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setIsSubmitting(true);

    try {
      const formData = new URLSearchParams({ username, password });
      const loginResponse = await fetch("/api/auth/cookie-login", {
        method: "POST",
        headers: {
          "Content-Type": "application/x-www-form-urlencoded",
        },
        body: formData,
        credentials: "include",
      });

      if (loginResponse.status !== 204) {
        if (loginResponse.status === 401) {
          setError("El nombre de usuario o la contraseña no son correctos.");
        } else if (loginResponse.status === 403) {
          setError(
            "No se pudo autorizar el acceso. Comprueba que la cuenta esté activa y que el origen esté permitido.",
          );
        } else if (loginResponse.status === 422) {
          setError("Revisa los campos e inténtalo de nuevo.");
        } else {
          setError("No se pudo iniciar sesión. Inténtalo de nuevo.");
        }
        return;
      }

      const profileResponse = await fetch("/api/users/me", {
        method: "GET",
        credentials: "include",
      });

      if (!profileResponse.ok) {
        setError(
          "El acceso se aceptó, pero no se pudo confirmar la sesión. Inténtalo de nuevo.",
        );
        return;
      }

      const responseBody: unknown = await profileResponse.json();
      if (!isUserProfile(responseBody)) {
        setError(
          "El acceso se aceptó, pero el perfil recibido no permitió confirmar la sesión.",
        );
        return;
      }

      setPassword("");
      onAuthenticated(responseBody);
    } catch {
      setError(
        "No se pudo conectar con el servicio. Comprueba la conexión e inténtalo de nuevo.",
      );
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <main className="min-h-screen bg-ivory text-graphite lg:grid lg:grid-cols-[minmax(0,0.92fr)_minmax(0,1.08fr)]">
      <aside className="relative flex min-h-60 flex-col justify-between overflow-hidden bg-graphite px-6 py-6 text-ivory sm:px-10 sm:py-8 lg:min-h-screen lg:px-14 lg:py-12">
        <div className="relative z-10">
          <a
            aria-label="DevTrack"
            className="inline-flex items-center gap-3 rounded-sm text-ivory focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-brass"
            href="/"
          >
            <span
              aria-hidden="true"
              className="grid size-9 place-items-center border border-brass/70 font-mono text-sm text-brass"
            >
              D
            </span>
            <span className="text-xl font-semibold tracking-tight">
              DevTrack
            </span>
          </a>
          <p className="mt-6 max-w-[42%] text-sm leading-6 text-ivory/80 sm:mt-8 sm:text-base lg:mt-10 lg:max-w-md">
            Planifica con precisión.
            <br />
            Avanza con claridad.
          </p>
        </div>

        <div className="pointer-events-none absolute inset-x-[38%] top-24 flex justify-center opacity-70 sm:inset-x-[40%] sm:top-28 lg:inset-x-8 lg:top-1/2 lg:-translate-y-1/2">
          <BlueprintIllustration />
        </div>

        <p className="relative z-10 mt-auto pt-8 font-mono text-[10px] tracking-[0.18em] text-ivory/60">
          TECHNICAL PRECISION
        </p>
      </aside>

      <section className="flex min-h-[calc(100vh-15rem)] items-center justify-center px-6 py-12 sm:px-10 lg:min-h-screen lg:px-12 lg:py-16">
        <div className="w-full max-w-md">
          <p className="mb-4 font-mono text-xs tracking-[0.14em] text-muted">
            ESPACIO DE TRABAJO
          </p>
          <h1 className="text-3xl font-semibold tracking-tight text-graphite sm:text-4xl">
            Iniciar sesión
          </h1>
          <p className="mt-3 text-sm leading-6 text-muted">
            Introduce tus credenciales para continuar.
          </p>

          <form
            className="mt-8 space-y-5"
            onSubmit={handleSubmit}
            aria-busy={isSubmitting}
          >
            <div className="space-y-2">
              <label
                className="block text-sm font-medium text-graphite"
                htmlFor="username"
              >
                Nombre de usuario
              </label>
              <input
                autoComplete="username"
                className="min-h-12 w-full rounded-md border border-steel/50 bg-paper px-4 py-3 text-base text-graphite placeholder:text-muted focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brass-ink disabled:cursor-not-allowed disabled:opacity-60"
                id="username"
                name="username"
                onChange={(event) => setUsername(event.target.value)}
                required
                autoCapitalize="none"
                spellCheck={false}
                value={username}
                disabled={isSubmitting}
              />
            </div>

            <div className="space-y-2">
              <label
                className="block text-sm font-medium text-graphite"
                htmlFor="password"
              >
                Contraseña
              </label>
              <div className="flex min-h-12 overflow-hidden rounded-md border border-steel/50 bg-paper focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-brass-ink">
                <input
                  autoComplete="current-password"
                  className="min-w-0 flex-1 bg-transparent px-4 py-3 text-base text-graphite placeholder:text-muted focus:outline-none disabled:cursor-not-allowed disabled:opacity-60"
                  id="password"
                  name="password"
                  onChange={(event) => setPassword(event.target.value)}
                  required
                  type={showPassword ? "text" : "password"}
                  value={password}
                  disabled={isSubmitting}
                />
                <button
                  aria-label={
                    showPassword ? "Ocultar contraseña" : "Mostrar contraseña"
                  }
                  aria-pressed={showPassword}
                  className="shrink-0 px-4 text-sm font-medium text-brass-ink underline-offset-4 hover:underline focus-visible:outline-2 focus-visible:outline-offset-[-4px] focus-visible:outline-brass-ink disabled:cursor-not-allowed disabled:opacity-60"
                  disabled={isSubmitting}
                  onClick={() => setShowPassword((visible) => !visible)}
                  type="button"
                >
                  {showPassword ? "Ocultar" : "Mostrar"}
                </button>
              </div>
            </div>

            {error && (
              <p
                className="rounded-md border border-error/40 bg-paper px-4 py-3 text-sm leading-6 text-error"
                role="alert"
              >
                {error}
              </p>
            )}

            <button
              className="inline-flex min-h-12 w-full items-center justify-center gap-3 rounded-md bg-graphite px-5 py-3 text-sm font-semibold text-ivory transition-colors hover:bg-graphite/90 focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-brass-ink disabled:cursor-wait disabled:opacity-65"
              disabled={isSubmitting || !username.trim() || !password}
              type="submit"
            >
              {isSubmitting && (
                <span
                  aria-hidden="true"
                  className="size-4 animate-spin rounded-full border-2 border-ivory/40 border-t-ivory motion-reduce:animate-none"
                />
              )}
              {isSubmitting ? "Comprobando acceso…" : "Iniciar sesión"}
            </button>
          </form>
        </div>
      </section>
    </main>
  );
}

export default LoginPage;
