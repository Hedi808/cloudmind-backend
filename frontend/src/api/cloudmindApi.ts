import axios from "axios";
import type {
  CloudMindChatRequest,
  CloudMindChatResponse,
} from "../types/cloudmind";

const API_BASE_URL =
  import.meta.env.VITE_CLOUDMIND_API_URL ?? "http://localhost:8000";

export async function sendCloudMindMessage(
  payload: CloudMindChatRequest,
): Promise<CloudMindChatResponse> {
  const response = await axios.post<CloudMindChatResponse>(
    `${API_BASE_URL}/api/chat/`,
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