"use client"

import { useState, useCallback } from "react"
import { v4 as uuidv4 } from "uuid"
import { ChatMessage, HistoryMessage } from "@/lib/types"
import { askQuestion } from "@/lib/api"

export function useChat() {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [isLoading, setIsLoading] = useState(false)

  /** Build history array from current committed messages (exclude loading stubs) */
  const buildHistory = (msgs: ChatMessage[]): HistoryMessage[] =>
    msgs
      .filter((m) => !m.loading && m.content)
      .map((m) => ({ role: m.role, content: m.content }))

  const sendMessage = useCallback(
    async (question: string) => {
      if (!question.trim() || isLoading) return

      const userMsg: ChatMessage = {
        id: uuidv4(),
        role: "user",
        content: question.trim(),
      }

      const loadingMsg: ChatMessage = {
        id: uuidv4(),
        role: "assistant",
        content: "",
        loading: true,
      }

      setMessages((prev) => {
        const history = buildHistory(prev)
        // We capture history here for the API call below
        return [...prev, userMsg, loadingMsg]
      })
      setIsLoading(true)

      // Use functional update to get the current state before setting loading
      let currentHistory: HistoryMessage[] = []
      setMessages((prev) => {
        // Extract history from before the loading message was added
        const beforeLoading = prev.slice(0, prev.length - 2)
        currentHistory = buildHistory(beforeLoading)
        return prev
      })

      try {
        const response = await askQuestion(question.trim(), currentHistory)

        setMessages((prev) =>
          prev.map((m) =>
            m.loading
              ? {
                  ...m,
                  loading: false,
                  content: response.answer,
                  sources: response.sources,
                  confidence: response.confidence,
                  rerank_score: response.rerank_score,
                  fallback: response.fallback,
                }
              : m
          )
        )
      } catch (err) {
        const errorMsg =
          err instanceof Error ? err.message : "Unknown error occurred."
        setMessages((prev) =>
          prev.map((m) =>
            m.loading
              ? {
                  ...m,
                  loading: false,
                  content: `Something went wrong: ${errorMsg} Please try again.`,
                  fallback: true,
                }
              : m
          )
        )
      } finally {
        setIsLoading(false)
      }
    },
    [isLoading]
  )

  const clearHistory = useCallback(() => {
    setMessages([])
  }, [])

  return { messages, isLoading, sendMessage, clearHistory }
}
