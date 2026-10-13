"""Pure-Python logic behind the MCP tools. No MCP dependency, so it is unit-testable.

Design rules (from the challenge brief):
  * every tool call is written to an audit log (inputs, outputs, timestamp, actor)
  * the agent can DRAFT and SUBMIT, never APPROVE or SEND; approval happens in cli.py by a named officer
  * every recommendation must cite evidence ids that actually exist
"""
from __future__ import annotations

import csv, functools, inspect, json, os, re, sqlite3, uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = Path(os.environ.get("EXTENSION_DESK_DATA", ROOT / "data" / "synthetic"))
NOTES = Path(os.environ.get("EXTENSION_DESK_NOTES", ROOT / "data" / "officer_notes"))
DB_PATH = Path(os.environ.get("EXTENSION_DESK_DB", ROOT / "data" / "audit.db"))
AS_OF = date.fromisoformat(os.environ.get("EXTENSION_DESK_AS_OF", "2026-10-12"))  # fixed for reproducibility
MIN_COVERAGE = 0.7          # below this, rainfall-based advice must be marked low confidence
STALE_DAYS = 10             # pest reports older than this are flagged stale
CONFIDENCE = {"high", "medium", "low"}

# ---------------------------------------------------------------- storage
def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    c.executescript("""
    CREATE TABLE IF NOT EXISTS audit_log(id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, actor TEXT, tool TEXT,
        inputs TEXT, outputs TEXT, status TEXT);
    CREATE TABLE IF NOT EXISTS drafts(draft_id TEXT PRIMARY KEY, household_id TEXT, created_ts TEXT, status TEXT,
        payload TEXT, officer TEXT, decision_ts TEXT, decision_note TEXT);
    CREATE TABLE IF NOT EXISTS outbox(draft_id TEXT PRIMARY KEY, channel TEXT, message TEXT, approved_by TEXT,
        approved_ts TEXT, sent INTEGER DEFAULT 0, note TEXT);
    """)
    return c

def log(actor: str, tool: str, inputs, outputs, status: str) -> None:
    with _conn() as c:
        c.execute("INSERT INTO audit_log(ts,actor,tool,inputs,outputs,status) VALUES(?,?,?,?,?,?)",
                  (datetime.now(timezone.utc).isoformat(), actor, tool,
                   json.dumps(inputs, default=str), json.dumps(outputs, default=str), status))

def audited(fn):
    """Log every tool call: inputs, outputs, timestamp. Exceptions become error results so the agent can recover."""
    sig = inspect.signature(fn)
    @functools.wraps(fn)
    def wrapper(*a, **kw):
        inputs = dict(sig.bind(*a, **kw).arguments)
        try:
            out = fn(*a, **kw)
        except Exception as e:  # noqa: BLE001
            out = {"error": f"{type(e).__name__}: {e}"}
        status = "error" if isinstance(out, dict) and "error" in out else "ok"
        log("agent", fn.__name__, inputs, out, status)
        return out
    return wrapper

# ---------------------------------------------------------------- data loading
def _households() -> dict:
    return {h["household_id"]: h for h in json.loads((DATA / "households.json").read_text())}

def _pests() -> list:
    return json.loads((DATA / "pest_reports.json").read_text())

def _rain(zone: str) -> dict:
    out = {}
    with open(DATA / "rainfall.csv") as f:
        for r in csv.DictReader(f):
            if r["zone_id"] == zone:
                out[date.fromisoformat(r["date"])] = float(r["rain_mm"]) if r["rain_mm"] != "" else None
    return out

# Simplified stage tables (days after planting). Indicative only; the officer's local calendar overrides.
_STAGES = {
    "maize": [(14, "emergence"), (35, "vegetative"), (60, "tasseling/silking"), (100, "grain fill")],
    "rice":  [(21, "seedling"), (55, "tillering"), (90, "panicle initiation to flowering")],
}
def _stage(crop: str, dap: int) -> str:
    for limit, name in _STAGES[crop]:
        if dap <= limit:
            return name
    return "maturity/ripening"

# ---------------------------------------------------------------- tool 1
@audited
def get_farm_context(household_id: str) -> dict:
    """Plot and crop-calendar context for one (synthetic) household."""
    h = _households().get(household_id)
    if not h:
        return {"error": f"unknown household_id {household_id!r}", "known": sorted(_households())}
    dap = (AS_OF - date.fromisoformat(h["planting_date"])).days
    return {**h, "as_of": AS_OF.isoformat(), "days_after_planting": dap,
            "growth_stage_indicative": _stage(h["crop"], dap), "evidence_id": f"HH:{household_id}"}

