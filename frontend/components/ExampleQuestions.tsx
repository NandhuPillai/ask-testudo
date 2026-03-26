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
    <div className="flex flex-wrap justify-center gap-2">
      {EXAMPLE_QUESTIONS.map((q) => (
        <button
          key={q}
          onClick={() => onSelect(q)}
          className="
            px-4 py-2 rounded-full text-sm
            bg-[var(--umd-surface)] text-[var(--umd-muted)] hover:text-[var(--umd-text)]
            border border-[var(--umd-border)] hover:border-[var(--umd-dark)]
            transition-all duration-200
          "
        >
          {q}
        </button>
      ))}
    </div>
  )
}
