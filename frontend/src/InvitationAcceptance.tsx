import { useRef, useState } from "react";

export type InvitationIntent =
  | { status: "valid"; invitationId: number; token: string }
  | { status: "invalid"; message: string };

interface InvitationAcceptanceProps {
  intent: InvitationIntent;
  onAuthenticationRequired: () => void;
  onReturnToDashboard: () => void;
}

type AcceptanceResult = {
  message: string;
  isFinal: boolean;
};

function InvitationAcceptance({
  intent,
  onAuthenticationRequired,
  onReturnToDashboard,
}: InvitationAcceptanceProps) {
  const requestInFlight = useRef(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [result, setResult] = useState<AcceptanceResult | null>(null);

  async function acceptInvitation() {
    if (intent.status !== "valid" || requestInFlight.current) {
      return;
    }

    requestInFlight.current = true;
    setIsSubmitting(true);
    setResult(null);

    try {
      const response = await fetch(
        `/api/users/me/invitations/${intent.invitationId}/accept`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          credentials: "include",
          body: JSON.stringify({ token: intent.token }),
        },
      );

      if (response.status === 200) {
        setResult({
          message: "La invitación se aceptó correctamente.",
          isFinal: true,
        });
      } else if (response.status === 401) {
        onAuthenticationRequired();
      } else if (response.status === 400) {
        setResult({
          message: "La invitación ha caducado y ya no se puede aceptar.",
          isFinal: true,
        });
      } else if (response.status === 403) {
        setResult({
          message:
            "La solicitud no está autorizada desde este origen. Contacta con soporte si el problema continúa.",
          isFinal: true,
        });
      } else if (response.status === 404) {
        setResult({
          message:
            "No se pudo validar el enlace con esta cuenta. Comprueba que has iniciado sesión con el correo destinatario y que el enlace es válido.",
          isFinal: true,
        });
      } else if (response.status === 409) {
        setResult({
          message:
            "La invitación fue revocada, ya se procesó anteriormente o tu cuenta ya pertenece a la organización.",
          isFinal: true,
        });
      } else if (response.status === 422) {
        setResult({
          message: "El enlace o los datos de la invitación no son válidos.",
          isFinal: true,
        });
      } else {
        setResult({
          message:
            "No se pudo completar la aceptación. Inténtalo de nuevo más tarde.",
          isFinal: false,
        });
      }
    } catch {
      setResult({
        message:
          "No se pudo conectar con el servicio. Comprueba la conexión e inténtalo de nuevo.",
        isFinal: false,
      });
    } finally {
      requestInFlight.current = false;
      setIsSubmitting(false);
    }
  }

  const message =
    intent.status === "invalid"
      ? intent.message
      : result?.message ??
        "Confirma la invitación para solicitar acceso a la organización.";

  return (
    <main className="grid min-h-screen place-items-center bg-canvas px-6 py-12 text-ink">
      <section
        aria-labelledby="invitation-title"
        className="w-full max-w-md rounded-md border border-line bg-surface p-6"
      >
        <h1
          className="text-xl font-semibold text-primary"
          id="invitation-title"
        >
          Invitación a una organización
        </h1>
        <p
          className="mt-3 text-sm leading-6 text-muted"
          role={result || intent.status === "invalid" ? "status" : undefined}
        >
          {message}
        </p>

        {intent.status === "valid" && !result && (
          <button
            className="mt-6 min-h-11 rounded-md bg-graphite px-5 py-3 text-sm font-semibold text-ivory focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-brass-ink disabled:cursor-not-allowed disabled:opacity-60"
            disabled={isSubmitting}
            onClick={() => void acceptInvitation()}
            type="button"
          >
            {isSubmitting ? "Aceptando…" : "Aceptar invitación"}
          </button>
        )}

        {result && !result.isFinal && intent.status === "valid" && (
          <button
            className="mt-6 min-h-11 rounded-md bg-graphite px-5 py-3 text-sm font-semibold text-ivory focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-brass-ink"
            disabled={isSubmitting}
            onClick={() => void acceptInvitation()}
            type="button"
          >
            {isSubmitting ? "Reintentando…" : "Reintentar"}
          </button>
        )}

        {(intent.status === "invalid" || result?.isFinal) && (
          <button
            className="mt-6 min-h-11 rounded-md border border-line px-5 py-3 text-sm font-semibold text-primary focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-brass-ink"
            onClick={onReturnToDashboard}
            type="button"
          >
            Volver a mis proyectos
          </button>
        )}
      </section>
    </main>
  );
}

export default InvitationAcceptance;
