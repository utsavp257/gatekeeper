# Submission kit

## Cerebral Valley project description (paste this)

**Gatekeeper: a procurement agent whose guardrails evolve themselves** (Statement 1: Recursive Harnessing)

AI agents are starting to approve vendors, and they fail in two ways. They miss sanctioned companies hidden behind name variants and subsidiaries (OFAC's 50% rule), and they "de-risk" by nationality. Our baseline agent wrongly blocked about half of the legitimate vendors.

Gatekeeper keeps the model fixed and evolves the **harness** around it. The harness is a versioned policy "genome" stored in MongoDB Atlas. It controls:
- which tools the agent is granted
- which checks must run before approval
- fuzzy-match and ownership-graph depth
- evidence-bound reject and escalate rules
- injection antibodies

A deterministic Strands hook enforces the genome, so the model can't override it. A critic (Claude Sonnet 5) reads the agent's failures, recalls earlier attempts and what they broke through **Atlas Vector Search**, and proposes a structured policy diff. Candidates are evaluated against hidden labels and promoted only if held-out catch never drops. **Atlas change streams** hot-swap each new champion into every running agent in about 200 ms ("herd immunity").

The data is real: 16,610 US-listed parties from the Consolidated Screening List, served through **Atlas Search** (fuzzy), and the GLEIF ownership graph, walked with **`$graphLookup`**.

**Result (same model; held-out; 3 runs each):**
- **Catch:** 87% → **100%**
- **Legitimate vendors wrongly blocked:** 44% → **3.7%**
- **Injection catch:** 80% → **100%**
- **Cost:** about $0.02 per vendor check Everything runs in the Atlas Hackathon Sandbox.

Stack: MongoDB Atlas (Search, Vector Search, change streams, `$graphLookup`), Strands Agents, OpenRouter (Qwen3-235B agent, Claude Sonnet 5 critic), Voyage AI, Tavily, FastAPI, Next.js on Vercel.

## 1-minute demo script

| Time | Screen | Voiceover |
|---|---|---|
| 0–8s | Title + one example vendor | "AI agents approve vendors now. Sanctioned companies hide behind name variants and subsidiaries, and naive agents over-block whole countries." |
| 8–20s | Baseline `g-0001` screens **Renaissance Capital** (clean, Russian) → *reject*, then **an opaque subsidiary of a listed bank** → *approve* | "Our baseline, name screening only, gets both wrong: it blocks half the legitimate vendors and lets hidden subsidiaries through." |
| 20–38s | Dashboard version tree: g-0001 → rejected g-0002/g-0003 (grey) → g-0004 → g-0005, with the chart. Click g-0004 to show its diff. | "Same model, and the harness rewrites itself. The critic proposed ownership checks, fuzzy matching and evidence-bound rejects. The gate pruned two attempts that traded away a single catch. Held-out false blocks fell from 44% to about 4%, and catch reached 100%." |
| 38–52s | Live ops split screen: promote the champion, and the **hot_swap banner** shows agent-a 170 ms, agent-b 250 ms. Re-screen the subsidiary on agent-b → *reject*, blocked_by `policy.ownership.block_if_listed_ancestor_within`. | "Every improvement lives in MongoDB Atlas. A change stream pushes it to every running agent in about 200 milliseconds." |
| 52–60s | Architecture strip: Atlas Search · `$graphLookup` · Vector Search · change streams | "The model never changed. The harness did, and it's all in Atlas." |

**Recording tips:**
- Run the steps first, then record from saved data. The dashboard reads Atlas, so nothing live can break mid-take.
- Before the take, set agent-a to `g-0001` so the baseline beat is real. Promote the champion on camera, or replay a real `hot_swap` event.
- Keep API keys and the Atlas URI off screen.
