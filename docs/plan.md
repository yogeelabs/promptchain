

# PromptChain — Execution Plan

This plan translates the **PRD and Architecture** into clear, trackable milestones.
Each milestone is scoped to produce a **working, testable capability**, not abstractions.

The guiding rule:
> Every milestone must end with something the user can actually run.

---

## Phase -1 — Repo Setup (Git, Tooling, and Agent Guardrails)

**Goal:** Establish repo hygiene and a reproducible development workflow.

### Tasks
- [ ] Initialize git repo (if not already) and create initial commit
- [ ] Add `.gitignore` with at least: `runs/`, `.venv/`, `__pycache__/`, `.env`, etc.
- [ ] Add a `README.md` with quickstart commands
- [ ] Ensure `AGENTS.md` includes:
  - [ ] Exact commands to run (format/lint/tests/smoke)
  - [ ] Definition of done
  - [ ] Guardrails (no overbuild; follow docs)
- [ ] Add `scripts/` with a placeholder smoke script (`zsh`) that prints intended checks
- [ ] Choose and document Python environment approach (`venv`) and a single install command

### Exit Criteria
- [ ] Clean repo status (`git status` shows no changes)
- [ ] Can create a venv, install dependencies, and run the smoke script (even if it’s a placeholder)
- [ ] Agents have a repeatable set of commands to verify changes

---

## Phase 0 — Foundation & Guardrails

**Goal:** Lock scope, prevent over-engineering, and set execution constraints.

### Objectives
- Ensure everyone understands what PromptChain *is* and *is not*
- Freeze MVP scope before writing code

### Tasks
- [ ] Finalize `URD.md`
- [ ] Finalize `PRD.md`
- [ ] Finalize `architecture.md`
- [ ] Agree on MVP non-goals (no reduce, no review, no PDF, no UI)

### Exit Criteria
- All three documents are aligned
- No unresolved scope questions
- Ready to code without design ambiguity

---

## Phase 1 — Minimal Engine Skeleton (Single Prompt)

**Goal:** Run one prompt locally and save outputs in a structured, inspectable way.

### Capabilities Delivered
- CLI can run a pipeline with a single stage
- Local Ollama model invocation
- Outputs written to a new run directory

### Sub‑Goals / Tasks
- [ ] Project skeleton (CLI, runner, folders)
- [ ] Basic pipeline loader (YAML → in-memory)
- [ ] Ollama provider (single model)
- [ ] Single-stage execution
- [ ] Run directory creation (`runs/<run_id>/`)
- [ ] Save raw model output
- [ ] Save processed output (JSON or Markdown)

### Exit Criteria
- User can run:
  ```sh
  promptchain run --pipeline single.yaml --topic chess
  ```
- Output files are created and readable
- No fan-out yet

---

## Phase 2 — Sequential Chains (Multi-Step)

**Goal:** Allow multiple stages to run in order, passing context forward.

### Capabilities Delivered
- Sequential execution of stages
- Each stage can depend on previous outputs
- User can stop after any stage

### Sub‑Goals / Tasks
- [ ] Stage dependency resolution
- [ ] Context assembly for downstream stages
- [ ] Run full chain vs single stage
- [ ] Persist per-stage completion markers
- [ ] Resume from a given stage

### Exit Criteria
- User can run a 3-step chain
- User can stop after step 1, inspect output, then resume
- Earlier outputs are reused, not recomputed

---

## Phase 3 — JSON Output + Normalization (Control Plane)

**Goal:** Support structured outputs without forcing JSON-heavy prompts.

### Capabilities Delivered
- JSON-emitting stages
- Deterministic normalization of JSON artifacts
- Stable list outputs usable for fan-out

### Sub‑Goals / Tasks
- [ ] JSON-only stage mode
- [ ] Parse model JSON output
- [ ] Normalize into canonical `{ items: [...] }`
- [ ] Auto-generate stable item ids
- [ ] Default `_selected = true`
- [ ] Clear failure when JSON is invalid (raw output preserved)

### Exit Criteria
- A stage can output a valid list artifact
- User does not write schemas in prompts
- Artifacts are safe for downstream control

---

## Phase 4 — Fan-Out (Map Stages)

**Goal:** Enable “for each item…” workflows.

