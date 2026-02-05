

# PromptChain — Architecture

This document describes the **system architecture** for PromptChain, derived from `docs/prd.md`.
It focuses on responsibilities, boundaries, and execution flow—without over-specifying implementation details.

---

## 1. Architectural Principles

PromptChain must prioritize:

1. **Simple prompt authoring**
   - Prompts are written in plain English.
   - Structure and control mechanics are handled by the system.

2. **Inspectability**
   - Every stage produces files a user can open and understand.
   - Users can pause, edit outputs, and continue.

3. **Deterministic control**
   - Fan-out (map) is driven by structured artifacts, not free-form text.

4. **Local-first**
   - Works with local model runtimes (starting with Ollama).
   - No cloud dependency by default.

5. **Separation of concerns**
   - Prompt reasoning, control flow, persistence, and model access are cleanly separated.

6. **Clean deliverables**
   - Final outputs are easy to find and separated from intermediate artifacts.

---

## 2. System Overview

At a high level, PromptChain consists of:

- **CLI**: user entrypoint (run pipeline, run stage, resume)
- **Pipeline Loader/Resolver**: reads pipeline definition and merges defaults/overrides
- **Runner**: orchestrates execution stage-by-stage and persists run state
- **Stage Executors**: implement stage behavior (single, map)
- **LLM Provider Layer**: calls the configured model per stage (local-first)
- **Artifact Store**: writes immutable run artifacts and logs
- **Output Publisher**: collects “final outputs” into a dedicated output location

The architecture is intentionally small and composable.

---

## 3. Execution Model

PromptChain executes a pipeline as a sequence of **stages**. The MVP supports:

### 3.1 Single Stage
- Runs once per stage.
- Produces one primary output artifact (JSON and/or Markdown).

### 3.2 Map Stage (Fan-out)
- Consumes a list artifact produced by an earlier stage.
- Runs once per list item (optionally filtered by user edits).
- Produces one output per item, organized under a stage folder.

Map stages must iterate over deterministic list sources, not free-form text prompts.
List-based fan-out preserves stable ordering and stable identity for each item across runs.

---

## 4. Inputs Model

Each stage may take input from:

1. **User parameters**
   - e.g., `topic`, `goal`, `question` passed at run time

2. **File inputs**
   - plain text or JSON files provided by the user
   - inputs can be bound per stage, not just globally

3. **Upstream artifacts**
   - outputs from earlier stages in the same run

4. **List inputs (for fan-out)**
   - a stage output that represents a list of items
   - a JSON list file provided by the user
   - a plain text file where each line is an item
   - the list is the iteration source for map stages

This supports the PRD requirement: “each step can take params, files, or lists.”

---

## 5. Prompt Construction Responsibilities

PromptChain must keep prompts simple while supporting chaining:

- **Prompt templates** may reference:
  - user params (e.g., topic)
  - upstream outputs
  - per-item content (for map stages)

The **Runner** (not the user) is responsible for:
- assembling context for each stage
- passing it to the model in a consistent way

The system must not force users to embed schemas or internal control details inside prompts.
Prompts should not need to understand the internal structure of list items to iterate over them.

---

## 6. Artifact Model & Directory Layout

PromptChain persists everything to disk for inspectability and resumability.

### 6.1 Run Snapshots (Immutable)
Each run creates a new directory:

`runs/<run_id>/`

It contains:
- run metadata (inputs, timestamps, pipeline reference)
- stage outputs (JSON/MD)
- per-item outputs for map stages
- logs including raw model responses

Runs are immutable snapshots: a new run is created for a new execution.

### 6.2 Final Output Directory (Deliverables)
To satisfy the PRD requirement (“final output under output directory separate from intermediate files”):

- Each run includes a dedicated **deliverables** location, separate from intermediate artifacts.
- Final outputs are **published** into:

`runs/<run_id>/output/`

Optionally (later), users may configure an external output directory, but MVP can treat the per-run output folder as the final deliverables location.

The key architectural rule:
- **intermediate artifacts live outside `output/`**
- **final deliverables are copied/collected into `output/`**

Supporting and debug artifacts are stored in run-internal folders:
- `runs/<run_id>/logs/` for raw outputs and error traces
- `runs/<run_id>/support/` for request/response summaries and context dumps

---

## 7. Stage Output Types

Stages may emit:
- **JSON**: structured outputs used for control and fan-out lists
- **Markdown**: human-readable outputs for review and sharing
- **Both**: JSON for control + Markdown for readability

