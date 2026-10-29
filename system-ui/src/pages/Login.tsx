import { useState, type FormEvent } from "react";
import axios from "axios";
import {
  login,
  registerPersonalAccount,
  requestPasswordReset,
  resendVerification,
  resetPassword,
} from "../services/auth";

interface LoginProps {
  onSuccess: () => void;
  resetToken?: string;
  onResetComplete?: () => void;
}

type LoginMode = "login" | "register" | "reset-request" | "reset";

function Login({ onSuccess, resetToken, onResetComplete }: LoginProps) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [passwordConfirmation, setPasswordConfirmation] = useState("");
  const [mode, setMode] = useState<LoginMode>(resetToken ? "reset" : "login");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setNotice("");
    setLoading(true);

    try {
      if (mode === "reset-request") {
        await requestPasswordReset(username);
        setMode("login");
        setNotice("If an account exists for that email, a password reset link has been sent.");
      } else if (mode === "reset") {
        if (!resetToken) {
          setError("This password reset link is invalid or expired.");
          return;
        }
        if (password !== passwordConfirmation) {
          setError("Passwords do not match.");
          return;
        }
        await resetPassword(resetToken, password);
        setPassword("");
        setNotice("Your password was reset. You can now sign in.");
        onResetComplete?.();
        setMode("login");
      } else if (mode === "register") {
        if (password !== passwordConfirmation) {
          setError("Passwords do not match.");
          return;
        }
        await registerPersonalAccount(username, password);
        setMode("login");
        setPassword("");
        setPasswordConfirmation("");
        setNotice("If registration succeeded, a verification link was sent to your email. The link expires in one hour.");
      } else {
        await login(username, password);
        onSuccess();
      }
    } catch (caught) {
      const responseMessage = axios.isAxiosError(caught)
        ? caught.response?.data?.detail
        : null;
      setError(
        typeof responseMessage === "string"
          ? responseMessage
          : mode === "register"
            ? "Account registration failed. Check the email settings and try again."
            : mode === "reset-request" || mode === "reset"
              ? "Password reset could not be completed. Try again later."
              : "Invalid username/email or password.",
      );
    } finally {
      setLoading(false);
    }
  }

  async function handleResendVerification() {
    setError("");
    setNotice("");
    setLoading(true);
    try {
      await resendVerification(username);
      setNotice("If an unverified account exists for that email, a verification link has been sent.");
    } catch (caught) {
      const responseMessage = axios.isAxiosError(caught)
        ? caught.response?.data?.detail
        : null;
      setError(
        typeof responseMessage === "string"
          ? responseMessage
          : "Could not request a verification email. Try again later.",
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <div
      style={{
        minHeight: "100vh",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: "#071018",
        color: "#fff",
        fontFamily: "sans-serif",
      }}
    >
      <style>{`
        .cvis-login-form input.cvis-login-input,
        .cvis-login-form input.cvis-login-input:-webkit-autofill,
        .cvis-login-form input.cvis-login-input:-webkit-autofill:hover,
        .cvis-login-form input.cvis-login-input:-webkit-autofill:focus {
          color: #111827 !important;
          -webkit-text-fill-color: #111827 !important;
          caret-color: #111827 !important;
          background-color: #fff !important;
          color-scheme: light;
        }
        .cvis-login-form input.cvis-login-input:-webkit-autofill {
          box-shadow: 0 0 0 1000px #fff inset !important;
        }
      `}</style>
      <form
        className="cvis-login-form"
        onSubmit={handleSubmit}
        style={{
          width: "360px",
          padding: "32px",
          border: "1px solid #294050",
          borderRadius: "12px",
          background: "#0c1720",
          boxSizing: "border-box",
        }}
      >
        <h1 style={{ marginTop: 0 }}>CVIS System UI</h1>
        <p style={{ color: "#8fa5b5" }}>
          {mode === "register"
            ? "Create a personal account. Email verification is required."
            : mode === "reset-request"
              ? "Enter your email to receive a password reset link."
              : mode === "reset"
                ? "Choose a new password for your account."
                : "Sign in with your account"}
        </p>

        {mode !== "reset" && (
          <label>
            {mode === "register" || mode === "reset-request" ? "Email" : "Email or admin username"}
            <input
              className="cvis-login-input"
              type={mode === "register" || mode === "reset-request" ? "email" : "text"}
              value={username}
              onChange={(event) => {
                setUsername(event.target.value);
                setError("");
                setNotice("");
              }}
              autoComplete={mode === "register" || mode === "reset-request" ? "email" : "username"}
              required
              style={{
                display: "block",
                width: "100%",
                marginTop: "8px",
                marginBottom: "16px",
                padding: "10px",
                boxSizing: "border-box",
                color: "#111827",
                backgroundColor: "#fff",
                WebkitTextFillColor: "#111827",
                caretColor: "#111827",
                colorScheme: "light",
              }}
            />
          </label>
        )}

        {mode !== "reset-request" && (
          <label>
            {mode === "register" || mode === "reset"
              ? "New password (at least 12 characters)"
              : "Password"}
            <input
            className="cvis-login-input"
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            minLength={mode === "register" || mode === "reset" ? 12 : undefined}
            maxLength={128}
            autoComplete={mode === "register" || mode === "reset" ? "new-password" : "current-password"}
            required
            style={{
              display: "block",
              width: "100%",
              marginTop: "8px",
              marginBottom: "16px",
              padding: "10px",
              boxSizing: "border-box",
              color: "#111827",
              backgroundColor: "#fff",
              WebkitTextFillColor: "#111827",
              caretColor: "#111827",
              colorScheme: "light",
            }}
            />
          </label>
        )}

        {(mode === "register" || mode === "reset") && (
          <label>
            Confirm password
            <input
              className="cvis-login-input"
              type="password"
              value={passwordConfirmation}
              onChange={(event) => setPasswordConfirmation(event.target.value)}
              autoComplete="new-password"
              required
              maxLength={128}
              style={{
                display: "block",
                width: "100%",
                marginTop: "8px",
                marginBottom: "16px",
                padding: "10px",
                boxSizing: "border-box",
                color: "#111827",
                backgroundColor: "#fff",
                WebkitTextFillColor: "#111827",
                caretColor: "#111827",
                colorScheme: "light",
              }}
            />
          </label>
        )}

        {error && (
          <div role="alert" style={{ color: "#ff7777", marginBottom: "16px" }}>
            {error}
          </div>
        )}
        {notice && (
          <div role="status" style={{ color: "#8fe4b5", marginBottom: "16px" }}>
            {notice}
          </div>
        )}

        <button
          type="submit"
          disabled={loading}
          style={{
            width: "100%",
            padding: "11px",
            cursor: loading ? "wait" : "pointer",
          }}
        >
          {loading
            ? mode === "register"
              ? "CREATING ACCOUNT..."
              : mode === "reset-request"
                ? "SENDING LINK..."
                : mode === "reset"
                  ? "RESETTING PASSWORD..."
                  : "AUTHENTICATING..."
            : mode === "register"
              ? "CREATE ACCOUNT"
              : mode === "reset-request"
                ? "SEND RESET LINK"
                : mode === "reset"
                  ? "RESET PASSWORD"
                  : "LOGIN"}
        </button>
        <div style={{ display: "grid", gap: 8, marginTop: 14 }}>
          {mode === "login" && (
            <>
              <button
                type="button"
                disabled={loading}
                onClick={() => {
                  setMode("register");
                  setPassword("");
                  setPasswordConfirmation("");
                  setError("");
                  setNotice("");
                }}
              >
                Create personal account
              </button>
              <button
                type="button"
                disabled={loading || !username.trim()}
                onClick={() => {
                  setMode("reset-request");
                  setPassword("");
                  setError("");
                  setNotice("");
                }}
              >
                Forgot password?
              </button>
            </>
          )}
          {(mode === "register" || mode === "reset-request" || mode === "reset") && (
            <button
              type="button"
              disabled={loading}
              onClick={() => {
                setMode("login");
                setPassword("");
                setPasswordConfirmation("");
                setError("");
                setNotice("");
              }}
            >
              Back to sign in
            </button>
          )}
          {mode === "login" && (
            <button type="button" disabled={loading || !username.trim()} onClick={() => void handleResendVerification()}>
              Resend verification email
            </button>
          )}
        </div>
      </form>
    </div>
  );
}

export default Login;
