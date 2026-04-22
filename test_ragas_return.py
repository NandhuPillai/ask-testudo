import asyncio
from ragas.metrics.collections import ContextRecall
from ragas.llms import llm_factory
from anthropic import AsyncAnthropic
import os
from dotenv import load_dotenv
load_dotenv('.env')

async def main():
    anthropic_key = os.environ.get('ANTHROPIC_API_KEY')
    client = AsyncAnthropic(api_key=anthropic_key)
    
    # monkeypatch messages.create
    original_create = client.messages.create
    async def mocked_create(*args, **kwargs):
        if 'top_p' in kwargs:
            del kwargs['top_p']
        return await original_create(*args, **kwargs)
    client.messages.create = mocked_create

    judge_llm = llm_factory(
        model='claude-haiku-4-5', 
        provider='anthropic', 
        client=client
    )

    m = ContextRecall(llm=judge_llm)
    
    try:
        res = await m.ascore(
            user_input="What is the capital of France?",
            retrieved_contexts=["Paris is the capital of France."],
            reference="Paris"
        )
        print("Result:", float(res))
    except Exception as e:
        print("Error:", e)

asyncio.run(main())
