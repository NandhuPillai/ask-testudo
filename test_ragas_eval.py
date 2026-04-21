import asyncio
from ragas import evaluate
from ragas.dataset_schema import SingleTurnSample, EvaluationDataset
from ragas.metrics.collections import ContextRecall
from ragas.llms import llm_factory
from anthropic import Anthropic
import os

from dotenv import load_dotenv
load_dotenv(".env")

anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
judge_llm = llm_factory(
    model="claude-haiku-4-5-20251001",
    provider="anthropic",
    client=Anthropic(api_key=anthropic_key),
)

m = ContextRecall(llm=judge_llm)

sample = SingleTurnSample(
    user_input="What is the capital of France?",
    retrieved_contexts=["Paris is the capital of France."],
    response="Paris",
    reference="Paris"
)

dataset = EvaluationDataset(samples=[sample])
results = evaluate(dataset, metrics=[m])
print(results)
