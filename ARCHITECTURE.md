# Architecture

```
 officer notes (md) --> [filesystem MCP server, borrowed]
                                  |
 Ollama (open-weights) <-> Pydantic AI agent <-> [extension-desk MCP server, ours] --> core.py --> SQLite (audit, drafts, outbox)
                                                                                        ^
 officer (human) ---- cli.py approve/reject (named) -----------------------------------+
```

**Agent shape.** One planning agent (Pydantic AI) that loops over a cluster's households: gather evidence, read notes,
draft, handle rejection by revising, submit. It stops at `awaiting_officer`. Planning and recovery come from the loop
plus tool errors that explain what to fix, not from a fixed script.

**Why logic lives in the tools, not the prompt.** Rules that must hold (cite real evidence, don't be confident on thin
rainfall, never send) are enforced in `core.py`, so a weak model cannot talk its way past them. The model's job is judgement
and wording; the tools' job is to refuse bad drafts.

**Built (MCP server `extension_desk.server`).** Four tools with boundaries a stranger could reuse: context lookup,
evidence aggregation, draft storage with validation, approval queueing. Evidence ids (`HH:`, `RF:`, `PR-`, `NOTE:`) make every
claim traceable.

**Borrowed.** `@modelcontextprotocol/server-filesystem`, sandboxed to `data/officer_notes/`. It beats writing our own because
path-sandboxing and file reading are solved and audited upstream, and officers' notes are the unstructured signal the
structured tools lack.

**Human gate.** `officer_decision` is deliberately not exposed over MCP. Approval requires a non-empty officer name,
a draft in `awaiting_officer`, and is logged. Approved messages land in `outbox` with `sent=0`.

**Data.** Synthetic (`scripts/generate_synthetic.py`), data stays local; the model runs locally via Ollama so records
need not leave the country. Swapping in CHIRPS/TAMSAT rainfall or consented cooperative records means replacing the
loaders in `core.py` only.

**Out of scope for this build.** Market-price intelligence, voice intake, live feeds, USSD/SMS delivery, multi-officer roles.
