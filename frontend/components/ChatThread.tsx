"use client"

import { StickToBottom } from "use-stick-to-bottom"
import { ChatMessage } from "@/lib/types"
import { MessageBubble } from "./MessageBubble"

interface ChatThreadProps {
  messages: ChatMessage[]
}

export function ChatThread({ messages }: ChatThreadProps) {
  return (
    <StickToBottom
      className="flex-1 overflow-y-auto"
      resize="smooth"
      initial="instant"
    >
      <StickToBottom.Content className="flex flex-col gap-6 max-w-[42rem] mx-auto w-full px-4 py-6">
        {messages.map((msg) => (
          <MessageBubble key={msg.id} message={msg} />
        ))}
      </StickToBottom.Content>
    </StickToBottom>
  )
}
