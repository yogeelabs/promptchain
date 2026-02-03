# PromptChain — Agent Instructions (AGENTS.md)

This document defines **how agents (human or AI)** should work inside this repository.
It is a guardrail against over-engineering, drift, and breaking core invariants.

Agents must read this before making changes.

---

## 1. Purpose of This File

AGENTS.md exists to ensure that:
- changes are intentional and minimal
- work aligns with URD → PRD → Architecture → Plan
- the codebase always **runs**, even if incomplete
- agents do not invent scope or abstractions

If something is unclear, **refer to the docs first**, not the code.

---

## 2. Canonical Documents (Read Order)

Before coding, agents must consult these documents **in order**:

1. `URD.md` — user needs and expectations
2. `docs/PRD.md` — product scope and guarantees
3. `docs/architecture.md` — system responsibilities
4. `docs/plan.md` — phases and milestones
5. `docs/Checklist.md` — acceptance criteria (when present)

Code must never contradict these documents.

---

## 3. Allowed Scope (MVP)

Agents must NOT implement features outside the current phase.

Explicitly out of scope unless the plan says otherwise:
- autonomous agents or planners
- reduce/merge stages
- review or critique automation
- PDF or document ingestion
- UI or dashboards
- background services or daemons

If tempted to add these, stop and re-check `plan.md`.

---

## 4. Required Development Workflow

### 4.0 Standard Commands (Format / Lint / Tests / Smoke)

Run these from repo root:
```zsh
scripts/format.zsh
scripts/lint.zsh
scripts/test.zsh
scripts/smoke_placeholder.zsh
```

### 4.1 Python Environment
Use a local virtual environment.

Required commands:
```zsh
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

If dependencies are not finalized, keep `requirements.txt` minimal.

### 4.1.1 Adding Dependencies (Libraries, Tools, Test Utilities)
Agents are allowed to add Python libraries (e.g., pytest, pdf/text parsers, yaml, http clients) only when required by the current phase.

Any new dependency must be added to `requirements.txt` with a brief comment explaining *why* it was added.

Installing libraries globally or via ad-hoc commands without updating `requirements.txt` is prohibited.

Agents should prefer the **standard library first**, then small, widely-used libraries.

After any dependency changes, agents must re-run smoke tests to verify stability.

---

### 4.2 Running the Project
Agents must ensure the project runs end-to-end after changes.

Canonical command (example):
```zsh
python -m promptchain.cli run --pipeline pipelines/fanout_personas_jtbd.yaml --topic chess
```

If functionality is not yet implemented, the command must:
- fail gracefully
- emit a clear error message
- not crash silently

---

### 4.3 Smoke Testing
If no test framework exists yet:
- provide a **smoke script** under `scripts/`
- smoke script must be written in **zsh**
- script should verify:
  - project starts
  - a run directory is created
  - expected files or placeholders exist

Example:
```zsh
scripts/smoke_fanout.zsh
```

Agents must run the smoke script before considering work complete.

---

## 5. Definition of Done (For Any Change)

A change is considered **done** only if:

- [ ] Code compiles / runs
- [ ] Smoke script passes (or fails clearly if dependencies missing)
- [ ] No existing behavior is broken
- [ ] Scope matches current phase in `plan.md`
- [ ] Docs are updated *only if* behavior changed

---

## 6. Guardrails & Invariants

Agents must preserve these invariants:

- Prompts remain **simple English**
- JSON is the **control plane**
- Markdown is never parsed back into JSON
- Runs are immutable snapshots
- Outputs are inspectable files
- Final deliverables are separated from intermediate artifacts

Violating these invariants requires explicit discussion and doc updates.

---

## 7. Error Handling Expectations

When adding or modifying code:
- always save raw model output
- failures must identify:
  - stage
  - item (for fan-out)
- earlier successful outputs must not be destroyed

Silent failures are unacceptable.

---

## 8. When Unsure What to Do

Agents must:
1. Check `plan.md` to see the current phase
2. Re-read URD/PRD requirements
3. Choose the **simplest possible implementation**
4. Ask for clarification rather than guessing

---

## 9. Tone & Philosophy

PromptChain is intentionally:
- small
- explicit
- boring (in a good way)

Agents should:
- prefer clarity over cleverness
- avoid premature abstractions
- resist “framework thinking”

---

## 10. Summary

AGENTS.md is a **safety rail**, not bureaucracy.

If you follow:
URD → PRD → Architecture → Plan → Checklist → Code

…you will not get lost.

If you skip them, you will.
