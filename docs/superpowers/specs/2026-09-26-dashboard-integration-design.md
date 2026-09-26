# Gatekeeper Dashboard Integration Design

## Purpose

Build the real Person B dashboard inside `/dashboard` and connect it to the
MongoDB Atlas collections and FastAPI endpoints defined in `HANDOFF.md`.
The dashboard is the visual proof that the harness—not the model—is changing:
it must make genome evolution, rejected mutations, deterministic blocks, and
change-stream hot-swaps understandable in a one-minute demo.

The existing v0 page is a visual reference only. It is not an implementation
and will not be copied into the repository as product code.

## Success criteria

- `npm run dev` in `/dashboard` starts a usable local dashboard.
- The evolution view reads real genome documents from Atlas and tolerates
  rejected genomes without held-out scores.
- The lineage view derives parent/child relationships from `genomes.parent`,
  excludes the `ref-all-tools` reference genome from the tree, and identifies
  the current champion.
- The live-ops view displays `agent-a` and `agent-b`, consumes the event stream,
  emphasizes blocks and antibody hits, and shows hot-swap latency.
- The screening form calls the FastAPI harness and renders the decision, memo,
  blocked actions, cost, and trace.
- Evolve, immune, and red-team actions call the current harness endpoints and
  expose queued/running, success, conflict, and failure states without holding
  a browser request open for a 5–15 minute harness step.
- Protected actions authenticate server-to-server with `HARNESS_API_TOKEN`;
  the token never reaches a browser response or bundle.
- Agent liveness is based on the 10-second `agents.last_heartbeat` updates.
- The application deploys to Vercel with secrets kept server-side.
- Tests cover contract normalization, missing data, state transitions, and the
  primary user flows. The Python suite remains green.

## Scope

### Included

1. `/` — **Immune System Command Center**
   - held-out metric chart by genome version
   - genome lineage tree
   - selected-genome detail panel with rationale, diff, gate reason, tool
     policy, and antibody count
   - dashed `ref-all-tools` benchmark, when it has comparable scores
2. `/ops` — **Herd Immunity Live Ops**
   - split panels for `agent-a` and `agent-b`
   - agent genome and heartbeat state
   - live event feed with distinct decision, blocked, antibody,
     antibody-hit, promotion/rejection, and hot-swap treatments
   - controls for red-team, immune, and evolution steps
3. `/screen` — **Procurement Mission Control**
   - vendor and purchase-request form
   - optional genome override for the before/after demo
   - decision, memo, blocked actions, cost, and trace-step rendering
4. Next.js server routes for Atlas reads, event streaming, and FastAPI proxying.
5. The newest `reports` document whose note starts with `FINAL`, used for the
   honest repeated-run mean/range summary.
6. Vercel configuration and dashboard-specific environment documentation.

### Excluded

- Changes to `/harness`, its collection contract, or evolution logic.
- Authentication and multi-tenant access control for this hackathon build.
- Editing genomes or Atlas documents from the browser.
- A general-purpose graph editor or analytics suite.
- Committing `.env*`, Atlas credentials, `.superpowers` state, or v0 runtime
  artifacts.

## Architecture

The dashboard is a standalone Next.js App Router application under
`/dashboard`, written in TypeScript. Browser components never receive
`MONGODB_URI` or the private harness base URL.

```text
Browser
  ├─ GET /api/dashboard      ──► Next.js server ──► MongoDB Atlas
  ├─ GET /api/events         ──► Next.js SSE route ──► Atlas change stream
  ├─ POST /api/harness/*     ──► Next.js proxy + token ──► FastAPI harness
  └─ GET /api/harness/jobs/* ──► Next.js proxy ──► FastAPI job status
```

The server data layer owns MongoDB connection reuse, query projections, BSON
serialization, and contract normalization. UI components consume dashboard
view models rather than raw MongoDB documents. This keeps optional or
historical fields from leaking defensive checks throughout the component tree.

The FastAPI proxy is configurable with `HARNESS_API_URL` and adds the
server-only `HARNESS_API_TOKEN` to protected POST requests. A local dashboard
can use `http://localhost:8000`; a Vercel deployment requires Utsav's current
network-reachable Cloudflare tunnel URL. Atlas-backed read-only views remain
usable when the harness is offline, while mutation controls clearly report
that live actions are unavailable.

