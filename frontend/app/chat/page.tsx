"use client"

import { useEffect, useState } from "react"
import { motion, AnimatePresence } from "framer-motion"
import { Trash2 } from "lucide-react"
import { useChat } from "@/hooks/useChat"
import { pingBackend } from "@/lib/api"
import { ChatThread } from "@/components/ChatThread"
import { PromptInputBox } from "@/components/ui/ai-prompt-box"
import { ExampleQuestions } from "@/components/ExampleQuestions"
import { ThemeToggle } from "@/components/ThemeToggle"
import AnimatedGradientBackground from "@/components/ui/animated-gradient-background"

const DARK_GRADIENT_COLORS = ["#0A0A0A", "#1a1a1a", "#2a1a0a", "#3d1a05", "#D53E0F", "#ff9a3c"]
const LIGHT_GRADIENT_COLORS = ["#F7EDD9", "#EED9B9", "#d9b896", "#b06040", "#9B0F06", "#5E0006"]
const GRADIENT_STOPS = [35, 50, 62, 72, 85, 100]

export default function ChatPage() {
  const { messages, isLoading, sendMessage, clearHistory } = useChat()
  const hasMessages = messages.length > 0
  const [isDark, setIsDark] = useState(true) // defaults to dark — matches layout.tsx class="dark"

  useEffect(() => {
    pingBackend()
  }, [])

  useEffect(() => {
    setIsDark(document.documentElement.classList.contains('dark'))
    const observer = new MutationObserver(() => {
      setIsDark(document.documentElement.classList.contains('dark'))
    })
    observer.observe(document.documentElement, { attributeFilter: ['class'] })
    return () => observer.disconnect()
  }, [])

  return (
    <div className="relative flex flex-col h-dvh bg-[var(--umd-bg)]">

      {/* Animated gradient — empty state only */}
      <AnimatePresence>
        {!hasMessages && (
          <motion.div
            key="gradient"
            aria-hidden="true"
            className="absolute inset-0 z-0"
            exit={{ opacity: 0, scale: 1.5 }}
            transition={{ duration: 0.6, ease: "easeIn" }}
          >
            <AnimatedGradientBackground
              Breathing={false}
              startingGap={125}
              gradientColors={isDark ? DARK_GRADIENT_COLORS : LIGHT_GRADIENT_COLORS}
              gradientStops={GRADIENT_STOPS}
            />
          </motion.div>
        )}
      </AnimatePresence>

      {/* Top-right controls — fade in once chat starts */}
      <AnimatePresence>
        {hasMessages && (
          <motion.div
            initial={{ opacity: 0, y: -8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.2 }}
            className="absolute top-4 right-4 flex items-center gap-2 z-10"
          >
            <button
              onClick={clearHistory}
              aria-label="New chat"
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm
                bg-[var(--umd-surface)] hover:bg-[var(--umd-surface)] text-[var(--umd-muted)] hover:text-[var(--umd-text)]
                border border-[var(--umd-border)] transition-all duration-200"
            >
              <Trash2 size={14} />
              <span className="hidden sm:inline">New chat</span>
            </button>
            <ThemeToggle />
          </motion.div>
        )}
      </AnimatePresence>

      {!hasMessages ? (
        /* ── Empty state: everything centered ── */
        <div className="relative z-10 flex flex-1 flex-col items-center justify-center gap-8 px-4">
          <motion.h1
            layoutId="ask-testudo-title"
            className="text-4xl md:text-5xl font-bold text-[var(--umd-text)] tracking-tight"
          >
            Ask Testudo
          </motion.h1>
          <div className="w-full max-w-[42rem] flex flex-col gap-4">
            <PromptInputBox
              onSend={sendMessage}
              isLoading={isLoading}
              placeholder="Ask anything about UMD policy..."
            />
            <ExampleQuestions onSelect={sendMessage} />
          </div>
        </div>
      ) : (
        /* ── Active chat: title top-left, messages, input pinned bottom ── */
        <div className="flex flex-col h-full">
          <div className="px-4 pt-4 pb-2 pr-36 shrink-0">
            <motion.h1
              layoutId="ask-testudo-title"
              className="text-base font-bold text-[var(--umd-text)] tracking-tight"
            >
              Ask Testudo
            </motion.h1>
          </div>

          <ChatThread messages={messages} />

          <div className="shrink-0 px-4 pb-4 pt-2 max-w-[42rem] w-full mx-auto">
            <PromptInputBox
              onSend={sendMessage}
              isLoading={isLoading}
              placeholder="Ask a follow-up..."
            />
            <p className="text-center text-[10px] text-[var(--umd-muted)] mt-1.5">
              Ask Testudo — UMD academic policy only. Always verify with your advisor.
            </p>
          </div>
        </div>
      )}
    </div>
  )
}
