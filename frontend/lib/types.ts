// lib/types.ts

export interface Source {
  filename: string
  page: number
  section: string
  doc_type: string
}

export interface ChatMessage {
  id: string
  role: "user" | "assistant"
  content: string
  sources?: Source[]
  confidence?: "high" | "medium" | "low"
  rerank_score?: number
  fallback?: boolean
  loading?: boolean  // true while waiting for API response
}

export interface AskResponse {
  answer: string
  sources: Source[]
  confidence: "high" | "medium" | "low"
  rerank_score: number
  fallback: boolean
}

export interface HistoryMessage {
  role: "user" | "assistant"
  content: string
}
