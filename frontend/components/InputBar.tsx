"use client"

import { useState, KeyboardEvent } from "react"
import { Send, Loader2 } from "lucide-react"

interface InputBarProps {
  onSend: (question: string) => void
  isLoading: boolean
}

const MAX_LENGTH = 500

export function InputBar({ onSend, isLoading }: InputBarProps) {
  const [value, setValue] = useState("")

  const handleSend = () => {
    const trimmed = value.trim()
    if (!trimmed || isLoading) return
    onSend(trimmed)
    setValue("")
  }

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const remaining = MAX_LENGTH - value.length
  const canSend = value.trim().length > 0 && !isLoading && value.length <= MAX_LENGTH

  return (
    <div className="px-4 pb-4 pt-2">
      <div
        className="
          relative flex items-end gap-2
          bg-[var(--umd-surface)] border border-[var(--umd-border)]
          rounded-2xl shadow-sm px-4 py-3
          focus-within:border-[var(--umd-mid)]
          focus-within:shadow-md
          transition-all duration-200
        "
      >
        <textarea
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask about courses, requirements, policies… (Enter to send)"
          maxLength={MAX_LENGTH + 50}
          rows={1}
          disabled={isLoading}
          className="
            flex-1 resize-none bg-transparent outline-none
            text-sm text-[var(--umd-text)] placeholder:text-[var(--umd-muted)]
            leading-relaxed max-h-40 overflow-y-auto
            disabled:opacity-60
          "
          style={{ lineHeight: "1.5" }}
          onInput={(e) => {
            const el = e.currentTarget
            el.style.height = "auto"
            el.style.height = Math.min(el.scrollHeight, 160) + "px"
          }}
        />

        {/* Right side: char count + send button */}
        <div className="flex items-center gap-2 shrink-0 pb-0.5">
          <span
            className={`text-[11px] tabular-nums transition-colors ${
              remaining < 50 ? "text-red-500" : "text-[var(--umd-muted)]"
            }`}
          >
            {remaining}
          </span>
          <button
            onClick={handleSend}
            disabled={!canSend}
            aria-label="Send message"
            className="
              flex items-center justify-center w-8 h-8 rounded-full
              bg-[var(--umd-dark)] text-white
              hover:bg-[var(--umd-mid)]
              disabled:opacity-40 disabled:cursor-not-allowed
              transition-all duration-200 hover:scale-105
            "
          >
            {isLoading ? (
              <Loader2 size={15} className="animate-spin" />
            ) : (
              <Send size={14} />
            )}
          </button>
        </div>
      </div>
      <p className="text-center text-[10px] text-[var(--umd-muted)] mt-1.5">
        Ask Testudo — UMD academic policy only. Always verify with your advisor.
      </p>
    </div>
  )
}
