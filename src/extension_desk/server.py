"""MCP server: four tools. Run with `python -m extension_desk.server` (stdio transport)."""
from mcp.server.fastmcp import FastMCP
from . import core

mcp = FastMCP("extension-desk")

@mcp.tool()
def get_farm_context(household_id: str) -> dict:
    """Plot and crop-calendar context (crop, planting date, indicative growth stage, cluster, zone) for one household."""
    return core.get_farm_context(household_id)

@mcp.tool()
def check_weather_and_pest_evidence(household_id: str, days: int = 14) -> dict:
    """Rainfall summary for the household's zone and pest reports for its cluster. Returns evidence ids,
    plus explicit gaps (missing rainfall days, unverified or stale reports) and conflicts between reports."""
    return core.check_weather_and_pest_evidence(household_id, days)

@mcp.tool()
def draft_advisory_for_review(household_id: str, recommendations: list[dict], farmer_message: str, gaps: list[str]) -> dict:
    """Store a DRAFT advisory (never sent). Each recommendation needs: action, rationale, evidence_ids (from the evidence
    tools or NOTE:<file>), and confidence (high/medium/low). Rejected if any citation is missing or invalid, or if
    rainfall coverage is below 70% and confidence is not 'low'. farmer_message must be 320 characters or fewer."""
    return core.draft_advisory_for_review(household_id, recommendations, farmer_message, gaps)

@mcp.tool()
def submit_for_approval(draft_id: str) -> dict:
    """Queue a stored draft for a named extension officer. The agent cannot approve or send."""
    return core.submit_for_approval(draft_id)

def main() -> None:
    mcp.run()

if __name__ == "__main__":
    main()
