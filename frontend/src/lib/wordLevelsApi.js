import api from "@/lib/api";

export async function classifyWordLevels(words) {
  const response = await api.post("/v1/words/level", { words });
  return response.data;
}

