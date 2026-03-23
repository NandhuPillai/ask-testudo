"use client"

import { useChat } from "@/hooks/useChat"
import { Navbar } from "@/components/Navbar"
import { ChatThread } from "@/components/ChatThread"
import { PromptInputBox } from "@/components/ui/ai-prompt-box"

export default function ChatPage() {
  const { messages, isLoading, sendMessage, clearHistory } = useChat()

  return (
    <div className="flex flex-col h-dvh bg-[var(--umd-bg)]">
      <Navbar onClear={clearHistory} hasMessages={messages.length > 0} />

      <ChatThread
        messages={messages}
        onSelectExample={sendMessage}
      />

      <div className="px-4 pb-4 pt-2 max-w-3xl w-full mx-auto">
        <PromptInputBox
          onSend={(message) => sendMessage(message)}
          isLoading={isLoading}
          placeholder="Ask about courses, requirements, policies…"
        />
        <p className="text-center text-[10px] text-[var(--umd-muted)] mt-1.5">
          Ask Testudo — UMD academic policy only. Always verify with your advisor.
        </p>
      </div>
    </div>
  )
}
