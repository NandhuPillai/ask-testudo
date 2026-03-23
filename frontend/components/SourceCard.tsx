"use client"

import { useState } from "react"
import { ChevronDown, ChevronUp, FileText } from "lucide-react"
import { Source } from "@/lib/types"

interface SourceCardProps {
  sources: Source[]
}

export function SourceCard({ sources }: SourceCardProps) {
  const [open, setOpen] = useState(false)

  if (!sources || sources.length === 0) return null

  return (
    <div className="mt-2">
      <button
        onClick={() => setOpen((o) => !o)}
        className="
          flex items-center gap-1.5 text-xs
          text-[var(--umd-muted)] hover:text-[var(--umd-dark)]
          dark:hover:text-[var(--umd-light)]
          transition-colors duration-150
        "
      >
        {open ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
        <span>
          {open ? "Hide" : "Show"} sources ({sources.length})
        </span>
      </button>

      {open && (
        <div className="mt-2 flex flex-col gap-2">
          {sources.map((src, i) => (
            <div
              key={i}
              className="
                flex items-start gap-2 px-3 py-2 rounded-lg text-xs
                bg-[var(--umd-bg)] dark:bg-[var(--umd-bg)]
                border border-[var(--umd-border)]
              "
            >
              <FileText
                size={14}
                className="mt-0.5 shrink-0 text-[var(--umd-light)]"
              />
              <div className="min-w-0">
                <div className="font-medium text-[var(--umd-text)] truncate">
                  {src.filename}
                </div>
                <div className="text-[var(--umd-muted)] mt-0.5">
                  Page {src.page}
                  {src.section && (
                    <span> · {src.section}</span>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
