import api from "@/lib/api";

export type CEFRLevel = "A1" | "A2" | "B1" | "B2" | "C1" | "C2";

export interface WordLevelItemData {
  word: string;
  level: CEFRLevel;
}

export interface WordLevelsRequest {
  words: string[];
}

export async function classifyWordLevels(words: string[]): Promise<WordLevelItemData[]> {
  const payload: WordLevelsRequest = { words };
  const response = await api.post<WordLevelItemData[]>("/v1/words/level", payload);
  return response.data;
}