## Server interfaces

### `GET /api/dashboard`

Returns the initial command-center snapshot:

```ts
type DashboardSnapshot = {
  generatedAt: string;
  genomes: GenomeSummary[];
  reference: GenomeSummary | null;
  finalReport: FinalReport | null;
  agents: AgentSummary[];
  recentEvents: GatekeeperEvent[];
};
```

The Atlas queries:

- read genomes ordered by `version`
- project out `embedding` and `critic_raw`
- separate `status: "reference"` from lineage genomes
- read both agent documents ordered by `_id`
- read the newest report where `note` starts with `FINAL`
- read the newest 100 events and return them oldest-to-newest for display

### `GET /api/traces/:id`

Returns one normalized trace with `steps`, `blocked`, `decision`, `memo`,
`costUsd`, `durationSeconds`, `model`, and error state. It returns 404 for an
unknown trace without exposing raw database errors.

### `GET /api/events`

Returns `text/event-stream`. The route opens an Atlas change stream on
`events`, emits normalized documents as `event: gatekeeper`, and sends periodic
comment heartbeats so intermediaries do not treat an idle stream as dead. The
client reconnects automatically and refreshes the snapshot after a disconnect,
so missed events do not leave the UI stale.

### Harness proxy routes

- `POST /api/harness/screen` → `POST /screen`
- `POST /api/harness/redteam` → `POST /redteam/attack`
- `POST /api/harness/evolve` → `POST /evolve/step`
- `POST /api/harness/immune` → `POST /immune/step`
- `GET /api/harness/jobs/:id` → `GET /jobs/:id`

The proxy preserves the harness status code, returns a small normalized error,
and applies an explicit timeout. Every protected POST includes
`x-harness-token` from the server environment. Evolve and immune return 202
with `{job_id, status: "running"}`; the browser polls the open job endpoint
until `done` or `error` while also watching promotion/rejection/hot-swap events.
A 409 is shown as “another harness step is already running,” not as a generic
crash.

## View models and contract handling

`GenomeSummary` contains the fields the UI actually uses:

```ts
type MetricSet = {
  catchRate: number | null;
  falseBlockRate: number | null;
  injectionBlockRate: number | null;
  costPerCaseUsd: number | null;
};

type MetricRange = { mean: number; min: number; max: number };

type FinalReport = {
  createdAt: string;
  note: string;
  runs: number;
  rows: Record<string, {
    catchRate: MetricRange | null;
    falseBlockRate: MetricRange | null;
    injectionCatch: MetricRange | null;
    costPerCaseUsd: MetricRange | null;
    n: number;
  }>;
};

type GenomeSummary = {
  id: string;
  version: number;
  parentId: string | null;
  status: "candidate" | "champion" | "rejected" | "retired" | "reference";
  origin: string | null;
  rationale: string;
  diff: GenomeDiff[];
  gateReason: string | null;
  train: MetricSet | null;
  heldout: MetricSet | null;
  allowedTools: string[];
  maxWebCalls: number | null;
  antibodyCount: number;
};
```

Rules:

- Missing `scores.heldout` produces gaps, never zeroes.
- Unknown event types use a neutral treatment and remain visible.
- Missing parents create an orphan root instead of crashing the tree.
- Dates become ISO strings at the server boundary.
- Arbitrary payload text is rendered as text, never injected as HTML.
- The UI never reads `case_labels`.
- The final report parser tolerates absent metric ranges and unknown genome ids.

## Page design

The visual language is a dense operations console, not a marketing landing
page: near-black/navy surfaces, restrained borders, high-contrast typography,
and semantic green, amber, red, and cyan. No ornamental gradients, oversized
hero copy, stock card grid, or excessive rounding.

### Shared shell

- compact top navigation: Command Center, Live Ops, Screen Vendor
- Atlas connection indicator based on the snapshot request
- harness availability indicator based on the proxy health check
- current champion badge
- responsive navigation and keyboard-visible focus states

### Command Center

