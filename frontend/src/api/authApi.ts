import axios from "axios";


export const API_BASE_URL =
  import.meta.env.VITE_CLOUDMIND_API_URL ?? "http://localhost:8000";

export type AuthUser = {
  id: string;
  email: string;
  display_name: string;
  avatar_url: string | null;
  email_verified: boolean;
  auth_provider: "password" | "google";
  role: "admin" | "member";
  must_change_password: boolean;
};

export type AuthResponse = {
  status: string;
  message: string;
  user: AuthUser;
};

export type AuthConfig = {
  google_enabled: boolean;
  registration_enabled: boolean;
};

export async function getAuthConfig(): Promise<AuthConfig> {
  const response = await axios.get<AuthConfig>(`${API_BASE_URL}/api/auth/config`, {
    withCredentials: true,
    timeout: 15000,
  });
  return response.data;
}

export async function getCurrentUser(): Promise<AuthUser | null> {
  try {
    const response = await axios.get<AuthResponse>(`${API_BASE_URL}/api/auth/me`, {
      withCredentials: true,
      timeout: 15000,
    });
    return response.data.user;
  } catch (error) {
    if (axios.isAxiosError(error) && error.response?.status === 401) {
      return null;
    }
    throw error;
  }
}

export async function registerUser(payload: {
  display_name: string;
  email: string;
  password: string;
}): Promise<AuthResponse> {
  const response = await axios.post<AuthResponse>(
    `${API_BASE_URL}/api/auth/register`,
    payload,
    { withCredentials: true, timeout: 30000 },
  );
  return response.data;
}

export async function loginUser(payload: {
  email: string;
  password: string;
}): Promise<AuthResponse> {
  const response = await axios.post<AuthResponse>(
    `${API_BASE_URL}/api/auth/login`,
    payload,
    { withCredentials: true, timeout: 30000 },
  );
  return response.data;
}

export async function logoutUser(): Promise<void> {
  await axios.post(
    `${API_BASE_URL}/api/auth/logout`,
    {},
    { withCredentials: true, timeout: 15000 },
  );
}

export async function changePassword(payload: {
  current_password: string;
  new_password: string;
}): Promise<AuthResponse> {
  const response = await axios.post<AuthResponse>(
    `${API_BASE_URL}/api/auth/change-password`,
    payload,
    { withCredentials: true, timeout: 30000 },
  );
  return response.data;
}

export function getAuthErrorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const detail = error.response?.data?.detail;

    if (typeof detail === "string") {
      return detail;
    }

    if (Array.isArray(detail) && typeof detail[0]?.msg === "string") {
      return detail[0].msg.replace(/^Value error, /, "");
    }

    if (!error.response) {
      return "CloudMind could not reach the authentication service.";
    }
  }

  return error instanceof Error ? error.message : "Authentication failed.";
}
