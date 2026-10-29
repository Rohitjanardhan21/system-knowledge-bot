import { useState, type FormEvent } from "react";
import axios from "axios";
import {
  login,
  registerPersonalAccount,
  resendVerification,
} from "../services/auth";

interface LoginProps {
  onSuccess: () => void;
}

function Login({ onSuccess }: LoginProps) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [passwordConfirmation, setPasswordConfirmation] = useState("");
  const [mode, setMode] = useState<"login" | "register">("login");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setNotice("");
    setLoading(true);

    try {
      if (mode === "register") {
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
          {mode === "register" ? "Create a personal account. Email verification is required." : "Sign in with your account"}
        </p>

        <label>
          {mode === "register" ? "Email" : "Email or admin username"}
          <input
            className="cvis-login-input"
            type={mode === "register" ? "email" : "text"}
            value={username}
            onChange={(event) => {
              setUsername(event.target.value);
              setError("");
              setNotice("");
            }}
            autoComplete={mode === "register" ? "email" : "username"}
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

        <label>
          {mode === "register" ? "Password (at least 12 characters)" : "Password"}
          <input
            className="cvis-login-input"
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            minLength={mode === "register" ? 12 : undefined}
            maxLength={128}
            autoComplete={mode === "register" ? "new-password" : "current-password"}
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

        {mode === "register" && (
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
            ? mode === "register" ? "CREATING ACCOUNT..." : "AUTHENTICATING..."
            : mode === "register" ? "CREATE ACCOUNT" : "LOGIN"}
        </button>
        <div style={{ display: "grid", gap: 8, marginTop: 14 }}>
          <button
            type="button"
            disabled={loading}
            onClick={() => {
              setMode(mode === "login" ? "register" : "login");
              setPassword("");
              setPasswordConfirmation("");
              setError("");
              setNotice("");
            }}
          >
            {mode === "login" ? "Create personal account" : "Back to sign in"}
          </button>
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
