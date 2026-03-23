import ReactMarkdown from "react-markdown"
import { ChatMessage } from "@/lib/types"
import { ConfidenceBadge } from "./ConfidenceBadge"
import { SourceCard } from "./SourceCard"

interface MessageBubbleProps {
  message: ChatMessage
}

export function MessageBubble({ message }: MessageBubbleProps) {
  const isUser = message.role === "user"

  if (isUser) {
    return (
      <div className="flex justify-end msg-animate">
        <div
          className="
            max-w-[72%] px-4 py-2.5 text-sm leading-relaxed
            bg-[var(--umd-dark)] text-white
            rounded-[18px_18px_4px_18px]
            shadow-sm
          "
        >
          {message.content}
        </div>
      </div>
    )
  }

  // Assistant message
  return (
    <div className="flex justify-start msg-animate">
      <div className="flex flex-col max-w-[85%] gap-1">
        {/* Bubble */}
        <div
          className="
            px-4 py-3 text-sm
            bg-[var(--umd-surface)] text-[var(--umd-text)]
            border border-[var(--umd-border)]
            rounded-[18px_18px_18px_4px]
            shadow-sm
          "
        >
          {message.loading ? (
            <div className="dot-pulse flex items-center gap-1.5 py-1 px-1" aria-label="Thinking...">
              <span />
              <span />
              <span />
            </div>
          ) : (
            <div className="prose-umd">
              <ReactMarkdown>{message.content}</ReactMarkdown>
            </div>
          )}
        </div>

        {/* Metadata below bubble (only when not loading) */}
        {!message.loading && (
          <div className="flex flex-col gap-1 px-1">
            {message.confidence && !message.fallback && (
              <ConfidenceBadge
                confidence={message.confidence}
                rerank_score={message.rerank_score}
              />
            )}
            {message.sources && message.sources.length > 0 && (
              <SourceCard sources={message.sources} />
            )}
          </div>
        )}
      </div>
    </div>
  )
}
