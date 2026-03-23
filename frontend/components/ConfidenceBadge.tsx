interface ConfidenceBadgeProps {
  confidence: "high" | "medium" | "low"
  rerank_score?: number
}

const config = {
  high:   { label: "High confidence",   classes: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-300" },
  medium: { label: "Medium confidence", classes: "bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-300" },
  low:    { label: "Low confidence",    classes: "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400" },
}

export function ConfidenceBadge({ confidence, rerank_score }: ConfidenceBadgeProps) {
  const { label, classes } = config[confidence]
  const tooltip = rerank_score !== undefined
    ? `Relevance score: ${rerank_score.toFixed(4)} — how well sources matched your question`
    : label

  return (
    <span
      title={tooltip}
      className={`
        inline-flex items-center gap-1 px-2 py-0.5 rounded-full
        text-[11px] font-medium cursor-help select-none
        ${classes}
      `}
    >
      <span className="text-[9px]">●</span>
      {label}
    </span>
  )
}
