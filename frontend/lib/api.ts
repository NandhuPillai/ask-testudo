// lib/api.ts

import { AskResponse, HistoryMessage } from "./types"

const API_URL = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/$/, "")

export async function askQuestion(
  question: string,
  history: HistoryMessage[]
): Promise<AskResponse> {
  const res = await fetch(`${API_URL}/ask`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, history, stream: false }),
  })

  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error((err as { detail?: string }).detail || `API error: ${res.status}`)
  }

  return res.json()
}

export async function askQuestionStream(
  question: string,
  history: HistoryMessage[],
  onChunk: (chunk: string) => void,
  onDone: (data: any) => void,
  onError: (err: Error) => void
): Promise<void> {
  try {
    const res = await fetch(`${API_URL}/ask`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, history, stream: true }),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error((err as { detail?: string }).detail || `API error: ${res.status}`);
    }

    if (!res.body) throw new Error("No response body");

    const reader = res.body.getReader();
    const decoder = new TextDecoder("utf-8");
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";

      for (const line of lines) {
        if (line.startsWith("data: ")) {
          const dataStr = line.slice(6);
          if (dataStr === "[DONE]") continue;
          try {
            const data = JSON.parse(dataStr);
            if (data.type === "chunk") {
              onChunk(data.content);
            } else if (data.type === "error") {
              onError(new Error(data.detail || "Stream error"));
              return;
            } else if (data.type === "done") {
              onDone(data);
              return;
            }
          } catch (e) {
            console.warn("Failed to parse SSE JSON", e);
          }
        }
      }
    }
  } catch (err) {
    onError(err instanceof Error ? err : new Error(String(err)));
  }
}

/** Fire-and-forget — warms Railway server on page load to reduce cold-start latency */
export function pingBackend(): void {
  fetch(`${API_URL}/ping`).catch(() => {})
}
