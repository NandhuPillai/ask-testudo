"""
RAGAS evaluation runner for ask-testudo.

Usage:
    python eval/run_eval.py --output baseline
    python eval/run_eval.py --output hires
    python eval/run_eval.py --output agentic

Requires:
    - ask-testudo backend running at http://localhost:8002
    - .venv-eval activated (pip install -r eval/requirements_eval.txt)
    - ANTHROPIC_API_KEY and COHERE_API_KEY in environment or .env
"""

import argparse
import asyncio
import json
import os
import sys
from datetime import date
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

BACKEND_URL = "http://localhost:8002"
GOLDEN_DATASET_PATH = Path(__file__).parent / "golden_dataset.json"
RESULTS_DIR = Path(__file__).parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)


def load_golden_dataset() -> list[dict]:
    with open(GOLDEN_DATASET_PATH, encoding="utf-8") as f:
        return json.load(f)


def query_backend(question: str) -> dict:
    resp = requests.post(
        f"{BACKEND_URL}/ask_with_contexts",
        json={"question": question, "stream": False, "history": []},
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()


def collect_responses(dataset: list[dict]) -> list[dict]:
    results = []
    for i, item in enumerate(dataset):
        print(f"  [{i+1}/{len(dataset)}] {item['id']}: {item['question'][:60]}...")
        try:
            response = query_backend(item["question"])
            results.append({
                "id": item["id"],
                "category": item["category"],
                "question": item["question"],
                "ground_truth": item["ground_truth_answer"],
                "answer": response.get("answer", ""),
                "contexts": response.get("retrieved_contexts", []),
                "rerank_score": response.get("rerank_score", 0.0),
                "confidence": response.get("confidence", "low"),
                "fallback": response.get("fallback", False),
                "expected_fallback": item["expected_fallback"],
                "expected_confidence": item["expected_confidence"],
            })
        except Exception as exc:
            print(f"    ERROR: {exc}")
            results.append({
                "id": item["id"],
                "category": item["category"],
                "question": item["question"],
                "ground_truth": item["ground_truth_answer"],
                "answer": "",
                "contexts": [],
                "rerank_score": 0.0,
                "confidence": "low",
                "fallback": True,
                "expected_fallback": item["expected_fallback"],
                "expected_confidence": item["expected_confidence"],
                "error": str(exc),
            })
    return results


async def _score_all(metrics, samples) -> list[dict]:
    """Score every sample against every metric concurrently."""
    import inspect

    async def score_one(sample):
        scores = {}
        for metric in metrics:
            try:
                sig = inspect.signature(metric.ascore)
                kwargs = {}
                if "user_input" in sig.parameters: kwargs["user_input"] = sample.user_input
                if "response" in sig.parameters: kwargs["response"] = sample.response
                if "reference" in sig.parameters: kwargs["reference"] = sample.reference
                if "retrieved_contexts" in sig.parameters: kwargs["retrieved_contexts"] = sample.retrieved_contexts
                
                res = await metric.ascore(**kwargs)
                scores[metric.name] = float(res)
            except Exception as exc:
                print(f"    scoring error ({metric.name}): {exc}")
                scores[metric.name] = None
        return scores

    return await asyncio.gather(*[score_one(s) for s in samples])


def run_ragas_evaluation(responses: list[dict]) -> tuple[list[dict], list[str]]:
    """
    Score all responses with RAGAS v2 metrics using direct .ascore() calls.
    Returns (raw_scores, metric_names).
    raw_scores is a list[dict] — one dict per response, keyed by metric name.
    """
    from ragas.metrics.collections import ContextPrecision, ContextRecall, Faithfulness, AnswerRelevancy
    from ragas.dataset_schema import SingleTurnSample
    from ragas.llms import llm_factory
    from ragas.embeddings import LiteLLMEmbeddings
    from anthropic import AsyncAnthropic

    anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
    if not anthropic_key:
        print("ERROR: ANTHROPIC_API_KEY not set. Add it to your .env file.")
        sys.exit(1)

    anthropic_client = AsyncAnthropic(api_key=anthropic_key)
    
    # Monkeypatch to avoid temperature/top_p parameter conflict with claude-haiku-4-5
    original_create = anthropic_client.messages.create
    async def mocked_create(*args, **kwargs):
        if 'top_p' in kwargs:
            del kwargs['top_p']
        return await original_create(*args, **kwargs)
    anthropic_client.messages.create = mocked_create

    judge_llm = llm_factory(
        model="claude-haiku-4-5",
        provider="anthropic",
        client=anthropic_client,
    )

    judge_embeddings = LiteLLMEmbeddings(
        model="cohere/embed-english-v3.0",
        api_key=os.environ.get("COHERE_API_KEY"),
    )

    metrics = [
        ContextPrecision(llm=judge_llm),
        ContextRecall(llm=judge_llm),
        Faithfulness(llm=judge_llm),
        AnswerRelevancy(llm=judge_llm, embeddings=judge_embeddings),
    ]
    metric_names = [m.name for m in metrics]

    samples = [
        SingleTurnSample(
            user_input=r["question"],
            retrieved_contexts=r["contexts"] if r["contexts"] else [""],
            response=r["answer"],
            reference=r["ground_truth"],
        )
        for r in responses
    ]

    print(f"  Scoring {len(samples)} samples × {len(metrics)} metrics via asyncio ...")
    raw_scores = asyncio.run(_score_all(metrics, samples))
    return raw_scores, metric_names


def compute_per_category(responses: list[dict], raw_scores: list[dict], metric_names: list[str]) -> dict:
    categories: dict[str, dict[str, list]] = {}
    for resp, scores in zip(responses, raw_scores):
        cat = resp["category"]
        if cat not in categories:
            categories[cat] = {k: [] for k in metric_names}
        for k in metric_names:
            v = scores.get(k)
            if v is not None:
                categories[cat][k].append(float(v))

    return {
        cat: {k: round(sum(v) / len(v), 4) if v else None for k, v in s.items()}
        for cat, s in categories.items()
    }


def compute_per_question(responses: list[dict], raw_scores: list[dict], metric_names: list[str]) -> list[dict]:
    per_question = []
    for resp, scores in zip(responses, raw_scores):
        q_scores = {
            k: (round(float(scores[k]), 4) if scores.get(k) is not None else None)
            for k in metric_names
        }
        per_question.append({
            "id": resp["id"],
            "category": resp["category"],
            "question": resp["question"],
            "fallback": resp["fallback"],
            "expected_fallback": resp["expected_fallback"],
            "rerank_score": resp["rerank_score"],
            "confidence": resp["confidence"],
            **q_scores,
        })
    return per_question


def print_summary_table(aggregate: dict, per_category: dict, metric_names: list[str]):
    abbrev = {n: n[:2].upper() for n in metric_names}
    abbrev.update({
        "context_precision": "CP",
        "context_recall": "CR",
        "faithfulness": "F ",
        "answer_relevancy": "AR",
    })

    print("\n" + "=" * 60)
    print("RAGAS EVALUATION RESULTS")
    print("=" * 60)
    print(f"{'Metric':<25} {'Score':>8}")
    print("-" * 35)
    for k, v in aggregate.items():
        print(f"  {k:<23} {v:>8.4f}" if v is not None else f"  {k:<23} {'N/A':>8}")

    print("\nPer-category breakdown:")
    header = f"{'Category':<25}" + "".join(f"{abbrev.get(k, k[:4]):>8}" for k in metric_names)
    print(header)
    print("-" * (25 + 8 * len(metric_names)))
    for cat, scores in per_category.items():
        row = f"  {cat:<23}"
        for k in metric_names:
            v = scores.get(k)
            row += f" {v:>7.4f}" if v is not None else f" {'N/A':>7}"
        print(row)
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, help="Output prefix: baseline, hires, or agentic")
    parser.add_argument("--skip-ragas", action="store_true", help="Only collect responses, skip RAGAS scoring")
    args = parser.parse_args()

    print(f"Loading golden dataset from {GOLDEN_DATASET_PATH}")
    dataset = load_golden_dataset()
    print(f"Loaded {len(dataset)} questions")

    print(f"\nQuerying backend at {BACKEND_URL} ...")
    try:
        health = requests.get(f"{BACKEND_URL}/health", timeout=10)
        health.raise_for_status()
        print(f"Backend health: {health.json()}")
    except Exception as exc:
        print(f"ERROR: Cannot reach backend at {BACKEND_URL}: {exc}")
        print("Start the backend with: uvicorn query:app --port 8002")
        sys.exit(1)

    responses = collect_responses(dataset)
    print(f"\nCollected {len(responses)} responses ({sum(1 for r in responses if r.get('error'))} errors)")

    if args.skip_ragas:
        output_path = RESULTS_DIR / f"{args.output}_{date.today()}_responses.json"
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(responses, f, indent=2, ensure_ascii=False)
        print(f"\nResponses saved to {output_path} (RAGAS scoring skipped)")
        return

    print("\nRunning RAGAS evaluation (this takes a few minutes) ...")
    raw_scores, metric_names = run_ragas_evaluation(responses)

    aggregate = {
        k: round(
            sum(s[k] for s in raw_scores if s.get(k) is not None) /
            max(1, sum(1 for s in raw_scores if s.get(k) is not None)),
            4,
        )
        for k in metric_names
    }

    per_category = compute_per_category(responses, raw_scores, metric_names)
    per_question = compute_per_question(responses, raw_scores, metric_names)

    output = {
        "run_id": f"{args.output}_{date.today()}",
        "pipeline_version": args.output,
        "total_questions": len(dataset),
        "metrics": aggregate,
        "per_category": per_category,
        "per_question": per_question,
    }

    output_path = RESULTS_DIR / f"{args.output}_{date.today()}.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print_summary_table(aggregate, per_category, metric_names)
    print(f"\nResults saved to {output_path}")


if __name__ == "__main__":
    main()
