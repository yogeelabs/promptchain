

# PromptChain — Product Requirements Document (PRD)

## 1. Product Overview

PromptChain is a **local‑first workflow tool for multi‑step LLM thinking**, designed to let users express complex reasoning as a sequence of simple prompts.

It enables users to:
- run a single prompt or a sequential chain of prompts
- fan out work across lists (e.g., “for each persona…”)
- pause, inspect, and modify outputs between steps
- use different AI models at different steps
- keep final results cleanly separated from intermediate artifacts

PromptChain is **not** a chat application or an autonomous agent system.  
It is a **controlled execution environment for deliberate, inspectable thinking**.

---

## 2. Target Users

PromptChain is intended for:
- builders and developers
- product thinkers and strategists
- researchers and analysts
- power users working with local LLMs

These users:
- think in structured steps
- care about reproducibility and debuggability
- prefer clarity and control over hidden automation

---

## 3. User Problems (From URD)

PromptChain addresses the following core problems:

1. **Prompt sprawl** — single prompts become long, brittle, and unreadable.
2. **Loss of control** — users cannot easily pause, inspect, or redirect workflows.
3. **Fan‑out pain** — “for each item…” workflows are hard to manage reliably.
4. **Model mismatch** — the same model is not optimal for every task.
5. **Messy outputs** — final deliverables get buried among intermediate steps.
6. **Poor recovery** — failures require restarting entire workflows.

---

## 4. Product Goals

### Primary Goals
1. Enable **single, sequential, and fan‑out prompt chains**
2. Keep **prompt authoring simple and natural**
3. Allow **manual inspection and modification between steps**
4. Support **different models per step**
5. Make workflows **deterministic and resumable**
6. Separate **final outputs from intermediate artifacts**

### Non‑Goals
- Autonomous agents or planners
- Hidden decision‑making
- UI/dashboard (CLI‑first)
- Markdown → structured data syncing
- Cloud dependency by default
- External providers as a default requirement (optional extension in Phase 9)

---

## 5. Core Product Capabilities

### 5.1 Single & Sequential Prompt Chains

The product must allow users to:
- run a single prompt as a one‑off task
- define sequential chains where each step builds on previous outputs
- execute the full chain or individual steps independently

This enables workflows to scale from simple to complex without rewriting prompts.

---

### 5.2 Flexible Inputs Per Step

Each step in a workflow must support:
- simple input parameters (e.g., topic, goal, question)
- file‑based inputs (text or JSON)
- list‑based inputs that enable fan‑out execution

This allows steps to operate on:
- raw ideas
- existing text
- generated lists from earlier steps

Additional requirements:
- inputs can be provided per stage, not only globally
- a stage can mix parameters, file inputs, and upstream artifacts in the same step

---

### 5.3 Fan‑Out (“For Each…”) Execution

The product must support workflows where:
- one step generates a list
- the next step runs once per list item
- outputs are produced per item

Fan-out list sources can be:
- generated lists from earlier steps
- user-provided lists from JSON files
- user-provided lists from plain text files (one item per line)

This exists to preserve prompt simplicity while keeping workflows flexible.

Examples:
- personas → per‑persona JTBD
- ideas → per‑idea expansion
- documents → per‑section analysis

Fan‑out must feel **native**, not like a workaround.
List-based fan‑out must be deterministic, preserving stable ordering and stable identity for each item across runs.

### 5.3.1 Prompt Simplicity Guarantee

Prompts must remain simple and natural:
- users should not need to reference internal schema keys
- map steps should support a simple “item placeholder” conceptually
- prompt authors should not be forced into schema-heavy prompt patterns

---

### 5.4 Review & Process Between Steps

Users must be able to:
- stop after any step
- inspect outputs in plain files
- edit, prune, or refine outputs
- continue execution using the modified results

This ensures:
- human judgment remains in the loop
- early mistakes do not poison downstream steps

---

### 5.5 Per‑Step Model Selection

The product must allow:
- selecting different AI models for different steps
- mixing models within the same workflow

This enables:
- lightweight models for enumeration
- stronger models for synthesis
- specialized models for specific reasoning tasks

---

### 5.6 Deterministic & Resumable Execution

The product must ensure:
- workflows can be re‑run predictably
- users can resume from any completed step
- earlier successful outputs are never lost

Users should never need to “start over” unless they choose to.

---

### 5.7 Clear Output Organization

The product must clearly separate:
- **intermediate artifacts** (used for reasoning and control)
- **final outputs** (intended as deliverables)

Users should be able to:
- quickly locate final results
- archive or share outputs without extra cleanup

### 5.8 Optional External Provider Support

The product should allow users to opt in to external providers (OpenAI and OpenAI‑compatible) without changing the local‑first default.

This must ensure:
- external providers are explicitly chosen by the user
- provider and model are recorded for traceability
- workflows behave the same (single, sequential, fan‑out)
- prompt‑writing requirements remain unchanged

---

## 6. Execution Experience

### CLI‑First
- Users run workflows from the command line
- Inputs are passed explicitly
- Execution scope is user‑controlled (full run or partial)

### Transparency
- Every step produces visible files
- Nothing is hidden or implicit
- Users can always trace where an output came from

---

## 7. Failure & Recovery

When a failure occurs:
- the failing step is clearly identified
- raw outputs are preserved
- earlier steps remain intact
- the user can fix and resume

Failures must feel **recoverable**, not destructive.

---

## 8. MVP Scope

The MVP must include:
- single‑step execution
- sequential chains
- fan‑out over lists
- fan‑out from JSON or plain text list files
- per‑stage file inputs (text or JSON)
- per‑step model choice
- pause / inspect / resume
- final output separation
- local‑first workflows with Ollama as the default provider

The MVP must **not** include:
- reduce/merge steps
- autonomous decision logic
- UI
- document ingestion
- review automation
- external providers as a requirement for completion (Phase 9 is post‑MVP)

---

## 9. Success Criteria

From a user’s perspective, PromptChain is successful if:

- they can write workflows using plain English prompts
- complex reasoning is broken into manageable steps
- fan‑out workflows feel natural and reliable
- they can inspect and intervene at any point
- final outputs are easy to find and reuse

---

## 10. Summary

PromptChain is a **thinking‑first orchestration tool** that prioritizes:

- simplicity in prompt writing
- explicit structure in execution
- human control at every stage
- clean separation of process vs output

It exists to make advanced LLM workflows **usable, debuggable, and sane**.
