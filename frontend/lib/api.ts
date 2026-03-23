// lib/api.ts

import { AskResponse, HistoryMessage } from "./types"

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"

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

/** Fire-and-forget — warms Railway server on page load to reduce cold-start latency */
export function pingBackend(): void {
  fetch(`${API_URL}/ping`).catch(() => {})
}
