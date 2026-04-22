"""
Compare two or three RAGAS evaluation result files side by side.

Usage:
    python eval/compare_runs.py baseline_2026-04-18.json hires_2026-04-20.json
    python eval/compare_runs.py baseline_*.json hires_*.json agentic_*.json
    python eval/compare_runs.py --auto   # auto-discover latest of each type
"""

import argparse
import json
import sys
from pathlib import Path

RESULTS_DIR = Path(__file__).parent / "results"
METRIC_KEYS = ["context_precision", "context_recall", "faithfulness", "answer_relevancy"]
METRIC_ABBREV = {
    "context_precision": "CP",
    "context_recall": "CR",
    "faithfulness": "F",
    "answer_relevancy": "AR",
}


def load_result(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def find_latest(prefix: str) -> Path | None:
    matches = sorted(RESULTS_DIR.glob(f"{prefix}_*.json"))
    matches = [p for p in matches if not p.name.endswith("_responses.json")]
    return matches[-1] if matches else None


def print_aggregate_table(runs: list[tuple[str, dict]]):
    print("\n" + "=" * 70)
    print("AGGREGATE METRICS COMPARISON")
    print("=" * 70)
    col_w = 14

    header = f"{'Metric':<22}" + "".join(f"{label:>{col_w}}" for label, _ in runs)
    print(header)
    print("-" * (22 + col_w * len(runs)))

    for k in METRIC_KEYS:
        row = f"  {k:<20}"
        first_val = None
        for label, data in runs:
            val = data["metrics"].get(k)
            if val is None:
                row += f"{'N/A':>{col_w}}"
            else:
                if first_val is None:
                    row += f"{val:>{col_w}.4f}"
                    first_val = val
                else:
                    delta = val - first_val
                    sign = "+" if delta >= 0 else ""
                    row += f"{val:>8.4f} ({sign}{delta:.4f})"
        print(row)
    print("=" * 70)


def print_category_table(runs: list[tuple[str, dict]]):
    categories = list(runs[0][1].get("per_category", {}).keys())
    if not categories:
        return

    print("\nPER-CATEGORY CONTEXT RECALL COMPARISON")
    print("=" * 70)
    col_w = 14
    header = f"{'Category':<26}" + "".join(f"{label:>{col_w}}" for label, _ in runs)
    print(header)
    print("-" * (26 + col_w * len(runs)))

    for cat in categories:
        for k in ["context_recall"]:
            row = f"  {cat:<24}"
            first_val = None
            for label, data in runs:
                val = (data.get("per_category", {}).get(cat) or {}).get(k)
                if val is None:
                    row += f"{'N/A':>{col_w}}"
                else:
                    if first_val is None:
                        row += f"{val:>{col_w}.4f}"
                        first_val = val
                    else:
                        delta = val - first_val
                        sign = "+" if delta >= 0 else ""
                        row += f"{val:>8.4f} ({sign}{delta:.4f})"
            print(row)
    print("=" * 70)


def print_regressions(runs: list[tuple[str, dict]]):
    if len(runs) < 2:
        return

    label_a, data_a = runs[0]
    label_b, data_b = runs[1]

    pq_a = {q["id"]: q for q in data_a.get("per_question", [])}
    pq_b = {q["id"]: q for q in data_b.get("per_question", [])}

    regressions = []
    for qid, q_b in pq_b.items():
        q_a = pq_a.get(qid)
        if not q_a:
            continue
        for k in METRIC_KEYS:
            val_a = q_a.get(k)
            val_b = q_b.get(k)
            if val_a is not None and val_b is not None and val_b < val_a - 0.05:
                regressions.append({
                    "id": qid,
                    "category": q_b.get("category"),
                    "question": q_b.get("question", "")[:60],
                    "metric": k,
                    "before": val_a,
                    "after": val_b,
                    "delta": val_b - val_a,
                })

    if not regressions:
        print("\nNo significant regressions (delta < -0.05) detected.")
        return

    print(f"\nREGRESSIONS: {label_a} → {label_b}  (delta < -0.05)")
    print("-" * 70)
    for r in sorted(regressions, key=lambda x: x["delta"]):
        print(f"  {r['id']} [{r['category']}] {r['metric']}: {r['before']:.4f} → {r['after']:.4f}  ({r['delta']:+.4f})")
        print(f"    Q: {r['question']}")


def generate_chart(runs: list[tuple[str, dict]], output_path: Path):
    try:
        import matplotlib.pyplot as plt
        import numpy as np
    except ImportError:
        print("matplotlib not installed — skipping chart generation")
        return

    labels = [label for label, _ in runs]
    x = np.arange(len(METRIC_KEYS))
    width = 0.8 / len(runs)

    fig, ax = plt.subplots(figsize=(10, 6))
    colors = ["#E03A3E", "#2563EB", "#16A34A", "#D97706"]

    for i, (label, data) in enumerate(runs):
        vals = [data["metrics"].get(k, 0) or 0 for k in METRIC_KEYS]
        offset = (i - (len(runs) - 1) / 2) * width
        bars = ax.bar(x + offset, vals, width, label=label, color=colors[i % len(colors)], alpha=0.85)
        for bar, v in zip(bars, vals):
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.01,
                    f"{v:.3f}", ha="center", va="bottom", fontsize=8)

    ax.set_ylabel("Score")
    ax.set_title("ask-testudo RAGAS Evaluation Comparison")
    ax.set_xticks(x)
    ax.set_xticklabels([METRIC_ABBREV.get(k, k) for k in METRIC_KEYS])
    ax.set_ylim(0, 1.15)
    ax.legend()
    ax.grid(axis="y", alpha=0.3)

    plt.tight_layout()
    plt.savefig(output_path, dpi=150)
    print(f"\nChart saved to {output_path}")
    plt.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("files", nargs="*", help="Result JSON files to compare")
    parser.add_argument("--auto", action="store_true", help="Auto-discover latest baseline/hires/agentic results")
    args = parser.parse_args()

    file_paths: list[Path] = []

    if args.auto:
        for prefix in ("baseline", "hires", "agentic"):
            p = find_latest(prefix)
            if p:
                file_paths.append(p)
        if not file_paths:
            print("No result files found in eval/results/")
            sys.exit(1)
    else:
        for f in args.files:
            p = Path(f)
            if not p.is_absolute():
                p = RESULTS_DIR / p
            if not p.exists():
                print(f"File not found: {p}")
                sys.exit(1)
            file_paths.append(p)

    if not file_paths:
        parser.print_help()
        sys.exit(1)

    runs = []
    for p in file_paths:
        data = load_result(p)
        label = data.get("run_id") or p.stem
        runs.append((label, data))
        print(f"Loaded: {p.name}  ({data.get('total_questions', '?')} questions)")

    print_aggregate_table(runs)
    print_category_table(runs)
    print_regressions(runs)
    generate_chart(runs, RESULTS_DIR / "comparison.png")


if __name__ == "__main__":
    main()
