import { useEffect, useState } from "react";
import Dashboard from "./Dashboard";
import LoginPage from "./LoginPage";
import { isUserProfile, type UserProfile } from "./userProfile";

type SessionState =
  | { status: "checking" }
  | { status: "authenticated"; profile: UserProfile }
  | { status: "unauthenticated" }
  | { status: "error"; message: string };

let sessionCheckInFlight: Promise<SessionState> | null = null;

function checkSession(): Promise<SessionState> {
  if (!sessionCheckInFlight) {
    const request: Promise<SessionState> = (async (): Promise<SessionState> => {
      try {
        const response = await fetch("/api/users/me", {
          method: "GET",
          credentials: "include",
        });

        if (response.status === 401) {
          return { status: "unauthenticated" };
        }

        if (!response.ok) {
          return {
            status: "error",
            message:
              "No se pudo comprobar la sesión. Comprueba el servicio e inténtalo de nuevo.",
          };
        }

        let responseBody: unknown;
        try {
          responseBody = await response.json();
        } catch {
          return {
            status: "error",
            message:
              "El servicio respondió con un formato que no se pudo validar.",
          };
        }

        if (!isUserProfile(responseBody)) {
          return {
            status: "error",
            message:
              "El servicio respondió, pero no se pudo validar el perfil recibido.",
          };
        }

        return { status: "authenticated", profile: responseBody };
      } catch {
        return {
          status: "error",
          message:
            "No se pudo conectar con el servicio para comprobar la sesión. Comprueba la conexión e inténtalo de nuevo.",
        };
      }
    })().finally(() => {
      sessionCheckInFlight = null;
    });
    sessionCheckInFlight = request;
  }

  return sessionCheckInFlight;
}

function App() {
  const [sessionState, setSessionState] = useState<SessionState>({
    status: "checking",
  });
  const [retryCount, setRetryCount] = useState(0);

  useEffect(() => {
    let isMounted = true;
    setSessionState({ status: "checking" });

    void checkSession().then((result) => {
      if (isMounted) {
        setSessionState(result);
      }
    });

    return () => {
      isMounted = false;
    };
  }, [retryCount]);

  if (sessionState.status === "checking") {
    return (
      <main
        aria-live="polite"
        className="grid min-h-screen place-items-center bg-canvas px-6 text-ink"
        role="status"
      >
        <p className="text-sm text-muted">Comprobando sesión…</p>
      </main>
    );
  }

  if (sessionState.status === "authenticated") {
    return <Dashboard profile={sessionState.profile} />;
  }

  if (sessionState.status === "error") {
    return (
      <main className="grid min-h-screen place-items-center bg-canvas px-6 text-ink">
        <section
          aria-labelledby="session-error-title"
          className="w-full max-w-md rounded-md border border-line bg-surface p-6"
        >
          <h1
            className="text-lg font-semibold text-primary"
            id="session-error-title"
          >
            No se pudo comprobar la sesión
          </h1>
          <p className="mt-3 text-sm leading-6 text-muted" role="alert">
            {sessionState.message}
          </p>
          <button
            className="mt-6 min-h-11 rounded-md bg-graphite px-5 py-3 text-sm font-semibold text-ivory focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-brass-ink"
            onClick={() => {
              setSessionState({ status: "checking" });
              setRetryCount((count) => count + 1);
            }}
            type="button"
          >
            Reintentar
          </button>
        </section>
      </main>
    );
  }

  return (
    <LoginPage
      onAuthenticated={(profile) =>
        setSessionState({ status: "authenticated", profile })
      }
    />
  );
}

export default App;
