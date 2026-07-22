import axios from "axios";
import type {
  WorkflowPlanRequest,
  WorkflowPlanResponse,
} from "../types/cloudmind";

const API_BASE_URL =
  import.meta.env.VITE_CLOUDMIND_API_URL ?? "http://localhost:8000";

export async function getWorkflowPlan(
  payload: WorkflowPlanRequest,
): Promise<WorkflowPlanResponse> {
  const response = await axios.post<WorkflowPlanResponse>(
    `${API_BASE_URL}/api/workflows/plan`,
    payload,
    {
      headers: {
        "Content-Type": "application/json",
      },
      timeout: 60000,
    },
  );

  return response.data;
}