A stage that emits JSON must produce a valid JSON artifact file.
If the model’s response cannot be used as valid JSON:
- the raw response must still be saved
- the stage must fail clearly and be recoverable by editing/re-running

---

## 8. Human-in-the-Loop Between Stages

To satisfy “ability to process output of any stage before next stage”:

The execution model must support:
- running only stage A
- user edits stage A output file(s)
- resuming execution from stage B

This requires:
- stage outputs to be stable, well-located files
- a “resume” behavior that reads the latest saved artifacts

The architecture assumes users may modify artifacts between steps.

---

## 9. Model Selection & Provider Layer

To satisfy “different models for each stage”:

- Each stage can specify which model to use.
- A pipeline can define defaults.
- The runner resolves the effective model configuration per stage.

The provider layer:
- abstracts model invocation
- supports local-first model runtimes (starting with Ollama)
- is structured so additional providers can be added later
- can be extended with external providers as an optional lane
- requires explicit configuration when using external providers

The runner must log which model was used per stage for traceability.

### 9.1 Reasoning Configuration

When supported by the chosen provider/model:
- the runner resolves per-stage reasoning configuration
- the provider receives it
- stage metadata records it for traceability

### 9.2 External Provider Lane (Optional)

PromptChain can be extended to use external providers (OpenAI or OpenAI‑compatible) without changing the default local‑first behavior.
External provider usage must be explicitly chosen and clearly logged per stage.
Failures should surface provider‑specific issues (auth, network, rate limits) in a user‑readable way.

---

## 10. Provider Policy

- The default provider is local.
- External providers are opt‑in only.
- No implicit fallback from local to cloud; users must choose.
- Behavior should be deterministic where possible, while acknowledging network variability.

---

## 11. Orchestration & Resumability

The Runner is responsible for:
- executing stages in order
- skipping stages that are already completed when resuming (based on existing artifacts)
- supporting partial execution modes:
  - run full pipeline
  - run a single stage
  - run from a stage onward

Resumability is achieved by:
- artifact persistence per stage
- clear stage completion markers in run metadata
- non-destructive failure handling

---

## 12. Failure Handling

Failures must be recoverable.

Architectural requirements:
- raw model outputs are always saved
- errors must identify the stage (and item, for map stages) that failed
- successful prior outputs remain intact
- map item failures are isolated (other items can still complete)

This supports the PRD requirement: “failure does not require starting over.”

---

## 13. Execution Modes: Interactive vs Batch

The system supports two execution modes:

### Interactive Mode
- Default execution path.
- Stages execute immediately.
- Outputs are written synchronously.

### Batch Mode
- Optional execution path for compatible workloads.
- Primarily applies to fan-out (map) stages processing large lists.
- The runner submits work to a provider capable of batch processing.
- Results are collected asynchronously and written to artifacts later.

### Responsibilities

**Runner**
- determines execution mode
- evaluates stage compatibility for batch
- submits and tracks batch jobs
- collects outputs
- writes artifacts in the standard structure

**Provider**
- accepts batch submissions
- processes asynchronously
- returns outputs for ingestion

### Product Contract
- Artifact structure must remain identical between modes.
- Only execution timing and cost behavior differ.
- Batch support must remain transparent via logs and metadata.

### Directory Policy
- Batch submission payloads, job ids, and status snapshots are stored under:
  - `runs/<run_id>/logs/` or `runs/<run_id>/support/`
- Final deliverables remain only under:
  - `runs/<run_id>/output/`

---

## 14. Minimal Extensibility Points (MVP-Safe)

PromptChain should be designed to grow without redesign:

- Add new stage types later (e.g., reduce) without changing the runner contract.
- Add new providers later without changing stage execution logic.
- Add output publishing strategies later without changing stage output format.

However, MVP should not implement features beyond the PRD MVP scope.

---

## 15. What This Architecture Explicitly Avoids

To keep the system aligned with the PRD and prevent complexity creep, the architecture avoids:

- autonomous agents or planners
- implicit mutation of prior artifacts
- hidden control logic inside prompts
- complex orchestration frameworks
- Markdown → structured data synchronization

---

## 16. Summary

This architecture implements PromptChain as a small, local-first execution engine where:

- users write plain-English prompts
- workflows can be single-step, sequential, or fan-out
- users can pause, edit outputs, and resume
- different models can be used per stage
- final deliverables are always easy to find in a dedicated output location

It is intentionally minimal so that complexity grows only when required.
