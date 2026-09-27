import { useState, type FormEvent } from "react";
import { login } from "../services/auth";

interface LoginProps {
  onSuccess: () => void;
}

function Login({ onSuccess }: LoginProps) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setLoading(true);

    try {
      await login(username, password);
      onSuccess();
    } catch {
      setError("Invalid username or password.");
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
      <form
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
        <p style={{ color: "#8fa5b5" }}>Authentication required</p>

        <label>
          Username
          <input
            value={username}
            onChange={(event) => setUsername(event.target.value)}
            autoComplete="username"
            required
            style={{
              display: "block",
              width: "100%",
              marginTop: "8px",
              marginBottom: "16px",
              padding: "10px",
              boxSizing: "border-box",
            }}
          />
        </label>

        <label>
          Password
          <input
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            autoComplete="current-password"
            required
            style={{
              display: "block",
              width: "100%",
              marginTop: "8px",
              marginBottom: "16px",
              padding: "10px",
              boxSizing: "border-box",
            }}
          />
        </label>

        {error && (
          <div style={{ color: "#ff7777", marginBottom: "16px" }}>
            {error}
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
          {loading ? "AUTHENTICATING..." : "LOGIN"}
        </button>
      </form>
    </div>
  );
}

export default Login;
