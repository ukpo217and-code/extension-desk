"""Run every task N times against the real agent and record pass/fail from the database state.
  python -m evals.run_evals 3      # 3 repetitions per task -> evals/results.json + markdown table
Requires the agent dependencies and Ollama. Results are whatever actually happened; nothing is curated."""
import asyncio, json, os, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
os.environ["EXTENSION_DESK_DB"] = str(ROOT / "evals" / "eval.db")   # before importing core
sys.path.insert(0, str(ROOT / "src")); sys.path.insert(0, str(ROOT / "agent"))
from evals.checks import TASKS
import run_agent

async def one(prompt: str) -> str:
    return await run_agent.run_prompt(prompt)

def main(n: int) -> None:
    results = []
    for tid, name, prompt, check in TASKS:
        for i in range(n):
            Path(os.environ["EXTENSION_DESK_DB"]).unlink(missing_ok=True)
            try:
                out = asyncio.run(one(prompt)); err = None
            except Exception as e:  # a crashed run is a failed run, recorded as such
                out, err = "", f"{type(e).__name__}: {e}"
            fails = [f"run crashed: {err}"] if err else check()
            results.append(dict(task=tid, name=name, run=i + 1, passed=not fails, failures=fails, final_text=out))
            print(f"{tid} run {i+1}: {'PASS' if not fails else 'FAIL ' + '; '.join(fails)}")
    (ROOT / "evals" / "results.json").write_text(json.dumps(results, indent=2))
    print("\n| Task | Name | Passes |\n|---|---|---|")
    for tid, name, *_ in TASKS:
        rs = [r for r in results if r["task"] == tid]
        print(f"| {tid} | {name} | {sum(r['passed'] for r in rs)}/{len(rs)} |")

if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 3)