### Capabilities Delivered
- Map stage execution
- One output per list item
- Isolated failures per item

### Sub‑Goals / Tasks
- [ ] Map stage definition
- [ ] List consumption from upstream JSON artifact
- [ ] Per-item prompt rendering
- [ ] Per-item output directories
- [ ] Skip unselected items
- [ ] Resume partially completed fan-outs

### Exit Criteria
- Personas → per-persona JTBD works
- Outputs are clearly organized per item
- One failing item does not kill the entire run

---

## Phase 5 — Human-in-the-Loop Editing & Resume

**Goal:** Let users intervene between stages without hacks.

### Capabilities Delivered
- User edits outputs manually
- Engine respects edited artifacts
- Clean resume semantics

### Sub‑Goals / Tasks
- [ ] No overwriting of existing artifacts on resume
- [ ] Clear detection of completed stages/items
- [ ] Resume-from-stage CLI support
- [ ] Document user editing workflow

### Exit Criteria
- User can prune/edit a list before fan-out
- Downstream stages reflect user edits
- No forced recomputation

---

## Phase 6 — Per-Stage Model Selection

**Goal:** Allow different models per stage.

### Capabilities Delivered
- Stage-level model configuration
- Defaults at pipeline level
- Full traceability of model usage

### Sub‑Goals / Tasks
- [ ] Pipeline-level model defaults
- [ ] Stage-level overrides
- [ ] Model metadata saved per stage
- [ ] Clear CLI errors if model unavailable

### Exit Criteria
- One pipeline uses multiple models successfully
- Model used per stage is visible in artifacts

---

## Phase 7 — Final Output Publishing

**Goal:** Separate deliverables from intermediate reasoning artifacts.

### Capabilities Delivered
- Dedicated output directory per run
- Explicit final-output marking or publishing
- Clean handoff for sharing or archiving

### Sub‑Goals / Tasks
- [ ] Define what counts as “final output”
- [ ] Copy/publish selected artifacts to `runs/<run_id>/output/`
- [ ] Prevent intermediate clutter in output directory

### Exit Criteria
- User opens `output/` and finds only final results
- Intermediate files remain intact elsewhere

---

## Phase 8 — Hardening & Usability Polish

**Goal:** Make the MVP reliable and pleasant to use.

### Capabilities Delivered
- Clear error messages
- Smoke tests
- Basic documentation

### Sub‑Goals / Tasks
- [ ] Failure isolation for map items
- [ ] Smoke scripts for core workflows
- [ ] README with examples
- [ ] Minimal logging improvements

### Exit Criteria
- New user can run a sample pipeline end-to-end
- Errors are understandable and actionable

---

## Phase 9 — External Providers (Optional): OpenAI + OpenAI-Compatible

**Goal:** Enable optional use of external providers without affecting existing local-first workflows.

### Capabilities Delivered
- Support OpenAI provider
- Support OpenAI-compatible provider (LM Studio / vLLM / other compatible servers)
- Provider choice per stage remains consistent with Phase 6 (per-stage model selection)
- Traceability and clear failure messages for external calls

### Sub‑Goals / Tasks
- [ ] Document provider configuration expectations (high level; env vars ok)
- [ ] Add explicit “opt-in external provider” guidance to README (optional addendum)
- [ ] Ensure plan includes “no cloud required” as an invariant
- [ ] Add conceptual acceptance tests (smoke scripts) for external providers

### Exit Criteria
- Docs clearly state external providers are optional
- Acceptance criteria are unambiguous:
  - can run a pipeline using an external provider
  - can mix providers across stages
  - logs show provider/model used
  - failures are explainable and recoverable
- No changes to MVP scope or earlier phase definitions

---

## Summary Roadmap

| Phase | Focus |
|------|------|
| 0 | Scope & docs |
| 1 | Single prompt |
| 2 | Sequential chains |
| 3 | JSON control |
| 4 | Fan-out |
| 5 | Human-in-loop |
| 6 | Multi-model |
| 7 | Output separation |
| 8 | Hardening |
| 9 | Optional external providers |

---

## Definition of Success

PromptChain is “ready” when:
- workflows scale from 1 prompt to many without prompt explosion
- users can stop, inspect, edit, and resume confidently
- fan-out feels native and predictable
- final outputs are clean and reusable
