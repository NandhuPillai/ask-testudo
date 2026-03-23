interface ExampleQuestionsProps {
  onSelect: (question: string) => void
}

const EXAMPLE_QUESTIONS = [
  "What are the prerequisites for CMSC132?",
  "What GPA do I need to stay in good academic standing?",
  "How do I apply for a late withdrawal?",
  "What are the lower-level requirements for the CS major?",
  "What courses are required for the CS major?",
  "What is the minimum GPA to graduate with honors?",
]

export function ExampleQuestions({ onSelect }: ExampleQuestionsProps) {
  return (
    <div className="flex flex-col items-center justify-center py-12 px-4 text-center">
      {/* Hero */}
      <div className="text-6xl mb-4 select-none" aria-hidden>🐢</div>
      <h1 className="text-3xl font-bold text-[var(--umd-dark)] dark:text-[var(--umd-light)] mb-1 tracking-tight">
        Ask Testudo
      </h1>
      <p className="text-[var(--umd-muted)] text-sm mb-8">
        Your UMD academic policy assistant
      </p>

      {/* Suggestion chips */}
      <div className="flex flex-wrap justify-center gap-2 max-w-2xl">
        {EXAMPLE_QUESTIONS.map((q) => (
          <button
            key={q}
            onClick={() => onSelect(q)}
            className="
              px-4 py-2 rounded-full text-sm
              bg-[var(--umd-surface)] text-[var(--umd-text)]
              border border-[var(--umd-border)]
              hover:bg-[var(--umd-dark)] hover:text-white hover:border-[var(--umd-dark)]
              transition-all duration-200 hover:scale-[1.03]
              shadow-sm
            "
          >
            {q}
          </button>
        ))}
      </div>
    </div>
  )
}
