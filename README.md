# Extension Desk

An agent that drafts **sourced, officer-approved climate-smart advisories** for an agricultural extension office.
Built for the Agentic AI for Africa Innovation Challenge, Agriculture track ("The Extension Backlog"), theme: *Climate-smart advisory*.

**Office and workflow served:** a small LGA-level extension desk (synthetic setting: Lokoja area, maize and rice clusters).
Signals in (rainfall, pest reports, officer notes, plot records) -> household-level advisory **drafts** out -> a named officer approves.

> **Everything in `data/` is synthetic.** No real household, rainfall or pest records are used. The synthetic set is
> deliberately messy (missing rainfall days, a conflicting and an unverified pest report, a report with unclear location).
> Live rainfall (CHIRPS/TAMSAT), pest feeds, market prices and speech transcription are **not** integrated.

## Hard rules, enforced in code (not just in the prompt)
- The agent has **no tool that approves or sends**. Approval is `python -m extension_desk.cli approve` by a named officer.
- `draft_advisory_for_review` **rejects** any recommendation with no evidence ids, an invalid or other-cluster id, or
  `high`/`medium` confidence when rainfall coverage is under 70%.
- Every tool call is logged (inputs, outputs, timestamp, actor) in `data/audit.db`; officer decisions are logged by name.
- This prototype never sends a message. Approved drafts go to an `outbox` table marked `sent=0`.

## Run it (one command, no model needed)
```bash
pip install -e . && python -m extension_desk.cli demo
```
This walks all four tools on the messiest household, shows an overconfident draft being rejected, then an honest draft
queued for approval. It is a **deterministic smoke test, not the agent**. Then, as the officer:
```bash
python -m extension_desk.cli pending
python -m extension_desk.cli approve <draft_id> --officer "Your Name"
python -m extension_desk.cli audit
```
Tests: `PYTHONPATH=src:. python -m unittest discover -s tests -t .` (19 tests, all passing at time of writing). Agent evals: `python -m evals.run_evals 3` (see EVALS.md).

## Run the agent (open-weights model)
```bash
ollama pull qwen2.5:7b-instruct
pip install -e ".[agent]"
python agent/run_agent.py C-KOTON
```
Needs Ollama and Node (for the borrowed filesystem MCP server). **Status: `agent/run_agent.py` has not been run end to end
yet**; see EVALS.md for what has and has not been measured.

## Tools (our MCP server, `extension_desk.server`)
| Tool | Kind | Purpose |
|---|---|---|
| `get_farm_context` | read | crop, planting date, indicative growth stage, cluster, zone |
| `check_weather_and_pest_evidence` | read | rainfall summary + cluster pest reports, with gaps and conflicts flagged |
| `draft_advisory_for_review` | action | stores a validated draft; rejects unsourced or overconfident advice |
| `submit_for_approval` | action | queues a draft for the officer; cannot approve |

Borrowed MCP server: the official filesystem server, to read the officer's own unstructured field notes (see ARCHITECTURE.md).

## Known limits
Growth-stage tables and thresholds are simplified placeholders for an officer's local calendar. Synthetic data is cleaner
than real records in most ways. Single-season window, two rainfall zones, nine households.

## Licence
MIT. Built during the challenge submission period; reuses ideas from the author's earlier FarmerPulse work, no code
from it is resubmitted (confirm the build-window rules with the organisers).
