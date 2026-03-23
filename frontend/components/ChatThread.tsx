"use client"

import { useEffect, useRef } from "react"
import { ChatMessage } from "@/lib/types"
import { MessageBubble } from "./MessageBubble"
import { ExampleQuestions } from "./ExampleQuestions"

interface ChatThreadProps {
  messages: ChatMessage[]
  onSelectExample: (question: string) => void
}

export function ChatThread({ messages, onSelectExample }: ChatThreadProps) {
  const bottomRef = useRef<HTMLDivElement>(null)

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages])

  return (
    <div className="flex-1 overflow-y-auto">
      {messages.length === 0 ? (
        <ExampleQuestions onSelect={onSelectExample} />
      ) : (
        <div className="max-w-3xl mx-auto px-4 py-6 flex flex-col gap-4">
          {messages.map((msg) => (
            <MessageBubble key={msg.id} message={msg} />
          ))}
          <div ref={bottomRef} />
        </div>
      )}
    </div>
  )
}
