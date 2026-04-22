import inspect
from ragas.metrics.collections import ContextPrecision, ContextRecall, Faithfulness, AnswerRelevancy

metrics = [ContextPrecision(), ContextRecall(), Faithfulness(), AnswerRelevancy()]
for m in metrics:
    print(f"--- {m.name} ---")
    print(inspect.signature(m.ascore))
