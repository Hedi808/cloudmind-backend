import axios from "axios";
import type {
  PipelineRunListResponse,
  PipelineRunRequest,
  PipelineRunResponse,
} from "../types/cloudmind";

const API_BASE_URL =
  import.meta.env.VITE_CLOUDMIND_API_URL ?? "http://localhost:8000";

export async function runOrResumePipeline(
  payload: PipelineRunRequest,
): Promise<PipelineRunResponse> {
  const response = await axios.post<PipelineRunResponse>(
    `${API_BASE_URL}/api/pipeline/run`,
    payload,
    {
      headers: {
        "Content-Type": "application/json",
      },
      timeout: 180000,
    },
  );

  return response.data;
}

export async function listPipelineRuns(
  projectId: string,
  limit = 20,
): Promise<PipelineRunListResponse> {
  const response = await axios.get<PipelineRunListResponse>(
    `${API_BASE_URL}/api/pipeline/runs`,
    {
      params: {
        project_id: projectId,
        limit,
      },
      timeout: 60000,
    },
  );

  return response.data;
}
