import axios from "axios";
import { API_BASE } from "./endpoints";

const ACCESS_TOKEN_KEY = "cvis_access_token";
const REFRESH_TOKEN_KEY = "cvis_refresh_token";

interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

export async function login(
  username: string,
  password: string,
): Promise<TokenResponse> {
  const response = await axios.post<TokenResponse>(
    `${API_BASE}/auth/login`,
    {
      username,
      password,
    },
  );

  const tokens = response.data;

  sessionStorage.setItem(ACCESS_TOKEN_KEY, tokens.access_token);
  sessionStorage.setItem(REFRESH_TOKEN_KEY, tokens.refresh_token);

  return tokens;
}

export function getAccessToken(): string | null {
  return sessionStorage.getItem(ACCESS_TOKEN_KEY);
}

export function getRefreshToken(): string | null {
  return sessionStorage.getItem(REFRESH_TOKEN_KEY);
}

let refreshPromise: Promise<string | null> | null = null;

export function refreshAccessToken(): Promise<string | null> {
  if (refreshPromise) {
    return refreshPromise;
  }

  const refreshToken = getRefreshToken();

  if (!refreshToken) {
    return Promise.resolve(null);
  }

  refreshPromise = (async (): Promise<string | null> => {
    try {
      const response = await axios.post<TokenResponse>(
        `${API_BASE}/auth/refresh`,
        { refresh_token: refreshToken },
      );

      const tokens = response.data;

      // Don't overwrite a session that changed while this request was in flight.
      if (getRefreshToken() !== refreshToken) {
        return getAccessToken();
      }

      sessionStorage.setItem(ACCESS_TOKEN_KEY, tokens.access_token);
      sessionStorage.setItem(REFRESH_TOKEN_KEY, tokens.refresh_token);

      return tokens.access_token;
    } catch {
      // Only clear the session if it still uses the token that failed.
      if (getRefreshToken() === refreshToken) {
        logout();
      }
      return null;
    } finally {
      refreshPromise = null;
    }
  })();

  return refreshPromise;
}

export function logout(): void {
  sessionStorage.removeItem(ACCESS_TOKEN_KEY);
  sessionStorage.removeItem(REFRESH_TOKEN_KEY);
}

export function isAuthenticated(): boolean {
  return Boolean(getAccessToken());
}
