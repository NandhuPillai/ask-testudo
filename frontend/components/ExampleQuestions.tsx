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
            bg-[#242424] text-[#808080] hover:text-[#f5f5f5]
            border border-[#3a3a3a] hover:border-[#D53E0F]
            transition-all duration-200
          "
        >
          {q}
        </button>
      ))}
    </div>
  )
}
