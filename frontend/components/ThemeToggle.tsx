"use client"

import { useEffect, useState } from "react"
import { Sun, Moon } from "lucide-react"

export function ThemeToggle() {
  const [isDark, setIsDark] = useState(false)

  useEffect(() => {
    const stored = localStorage.getItem("theme")
    const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches
    const dark = stored === "dark" || (!stored && prefersDark)
    setIsDark(dark)
    document.documentElement.classList.toggle("dark", dark)
  }, [])

  const toggle = () => {
    const next = !isDark
    setIsDark(next)
    document.documentElement.classList.toggle("dark", next)
    localStorage.setItem("theme", next ? "dark" : "light")
  }

  return (
    <button
      onClick={toggle}
      aria-label="Toggle dark mode"
      className="
        flex items-center justify-center w-9 h-9 rounded-full
        bg-[#242424] hover:bg-[#2a2a2a] text-[#f5f5f5]
        border border-[#3a3a3a]
        transition-all duration-200 hover:scale-105
      "
    >
      {isDark ? <Sun size={17} /> : <Moon size={17} />}
    </button>
  )
}