# ---------------------------------------------------------------- tool 2
@audited
def check_weather_and_pest_evidence(household_id: str, days: int = 14) -> dict:
    """Rainfall summary for the household's zone plus pest reports for its cluster, with gaps/conflicts flagged."""
    h = _households().get(household_id)
    if not h:
        return {"error": f"unknown household_id {household_id!r}"}
    days = max(3, min(int(days), 21))
    end = AS_OF
    start = end - timedelta(days=days - 1)
    window = [start + timedelta(days=i) for i in range(days)]
    rain = _rain(h["zone_id"])
    known = [d for d in window if rain.get(d) is not None]
    missing = [d.isoformat() for d in window if rain.get(d) is None]
    longest = run = 0
    for d in window:                       # a missing day breaks a dry run: we only count CONFIRMED dry days
        v = rain.get(d)
        run = run + 1 if (v is not None and v < 1.0) else 0
        longest = max(longest, run)
    coverage = round(len(known) / days, 2)
    gaps = []
    if missing:
        gaps.append(f"rainfall missing for {len(missing)} of {days} days ({', '.join(missing)}); zero is NOT assumed")
    if coverage < MIN_COVERAGE:
        gaps.append(f"rainfall coverage {coverage} is below {MIN_COVERAGE}: rainfall-based advice must be low confidence")

    pests, excluded = [], []
    for p in _pests():
        if h["crop"] not in p["crops"]:
            continue
        if p["cluster_id"] is None:
            excluded.append({"report_id": p["report_id"], "reason": "location unclear, cannot attribute to this cluster"})
            continue
        if p["cluster_id"] != h["cluster_id"]:
            continue
        age = (AS_OF - date.fromisoformat(p["date"])).days
        pests.append({"evidence_id": p["report_id"], "date": p["date"], "pest": p["pest"], "severity": p["severity"],
                      "source": p["source"], "verified": p["verified"], "age_days": age, "stale": age > STALE_DAYS})
    conflicts = []
    by_pest: dict = {}
    for p in pests:
        by_pest.setdefault(p["pest"], []).append(p)
    for pest, rs in by_pest.items():
        if len({r["severity"] for r in rs}) > 1:
            conflicts.append(f"{pest}: reports disagree on severity ("
                             + "; ".join(f"{r['evidence_id']}={r['severity']}, verified={r['verified']}" for r in rs) + ")")
    for p in pests:
        if not p["verified"]:
            gaps.append(f"{p['evidence_id']} is unverified ({p['source']})")
        if p["stale"]:
            gaps.append(f"{p['evidence_id']} is stale ({p['age_days']} days old)")
    if excluded:
        gaps.append(f"{len(excluded)} pest report(s) excluded for unclear location")
    return {"household_id": household_id, "crop": h["crop"],
            "rainfall": {"evidence_id": f"RF:{h['zone_id']}:{start}..{end}", "zone": h["zone_id"],
                         "days_requested": days, "days_with_data": len(known), "coverage": coverage,
                         "total_mm": round(sum(rain[d] for d in known), 1),
                         "rainy_days": sum(1 for d in known if rain[d] >= 1.0),
                         "longest_confirmed_dry_spell_days": longest, "missing_dates": missing},
            "pest_reports": pests, "excluded_reports": excluded, "conflicts": conflicts, "gaps": gaps}

# ---------------------------------------------------------------- evidence validation
def _validate_evidence(eid: str, h: dict, confidence: str) -> str | None:
    """Return an error string, or None if the citation is real and appropriate."""
    if eid == f"HH:{h['household_id']}":
        return None
    if re.fullmatch(r"PR-\d{3}", eid):
        rep = next((p for p in _pests() if p["report_id"] == eid), None)
        if not rep:
            return f"{eid}: no such pest report"
        if rep["cluster_id"] != h["cluster_id"]:
            return f"{eid}: not a report for this household's cluster"
        return None
    m = re.fullmatch(r"RF:([\w-]+):(\d{4}-\d{2}-\d{2})\.\.(\d{4}-\d{2}-\d{2})", eid)
    if m:
        zone, s, e = m.group(1), date.fromisoformat(m.group(2)), date.fromisoformat(m.group(3))
        if zone != h["zone_id"]:
            return f"{eid}: rainfall zone does not match this household's zone {h['zone_id']}"
        rain, n = _rain(zone), (e - s).days + 1
        if n < 1 or n > 21:
            return f"{eid}: invalid window"
        have = sum(1 for i in range(n) if rain.get(s + timedelta(days=i)) is not None)
        if have / n < MIN_COVERAGE and confidence != "low":
            return f"{eid}: rainfall coverage {have}/{n} is below {MIN_COVERAGE}; confidence must be 'low'"
        return None
    m = re.fullmatch(r"NOTE:([\w.\-]+)", eid)
    if m:
        return None if (NOTES / m.group(1)).is_file() else f"{eid}: no such officer note file"
    return f"{eid}: unrecognised evidence id format"

