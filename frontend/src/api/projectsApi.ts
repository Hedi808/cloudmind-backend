import axios from "axios";
import type {
  ProjectDetailResponse,
  ProjectListResponse,
} from "../types/cloudmind";

const API_BASE_URL =
  import.meta.env.VITE_CLOUDMIND_API_URL ?? "http://localhost:8000";

export async function listProjects(
  q?: string,
): Promise<ProjectListResponse> {
  const response = await axios.get<ProjectListResponse>(
    `${API_BASE_URL}/api/projects`,
    {
      params: q ? { q } : undefined,
      timeout: 60000,
    },
  );

  return response.data;
}

export async function getProject(
  projectId: string,
): Promise<ProjectDetailResponse> {
  const response = await axios.get<ProjectDetailResponse>(
    `${API_BASE_URL}/api/projects/${projectId}`,
    {
      timeout: 60000,
    },
  );

  return response.data;
}