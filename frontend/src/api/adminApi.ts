import axios from "axios";

import { API_BASE_URL } from "./authApi";


export type AdminUserSummary = {
  id: string;
  email: string;
  display_name: string;
  avatar_url: string | null;
  role: "admin" | "member";
  is_active: boolean;
  email_verified: boolean;
  auth_provider: "google" | "password";
  project_count: number;
  conversation_count: number;
  created_at: string | null;
  last_login_at: string | null;
};

export type AdminOverview = {
  status: string;
  message: string;
  metrics: {
    users: number;
    active_users: number;
    projects: number;
    conversations: number;
    messages: number;
    agent_actions: number;
    pipeline_runs: number;
    live_sessions: number;
  };
  recent_users: AdminUserSummary[];
};

export async function getAdminOverview(): Promise<AdminOverview> {
  const response = await axios.get<AdminOverview>(
    `${API_BASE_URL}/api/admin/overview`,
    { withCredentials: true, timeout: 15000 },
  );
  return response.data;
}
