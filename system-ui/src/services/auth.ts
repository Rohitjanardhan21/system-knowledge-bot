import axios from "axios";

const API_BASE = "http://127.0.0.1:8000";

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

export async function refreshAccessToken(): Promise<string | null> {
  const refreshToken = getRefreshToken();

  if (!refreshToken) {
    return null;
  }

  try {
    const response = await axios.post<TokenResponse>(
      `${API_BASE}/auth/refresh`,
      {
        refresh_token: refreshToken,
      },
    );

    const tokens = response.data;

    sessionStorage.setItem(ACCESS_TOKEN_KEY, tokens.access_token);
    sessionStorage.setItem(REFRESH_TOKEN_KEY, tokens.refresh_token);

    return tokens.access_token;
  } catch {
    logout();
    return null;
  }
}

export function logout(): void {
  sessionStorage.removeItem(ACCESS_TOKEN_KEY);
  sessionStorage.removeItem(REFRESH_TOKEN_KEY);
}

export function isAuthenticated(): boolean {
  return Boolean(getAccessToken());
}
