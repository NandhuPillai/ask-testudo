"use client"

import { ThemeToggle } from "./ThemeToggle"
import { Trash2 } from "lucide-react"

interface NavbarProps {
  onClear?: () => void
  hasMessages: boolean
}

export function Navbar({ onClear, hasMessages }: NavbarProps) {
  return (
    <header
      className="
        sticky top-0 z-50 flex items-center justify-between
        px-4 h-14
        bg-[var(--umd-dark)] text-white
        shadow-md
      "
    >
      {/* Logo + title */}
      <div className="flex items-center gap-2.5">
        <span className="text-2xl select-none" aria-hidden>🐢</span>
        <div className="flex flex-col leading-tight">
          <span className="font-bold text-base tracking-tight">Ask Testudo</span>
          <span className="text-[10px] text-white/60 uppercase tracking-widest hidden sm:block">
            UMD Academic Assistant
          </span>
        </div>
      </div>

      {/* Right side controls */}
      <div className="flex items-center gap-2">
        {hasMessages && (
          <button
            onClick={onClear}
            aria-label="Clear conversation"
            className="
              flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm
              bg-white/15 hover:bg-white/25 text-white/80 hover:text-white
              transition-all duration-200
            "
          >
            <Trash2 size={14} />
            <span className="hidden sm:inline">New chat</span>
          </button>
        )}
        <ThemeToggle />
      </div>
    </header>
  )
}