# ---------------------------------------------------------------- tool 3 (action)
@audited
def draft_advisory_for_review(household_id: str, recommendations: list[dict], farmer_message: str, gaps: list[str]) -> dict:
    """Store a DRAFT advisory. Each recommendation: {action, rationale, evidence_ids[], confidence}.
    Rejected unless every recommendation cites real evidence. Nothing is sent to anyone."""
    h = _households().get(household_id)
    if not h:
        return {"error": f"unknown household_id {household_id!r}"}
    if not recommendations or len(recommendations) > 5:
        return {"error": "provide 1-5 recommendations"}
    if len(farmer_message) > 320:
        return {"error": f"farmer_message is {len(farmer_message)} chars; SMS/USSD limit is 320"}
    problems = []
    for i, r in enumerate(recommendations):
        if not r.get("action") or not r.get("rationale"):
            problems.append(f"rec {i}: action and rationale are required")
        if r.get("confidence") not in CONFIDENCE:
            problems.append(f"rec {i}: confidence must be one of {sorted(CONFIDENCE)}")
        if not r.get("evidence_ids"):
            problems.append(f"rec {i}: no evidence_ids; unsourced recommendations are rejected")
            continue
        for eid in r["evidence_ids"]:
            err = _validate_evidence(eid, h, r.get("confidence", ""))
            if err:
                problems.append(f"rec {i}: {err}")
    if problems:
        return {"error": "draft rejected", "problems": problems}
    draft_id = "D-" + uuid.uuid4().hex[:8]
    payload = {"recommendations": recommendations, "farmer_message": farmer_message, "gaps": gaps}
    with _conn() as c:
        c.execute("INSERT INTO drafts(draft_id,household_id,created_ts,status,payload) VALUES(?,?,?,?,?)",
                  (draft_id, household_id, datetime.now(timezone.utc).isoformat(), "pending_submission", json.dumps(payload)))
    return {"draft_id": draft_id, "status": "pending_submission", "sent_to_farmer": False,
            "next": "call submit_for_approval so a named officer can review"}

# ---------------------------------------------------------------- tool 4 (action)
@audited
def submit_for_approval(draft_id: str) -> dict:
    """Queue a draft for the extension officer. The agent cannot approve; approval is a separate human CLI step."""
    with _conn() as c:
        row = c.execute("SELECT status FROM drafts WHERE draft_id=?", (draft_id,)).fetchone()
        if not row:
            return {"error": f"unknown draft_id {draft_id!r}"}
        if row["status"] != "pending_submission":
            return {"error": f"draft is already {row['status']}"}
        c.execute("UPDATE drafts SET status='awaiting_officer' WHERE draft_id=?", (draft_id,))
    return {"draft_id": draft_id, "status": "awaiting_officer", "sent_to_farmer": False,
            "message": "Queued. Nothing reaches a farmer until a named officer approves via the CLI."}

# ---------------------------------------------------------------- human step (NOT an MCP tool)
def officer_decision(draft_id: str, officer: str, approve: bool, note: str = "") -> dict:
    if not officer or not officer.strip():
        return {"error": "a named officer is required"}
    with _conn() as c:
        row = c.execute("SELECT * FROM drafts WHERE draft_id=?", (draft_id,)).fetchone()
        if not row:
            return {"error": f"unknown draft_id {draft_id!r}"}
        if row["status"] != "awaiting_officer":
            return {"error": f"draft is {row['status']}, not awaiting_officer"}
        now = datetime.now(timezone.utc).isoformat()
        status = "approved" if approve else "rejected"
        c.execute("UPDATE drafts SET status=?,officer=?,decision_ts=?,decision_note=? WHERE draft_id=?",
                  (status, officer, now, note, draft_id))
        if approve:
            payload = json.loads(row["payload"])
            ch = _households()[row["household_id"]]["preferred_channel"]
            c.execute("INSERT INTO outbox(draft_id,channel,message,approved_by,approved_ts,sent,note) VALUES(?,?,?,?,?,0,?)",
                      (draft_id, ch, payload["farmer_message"], officer, now,
                       "SIMULATED: this prototype never sends. Dispatch is a manual officer action."))
    out = {"draft_id": draft_id, "status": status, "officer": officer}
    log(officer, "officer_decision", {"draft_id": draft_id, "approve": approve, "note": note}, out, "ok")
    return out
