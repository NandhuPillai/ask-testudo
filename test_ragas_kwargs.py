import asyncio
from ragas.metrics.collections import ContextRecall
from ragas.dataset_schema import SingleTurnSample

async def main():
    # just create a mock
    from unittest.mock import MagicMock
    m = ContextRecall()
    
    sample = SingleTurnSample(
        user_input="q",
        retrieved_contexts=["c"],
        response="r",
        reference="ref"
    )
    
    # We want to see if we can unpack it
    kwargs = {k: v for k, v in sample.model_dump().items() if v is not None}
    print("Kwargs:", kwargs)
    try:
        # actually ascore expects to run an LLM, but we can just see if it raises TypeError for missing params
        await m.ascore(**kwargs)
    except TypeError as e:
        print("TypeError:", e)
    except Exception as e:
        print("Other Error:", e)

asyncio.run(main())
