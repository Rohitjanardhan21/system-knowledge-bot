import { useEffect, useRef, useState } from "react";
import Dashboard from "./pages/Dashboard";
import Login from "./pages/Login";
import { isAuthenticated, logout, verifyEmail } from "./services/auth";

function App() {
  const [verificationToken, setVerificationToken] = useState(
    () => new URLSearchParams(window.location.hash.slice(1)).get("verify-email"),
  );
  const [passwordResetToken, setPasswordResetToken] = useState(
    () => new URLSearchParams(window.location.hash.slice(1)).get("reset-password"),
  );
  const [verificationState, setVerificationState] = useState<
    "checking" | "success" | "error" | null
  >(() => verificationToken ? "checking" : null);
  const verificationStarted = useRef(false);
  const [access, setAccess] = useState<"checking" | "desktop" | "authenticated" | "login">(
    () => isAuthenticated()
      ? "authenticated"
      : window.pywebview?.api?.get_api_key ? "desktop" : "checking",
  );

  useEffect(() => {
    if (!verificationToken || verificationStarted.current) return;
    verificationStarted.current = true;
    window.history.replaceState(null, "", `${window.location.pathname}${window.location.search}`);
    verifyEmail(verificationToken)
      .then(() => setVerificationState("success"))
      .catch(() => setVerificationState("error"));
  }, [verificationToken]);

  useEffect(() => {
    if (access !== "checking") {
      return;
    }

    const resolveAccess = () => {
      setAccess(window.pywebview?.api?.get_api_key ? "desktop" : "login");
    };

    window.addEventListener("pywebviewready", resolveAccess, { once: true });
    const timeout = window.setTimeout(resolveAccess, 250);

    return () => {
      window.removeEventListener("pywebviewready", resolveAccess);
      window.clearTimeout(timeout);
    };
  }, [access]);

  if (verificationState) {
    const verified = verificationState === "success";
    return (
      <main style={styles.verification}>
        <h1>Email verification</h1>
        <p role="status">
          {verificationState === "checking"
            ? "Verifying your email…"
            : verified
              ? "Your email is verified. You can now sign in."
              : "This verification link is invalid, expired, or already used. Request a new link from sign-in."}
        </p>
        {verificationState !== "checking" && (
          <button
            type="button"
            onClick={() => {
              setVerificationState(null);
              setVerificationToken(null);
              setAccess("login");
            }}
          >
            Continue to sign in
          </button>
        )}
      </main>
    );
  }

  if (passwordResetToken) {
    return (
      <Login
        resetToken={passwordResetToken}
        onResetComplete={() => {
          window.history.replaceState(null, "", `${window.location.pathname}${window.location.search}`);
          setPasswordResetToken(null);
        }}
        onSuccess={() => setAccess("authenticated")}
      />
    );
  }

  if (access === "checking") {
    return <div role="status" aria-live="polite">Starting CVIS…</div>;
  }

  if (access === "login") {
    return <Login onSuccess={() => setAccess("authenticated")} />;
  }

  return (
    <Dashboard
      onLogout={access === "authenticated"
        ? () => {
            void logout()
              .catch((error) => {
                console.error("[CVIS] Server-side logout could not be confirmed:", error);
              })
              .finally(() => setAccess("login"));
          }
        : undefined}
    />
  );
}

const styles = {
  verification: {
    minHeight: "100vh",
    display: "grid",
    alignContent: "center",
    justifyItems: "center",
    gap: 12,
    padding: 24,
    background: "#071018",
    color: "#e7f1fb",
    fontFamily: "system-ui, sans-serif",
    textAlign: "center" as const,
  },
};

export default App;
