import ReactMarkdown from "react-markdown"
import { ChatMessage } from "@/lib/types"
import { ConfidenceBadge } from "./ConfidenceBadge"
import { SourceCard } from "./SourceCard"

interface MessageBubbleProps {
  message: ChatMessage
}

export function MessageBubble({ message }: MessageBubbleProps) {
  if (message.role === "user") {
    return (
      <div className="flex justify-end msg-animate">
        <div className="max-w-[72%] px-4 py-2.5 text-sm leading-relaxed bg-[var(--umd-surface)] text-[var(--umd-text)] border border-[var(--umd-border)] rounded-[18px_18px_4px_18px] shadow-sm">
          {message.content}
        </div>
      </div>
    )
  }

  // Assistant message — no bubble
  return (
    <div className="flex flex-col gap-3 msg-animate">
      <p className="inline-flex items-center gap-2 text-lg font-semibold text-[var(--umd-dark)]">
        ✦ Answer
      </p>

      <div className="text-[var(--umd-text)] text-sm leading-relaxed">
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

      {!message.loading && (
        <div className="flex flex-col gap-1">
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
  )
}
