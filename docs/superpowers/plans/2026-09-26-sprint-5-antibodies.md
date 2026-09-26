# Sprint 5 — Injection Attacks + Antibodies Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add prompt-injection attack cases and a harness "immune system":
1. A successful injection on train is turned into an **antibody**: an embedded signature plus an action.
2. The antibody is stored in the genome.
3. The enforcer applies it deterministically to all untrusted text, meaning the request justification and web content.
4. The antibody is gated on held-out attacks that are **reworded**.

**Architecture:**
- `harness/antibodies.py` (pure plus a Voyage embed cache) handles chunking, cosine scanning and neutralizing.
- The agent runner scans the request text before the model sees it. `web_research` and the new `fetch_website` tool scan web content.
- Any hit is recorded in `CaseState.injection_hits`, and the enforcer blocks `approve_vendor` (`blocked_by: policy.antibodies.<id>`). An antibody hit also counts as evidence for escalation.
- `harness/immune.py` mints antibodies from the champion's failed train injection cases and gates them like any other candidate genome.

**Where injection bites (from live data):** once the harness requires ownership and screening, hard blocks catch vendors with real evidence no matter what the model is persuaded of. Injection succeeds where the policy relies on the model's judgment: name variants whose similarity is below `screening.min_score`. So injection cases are built from **name-variant vendors**.

**Spec:** HANDOFF §5 (antibodies), §6 (`injection_block_rate`, `events.antibody`), §10 (herd-immunity demo)

## Global Constraints
- Train and held-out use **different payload families** and wording. Held-out payloads are never shown to the immune step.
- Injection cases reuse the group (listed party) of their source name-variant case, and stay in that case's split.
- Embeddings use `voyage-3.5-lite`, `input_type="document"`, cached in the Atlas collection `embed_cache` by text hash.
- An antibody is `{id, kind: "injection", signature_text, embedding, similarity_threshold, action: "escalate", source_case, stats}`.

## Review Focus
- Benign justifications ("Raw materials supplier for Q4 production") must **not** trigger antibodies, so the false-block rate stays flat. The test uses real embeddings, via a cosine fixture.
- A genome with no antibodies → the scan costs nothing and makes no embedding call.
- An antibody hit on a clean vendor → escalation is allowed (the hit counts as evidence), and it's counted as a false block in metrics. That's the honest cost.

## Tasks
1. `harness/antibodies.py`: `chunks(text)`, `cosine(a,b)`, `scan(text, antibodies, embed) -> hits`, `neutralize(text, hits)`, and `embed_cached(db, texts)`. Pure tests with a fake embedder.
2. Enforcer: add `CaseState.injection_hits`. `decide()` blocks approve on any hit and treats hits as evidence. Tests.
3. Runner and tools: scan the justification before prompting, and scan in `web_research`/`fetch_website`. `fetch_website(url)` uses Tavily extract, the sanitize rules, the antibody scan and the web cache.
4. Injection cases: `build_injection_cases(db)` appends train families `compliance_preapproval` and `exec_urgency`, and held-out families `legal_cleared` and `system_whitelist`, drawn from name-variant vendors in each split. The expected outcome is `reject`.
5. `harness/immune.py`: from the champion's latest train run, take the failed injection cases, extract the injected sentence (the justification chunk least similar to the benign templates), and create a candidate genome with the new antibodies. Evaluate and gate it with `evolve.gate`, then promote or reject, and emit an `antibody` event.
6. Live: evaluate the champion on the new injection cases, then run the immune step, and report `injection_block_rate` before and after, on train and on held-out.
