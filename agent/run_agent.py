"""Agent runner (Pydantic AI + MCP, open-weights model via Ollama's OpenAI-compatible API).

STATUS: written against pydantic-ai >= 1.0 but NOT yet executed end to end. Verify the imports/toolset API against
your installed version before recording the demo. The tools it calls ARE tested (tests/test_core.py).

  ollama pull qwen2.5:7b-instruct   # or any open-weights model with tool calling
  pip install -e ".[agent]"
  python agent/run_agent.py C-KOTON
"""
import asyncio, os, sys
from pathlib import Path

from pydantic_ai import Agent
from pydantic_ai.mcp import MCPServerStdio
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

ROOT = Path(__file__).resolve().parents[1]
MODEL = os.environ.get("EXTENSION_DESK_MODEL", "qwen2.5:7b-instruct")
BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434/v1")

SYSTEM = """You assist an agricultural extension officer. You DRAFT advisories; you never approve or send anything.
Plan before acting. For the cluster you are given:
1. Find its households (HH-001..HH-009; get_farm_context tells you the cluster).
2. For each household call check_weather_and_pest_evidence. Read the gaps and conflicts carefully.
3. Read the officer notes with the filesystem tool (cite them as NOTE:<filename>).
4. Draft ONE advisory per household with draft_advisory_for_review. Cite only evidence ids returned by tools.
   If rainfall coverage is below 70%, confidence must be 'low' and you must say what is unknown.
   If reports conflict or are unverified, say so; do not pick the scarier one.
5. If a draft is rejected, read the problems, fix them, and retry. Do not invent evidence ids.
6. Call submit_for_approval for each accepted draft. Then summarise what is waiting for the officer and what you could not verify."""

async def run_prompt(prompt: str) -> str:
    ours = MCPServerStdio(sys.executable, args=["-m", "extension_desk.server"], cwd=str(ROOT), env={**os.environ, "PYTHONPATH": str(ROOT / "src")})
    borrowed = MCPServerStdio("npx", args=["-y", "@modelcontextprotocol/server-filesystem", str(ROOT / "data" / "officer_notes")])
    model = OpenAIChatModel(MODEL, provider=OpenAIProvider(base_url=BASE_URL, api_key="ollama"))
    agent = Agent(model, system_prompt=SYSTEM, toolsets=[ours, borrowed])
    async with agent:
        result = await agent.run(prompt)
    return result.output

async def main(cluster: str) -> None:
    print(await run_prompt(f"Prepare advisories for every household in cluster {cluster} for review."))
    print("\nPending approval: python -m extension_desk.cli pending")

if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "C-KOTON"))