The metric chart and lineage tree share the main canvas. Selecting a genome in
either view synchronizes the other and updates a detail rail. The chart plots
only held-out catch, false-block, and injection-block rates; rejected genomes
without held-out data remain present in the lineage but do not fabricate chart
points. The reference genome appears only as a dashed comparison series.

### Live Ops

Two equal agent panels create the herd-immunity split screen. Each panel shows
its current genome, heartbeat freshness derived from `last_heartbeat`, latest
decision, blocks, and antibody hits. A hot-swap event creates a prominent but
non-blocking banner containing the old genome, new genome, and latency. Global
promotion, rejection, and antibody events appear in a shared center timeline
rather than being assigned to an agent that did not produce them.

Controls are intentionally narrow: choose an agent and attack family, launch a
red-team attack, or run one immune/evolution step. Each control disables only
while its own request is active, reports the returned job identifier, and polls
job status without blocking the event feed.

### Screen Vendor

The form captures name, country, optional LEI and website, PO amount,
justification, agent instance, and optional genome override. The result leads
with the decision, then memo and cited evidence, followed by blocked actions
and an expandable trace. The default state contains demo-ready example values
but does not submit automatically.

## Loading, empty, and failure states

- Initial pages use stable skeletons that preserve layout.
- An empty genome collection explains how to run the seed/evaluation commands.
- Missing agents show an offline panel rather than removing half of Live Ops.
- An SSE disconnect marks the feed “reconnecting,” retains existing events,
  and refreshes the snapshot on reconnection.
- Atlas read failures show a retry action and no fabricated sample metrics.
- Harness failures preserve entered form data and show the backend message when
  safe to do so.

## Accessibility and responsiveness

- All navigation, controls, lineage nodes, and detail disclosures are keyboard
  reachable.
- Color is never the sole status signal; labels and icons accompany it.
- Charts include a tabular accessible summary.
- Motion respects `prefers-reduced-motion`.
- Desktop is optimized for the recorded demo. Below 900 px, split panels stack
  and the genome detail rail moves below the chart/tree.

## Security

- `MONGODB_URI`, `HARNESS_API_URL`, and `HARNESS_API_TOKEN` are server-only variables.
- `HARNESS_API_TOKEN` is attached only to protected harness POST requests.
- Atlas reads use explicit projections and limits.
- No API route exposes `case_labels`, embeddings, or raw critic output.
- User and event text is escaped by React and is never passed to
  `dangerouslySetInnerHTML`.
- Harness proxy paths are an allowlist; callers cannot supply arbitrary URLs.
- `.env.local`, `.next`, coverage, and `node_modules` are ignored.

This is a hackathon dashboard with no login. The Vercel URL should therefore
be treated as a demo surface, and Atlas credentials should use the narrowest
available database permissions.

## Testing and verification

Automated tests will cover:

- normalization of real, partial, and malformed-optional MongoDB documents
- missing held-out scores and the separate reference genome
- lineage construction, including rejected branches and orphan parents
- event classification and agent/global routing
- screen form validation, request shape, loading state, and preserved errors
- action controls, including 409 conflict handling
- route projections, serialization, and proxy error normalization
- accessible labels and tabular metric fallback

Verification before review:

1. Run dashboard unit/component tests, lint, typecheck, and production build.
2. Run the repository’s complete Python test suite.
3. Run the dashboard against Atlas and the local FastAPI server.
4. Browser-check desktop and narrow layouts plus SSE reconnection.
5. Confirm no secret or `.env` value appears in the Git diff or client bundle.

## Deployment and handoff

The Vercel project root is `/dashboard`. Required variables are:

- `MONGODB_URI`
- `MONGODB_DB=gatekeeper` (optional when using the default)
- `HARNESS_API_URL`
- `HARNESS_API_TOKEN`

The deployment must complete even when `HARNESS_API_URL` points to an offline
backend; only live actions are unavailable. Utsav can run the harness locally
for development and replace the URL with his current Cloudflare tunnel for the
shared Vercel demo. Restarting the quick tunnel requires updating
`HARNESS_API_URL` in Vercel.

The PR description will identify the collection fields and harness endpoints
consumed so Person A can review the integration boundary quickly.
