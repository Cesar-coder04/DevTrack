import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import type { InvitationIntent } from "./InvitationAcceptance";
import "./index.css";

function captureInvitationIntent(): InvitationIntent | null {
  if (window.location.pathname !== "/invitations/accept") {
    return null;
  }

  const params = new URLSearchParams(window.location.search);
  const invitationIds = params.getAll("invitation_id");
  const tokens = params.getAll("token");
  let intent: InvitationIntent;

  if (invitationIds.length !== 1 || tokens.length !== 1) {
    intent = {
      status: "invalid",
      message:
        "El enlace de invitación está incompleto o no es válido. Solicita un nuevo enlace.",
    };
  } else {
    const invitationIdText = invitationIds[0];
    const token = tokens[0];
    const invitationId = Number(invitationIdText);

    if (
      !/^[1-9]\d*$/.test(invitationIdText) ||
      !Number.isSafeInteger(invitationId) ||
      token.length < 32 ||
      token.length > 256
    ) {
      intent = {
        status: "invalid",
        message:
          "El enlace de invitación está incompleto o no es válido. Solicita un nuevo enlace.",
      };
    } else {
      intent = { status: "valid", invitationId, token };
    }
  }

  window.history.replaceState(window.history.state, "", "/");
  return intent;
}

const invitationIntent = captureInvitationIntent();
const rootElement = document.getElementById("root");

if (!rootElement) {
  throw new Error("Missing root element.");
}

createRoot(rootElement).render(
  <StrictMode>
    <App invitationIntent={invitationIntent} />
  </StrictMode>,
);
