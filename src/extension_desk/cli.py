"""Officer-facing CLI. This is the human gate: only a named officer can approve here; the agent has no equivalent tool.
Usage:
  python -m extension_desk.cli pending
  python -m extension_desk.cli show D-xxxx
  python -m extension_desk.cli approve D-xxxx --officer "Name"   (or: reject D-xxxx --officer "Name" --note "why")
  python -m extension_desk.cli audit
  python -m extension_desk.cli demo        (deterministic smoke test, NO model involved)
"""
import argparse, json
from . import core

def _print(o): print(json.dumps(o, indent=2, default=str))

def demo() -> None:
    """Scripted walk through all four tools on the messiest household (HH-007). Not an agent: it proves the tools,
    validation and approval gate work. The agent run is agent/run_agent.py."""
    print("1) context");  ctx = core.get_farm_context("HH-007"); _print(ctx)
    print("2) evidence"); ev = core.check_weather_and_pest_evidence("HH-007"); _print(ev)
    rf, pr = ev["rainfall"]["evidence_id"], ev["pest_reports"][0]["evidence_id"]
    print("3) draft with HIGH confidence on thin rainfall (should be rejected)")
    _print(core.draft_advisory_for_review("HH-007", [{"action": "Delay top-dressing", "rationale": "rainfall pattern",
          "evidence_ids": [rf], "confidence": "high"}], "x", []))
    print("4) honest draft")
    d = core.draft_advisory_for_review("HH-007", [
        {"action": "Scout whorls for fall armyworm before any spraying", "rationale": "Officer-verified low-severity report in cluster, 15 days old",
         "evidence_ids": [pr, "NOTE:field_notes.md"], "confidence": "medium"},
        {"action": "Hold top-dressing until rainfall is confirmed", "rationale": "Only 43% of rainfall days have data (6 of 14); gauge unreadable per officer note",
         "evidence_ids": [rf, "NOTE:field_notes.md"], "confidence": "low"}],
        "Check maize whorls for armyworm this week. Delay fertiliser until your officer confirms rains.",
        ev["gaps"]); _print(d)
    print("5) submit"); _print(core.submit_for_approval(d["draft_id"]))
    print(f"\nNothing was sent. Approve as a named officer with:\n  python -m extension_desk.cli approve {d['draft_id']} --officer \"Your Name\"")

def main() -> None:
    p = argparse.ArgumentParser(); sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("pending"); sub.add_parser("audit"); sub.add_parser("demo")
    s = sub.add_parser("show"); s.add_argument("draft_id")
    for name in ("approve", "reject"):
        a = sub.add_parser(name); a.add_argument("draft_id"); a.add_argument("--officer", required=True); a.add_argument("--note", default="")
    args = p.parse_args()
    if args.cmd == "demo": return demo()
    with core._conn() as c:
        if args.cmd == "pending":
            _print([dict(r) for r in c.execute("SELECT draft_id,household_id,status,created_ts FROM drafts WHERE status='awaiting_officer'")])
        elif args.cmd == "show":
            r = c.execute("SELECT * FROM drafts WHERE draft_id=?", (args.draft_id,)).fetchone()
            _print({**dict(r), "payload": json.loads(r["payload"])} if r else {"error": "unknown draft"})
        elif args.cmd == "audit":
            _print([dict(r) for r in c.execute("SELECT ts,actor,tool,status,inputs,outputs FROM audit_log ORDER BY id")])
    if args.cmd in ("approve", "reject"):
        _print(core.officer_decision(args.draft_id, args.officer, args.cmd == "approve", args.note))

if __name__ == "__main__":
    main()
