# Gatekeeper Dashboard Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a Vercel-ready Next.js dashboard that visualizes Atlas-backed genome evolution and live herd immunity, and safely proxies demo actions to the FastAPI harness.

**Architecture:** A TypeScript Next.js App Router application lives in `/dashboard`. Server-only modules read MongoDB Atlas and proxy an allowlisted set of FastAPI endpoints; client components receive normalized view models, with an SSE route translating the Atlas `events` change stream into live UI updates.

**Tech Stack:** Node 25, npm, Next.js App Router, React, TypeScript, MongoDB Node driver, native SVG/CSS charts, Vitest, jsdom, Testing Library, ESLint, Vercel.

**Spec:** `docs/superpowers/specs/2026-09-26-dashboard-integration-design.md`

## Global Constraints

- Keep all dashboard product code inside `/dashboard`; do not modify `/harness` or its MongoDB contract.
- Keep `MONGODB_URI` and `HARNESS_API_URL` server-only and never commit `.env*` files other than examples.
- Never expose `case_labels`, genome embeddings, or `critic_raw` through a dashboard route.
- Use real Atlas data and honest empty/error states; do not ship fabricated demo metrics.
- Treat missing `scores.heldout` as missing data, not zero.
- Keep `ref-all-tools` out of the lineage tree and render it only as a dashed benchmark when comparable scores exist.
- Render external strings as text; do not use `dangerouslySetInnerHTML`.
- Optimize the recorded desktop demo while remaining keyboard accessible and stacking layouts below 900 px.
- Use the approved dense navy operations-console direction with restrained borders and semantic green, amber, red, and cyan; no ornamental gradients or generic marketing hero.
- Each task follows RED → GREEN → REFACTOR and ends in one atomic commit without `Co-Authored-By` trailers.

## Review Focus

1. A rejected genome with train scores but no held-out scores stays in lineage and creates no fake chart point — pinned in Tasks 1 and 3.
2. Missing or unknown parents produce a stable orphan root instead of breaking lineage — pinned in Task 3.
3. Replayed or duplicate SSE events do not duplicate the visible feed, and reconnect state never discards prior events — pinned in Task 4.
4. A slow/offline harness or a 409 step conflict preserves user input and produces a useful message — pinned in Tasks 5 and 6.
5. Injection payloads containing HTML-like text render literally and cannot become DOM markup — pinned in Tasks 4 and 6.

## File map

```text
dashboard/
  app/
    api/dashboard/route.ts           initial Atlas snapshot
    api/events/route.ts              Atlas change-stream SSE
    api/harness/[action]/route.ts    allowlisted FastAPI proxy
    api/traces/[id]/route.ts         one normalized trace
    ops/page.tsx                     herd-immunity screen
    screen/page.tsx                  vendor-screening screen
    globals.css                      design tokens and responsive layout
    loading.tsx                      stable route skeleton
    layout.tsx                       shared shell
    page.tsx                         command center
  components/
    app-shell.tsx
    command-center.tsx
    genome-detail.tsx
    lineage-tree.tsx
    metric-chart.tsx
    metric-table.tsx
    ops-console.tsx
    event-card.tsx
    harness-controls.tsx
    screen-form.tsx
    screen-result.tsx
    trace-view.tsx
  lib/
    contracts.ts                     browser-safe view models
    normalize.ts                     MongoDB document → view model
    lineage.ts                       pure tree layout
    event-feed.ts                    pure event routing/deduplication
    mongodb.ts                       cached server-only Mongo client
    dashboard-data.ts                projected Atlas reads
    harness.ts                       allowlisted backend forwarding
  test/
    setup.ts
    fixtures.ts
  .env.example
  eslint.config.mjs
  next.config.ts
  package.json
  tsconfig.json
  vitest.config.ts
  vercel.json
```

---

### Task 1: Dashboard foundation and contract normalization

**Files:**
- Create: `dashboard/package.json`
- Create: `dashboard/package-lock.json`
- Create: `dashboard/tsconfig.json`
- Create: `dashboard/next.config.ts`
- Create: `dashboard/eslint.config.mjs`
- Create: `dashboard/vitest.config.ts`
- Create: `dashboard/test/setup.ts`
- Create: `dashboard/test/fixtures.ts`
- Create: `dashboard/lib/contracts.ts`
- Create: `dashboard/lib/normalize.ts`
- Test: `dashboard/lib/normalize.test.ts`

**Interfaces:**
- Consumes: MongoDB documents shaped by `HANDOFF.md` §6.
- Produces: `MetricSet`, `GenomeSummary`, `AgentSummary`, `GatekeeperEvent`, `TraceView`, `DashboardSnapshot`, `normalizeGenome`, `normalizeAgent`, `normalizeEvent`, and `normalizeTrace`.

- [ ] **Step 1: Create the Node/test configuration**

Run from the repository root:

```bash
mkdir -p dashboard
cd dashboard
npm init -y
npm install next react react-dom mongodb
npm install --save-dev typescript @types/node @types/react @types/react-dom eslint eslint-config-next vitest jsdom @testing-library/react @testing-library/jest-dom @testing-library/user-event
```

Set package scripts to these exact commands and keep the generated dependency versions plus lockfile:

```json
{
  "scripts": {
    "dev": "next dev",
    "build": "next build",
    "start": "next start",
    "lint": "eslint .",
    "typecheck": "tsc --noEmit",
    "test": "vitest run",
    "test:watch": "vitest"
  }
}
```

Create `tsconfig.json` with strict checking and the dashboard-root alias:

```json
{
  "compilerOptions": {
    "target": "ES2017",
    "lib": ["dom", "dom.iterable", "esnext"],
    "allowJs": false,
    "skipLibCheck": true,
    "strict": true,
    "noEmit": true,
    "esModuleInterop": true,
    "module": "esnext",
    "moduleResolution": "bundler",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "jsx": "react-jsx",
    "incremental": true,
    "plugins": [{ "name": "next" }],
    "paths": { "@/*": ["./*"] },
    "types": ["vitest/globals"]
  },
  "include": ["next-env.d.ts", "**/*.ts", "**/*.tsx", ".next/types/**/*.ts"],
  "exclude": ["node_modules"]
}
```

Use these minimal configuration files:

```ts
// next.config.ts
import type { NextConfig } from "next";
const nextConfig: NextConfig = {};
export default nextConfig;

// vitest.config.ts
import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";
export default defineConfig({
  resolve: { alias: { "@": fileURLToPath(new URL(".", import.meta.url)) } },
  test: { environment: "jsdom", globals: true, setupFiles: ["./test/setup.ts"] },
});
```

Create `eslint.config.mjs` as:

```js
import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTypescript from "eslint-config-next/typescript";

export default defineConfig([
  ...nextVitals,
  ...nextTypescript,
  globalIgnores([".next/**", "coverage/**"]),
]);
```

Import `@testing-library/jest-dom/vitest` in `test/setup.ts`.

- [ ] **Step 2: Write the failing normalizer tests**

Create contract-shaped fixtures and assert these behaviors:

```ts
it("preserves a rejected genome without inventing held-out scores", () => {
  const result = normalizeGenome({
    _id: "g-0002", version: 2, parent: "g-0001", status: "rejected",
    rationale: "catch dropped", diff: [], scores: { train: { catch_rate: 0.8 } },
    policy: { tools: { allow: ["screen_name"], max_web_calls: 1 }, antibodies: [] },
  });
  expect(result.heldout).toBeNull();
  expect(result.train?.catchRate).toBe(0.8);
});

it("normalizes an unknown event without dropping its payload", () => {
  const result = normalizeEvent({
    _id: "evt-1", ts: new Date("2026-09-26T18:00:00Z"), type: "future_event",
    agent_instance: null, genome_id: "g-0004", payload: { note: "kept" },
  });
  expect(result.type).toBe("future_event");
  expect(result.payload).toEqual({ note: "kept" });
});
```

Also cover ISO date serialization, absent optional policy fields, antibody
counts, trace step/blocked arrays, and a BSON-like `_id` whose `toString()`
returns an identifier.

- [ ] **Step 3: Run the tests and verify RED**

Run: `cd dashboard && npm test -- lib/normalize.test.ts`

Expected: FAIL because `@/lib/normalize` and contract exports do not exist.

- [ ] **Step 4: Implement the browser-safe contracts and normalizers**

Use nullable metrics and string-keyed payloads:

```ts
export type MetricSet = {
  catchRate: number | null;
  falseBlockRate: number | null;
  injectionBlockRate: number | null;
  costPerCaseUsd: number | null;
};

export type GenomeStatus = "candidate" | "champion" | "rejected" | "retired" | "reference";

export type GenomeSummary = {
  id: string; version: number; parentId: string | null; status: GenomeStatus;
  origin: string | null; rationale: string; diff: Array<Record<string, unknown>>;
  gateReason: string | null; train: MetricSet | null; heldout: MetricSet | null;
  allowedTools: string[]; maxWebCalls: number | null; antibodyCount: number;
};
```

Implement `normalizeMetricSet(value: unknown): MetricSet | null` so a missing
object returns `null`, while missing individual numbers become `null`.
`normalizeGenome` must default display strings/arrays safely without rejecting
historical documents. Define matching explicit types for agents, events,
traces, and snapshots in the same file.

- [ ] **Step 5: Run checks and commit**

Run:

```bash
cd dashboard
npm test -- lib/normalize.test.ts
npm run typecheck
npm run lint
git add dashboard
git commit -m "feat(dashboard): define Atlas view-model contract"
```

Expected: all commands pass.

---

### Task 2: Atlas snapshot and trace routes

**Files:**
- Create: `dashboard/lib/mongodb.ts`
- Create: `dashboard/lib/dashboard-data.ts`
- Create: `dashboard/lib/dashboard-data.test.ts`
- Create: `dashboard/app/api/dashboard/route.ts`
- Create: `dashboard/app/api/traces/[id]/route.ts`
- Test: `dashboard/app/api/dashboard/route.test.ts`

**Interfaces:**
- Consumes: Task 1 normalizers and `MONGODB_URI`/optional `MONGODB_DB`.
- Produces: `getDb(): Promise<Db>`, `loadDashboardSnapshot(db?: Db): Promise<DashboardSnapshot>`, `loadTrace(id: string, db?: Db): Promise<TraceView | null>`, `GET /api/dashboard`, and `GET /api/traces/:id`.

- [ ] **Step 1: Write failing data-layer tests**

Use a small fake collection adapter only at the MongoDB boundary. Assert:

```ts
it("separates the reference genome and orders recent events oldest first", async () => {
  const snapshot = await loadDashboardSnapshot(fakeDb({
    genomes: [referenceGenome, championGenome, rejectedGenome],
    agents: [agentB, agentA],
    events: [newerEvent, olderEvent],
  }));
  expect(snapshot.reference?.id).toBe("ref-all-tools");
  expect(snapshot.genomes.map((genome) => genome.id)).toEqual(["g-0002", "g-0004"]);
  expect(snapshot.agents.map((agent) => agent.id)).toEqual(["agent-a", "agent-b"]);
  expect(snapshot.recentEvents.map((event) => event.id)).toEqual(["evt-old", "evt-new"]);
});

it("returns null for an unknown trace", async () => {
  await expect(loadTrace("missing", fakeDb({ traces: [] }))).resolves.toBeNull();
});
```

Assert exported `GENOME_PROJECTION` explicitly sets `embedding: 0` and
`critic_raw: 0`, and no data-layer code reads `case_labels`.

- [ ] **Step 2: Run the tests and verify RED**

Run: `cd dashboard && npm test -- lib/dashboard-data.test.ts`

Expected: FAIL because the data layer is absent.

- [ ] **Step 3: Implement connection reuse and projected reads**

`mongodb.ts` must throw `MONGODB_URI is not configured` before creating a
client. Cache the connection promise on `globalThis` during development and
select `process.env.MONGODB_DB || "gatekeeper"`.

In `dashboard-data.ts`, implement:

```ts
export const GENOME_PROJECTION = { embedding: 0, critic_raw: 0 } as const;

export async function loadDashboardSnapshot(db?: Db): Promise<DashboardSnapshot>;
export async function loadTrace(id: string, db?: Db): Promise<TraceView | null>;
```

Read genomes sorted by version ascending, agents by `_id` ascending, and the
latest 100 events by `ts` descending; reverse only the events after
normalization. Split the reference from lineage genomes after normalization.

- [ ] **Step 4: Write failing route tests**

Mock only `loadDashboardSnapshot`/`loadTrace`, then call route handlers and
assert status/body. Cover a successful snapshot, a 503 JSON response for an
Atlas error, a successful trace, and an unknown trace returning 404.

- [ ] **Step 5: Run route tests and verify RED**

Run: `cd dashboard && npm test -- app/api/dashboard/route.test.ts`

Expected: FAIL because the route handlers do not exist.

- [ ] **Step 6: Implement routes and verify GREEN**

Return `NextResponse.json(snapshot, { headers: { "Cache-Control": "no-store" } })`.
On errors, log the server-side error and return only
`{ error: "Atlas data is unavailable" }` with 503. The trace route validates a
non-empty id and returns `{ error: "Trace not found" }` with 404.

Run:

```bash
cd dashboard
npm test -- lib/dashboard-data.test.ts app/api/dashboard/route.test.ts
npm run typecheck
git add dashboard
git commit -m "feat(dashboard): expose projected Atlas snapshots"
```

---

### Task 3: Command Center evolution view

**Files:**
- Create: `dashboard/lib/lineage.ts`
- Create: `dashboard/lib/lineage.test.ts`
- Create: `dashboard/components/metric-chart.tsx`
- Create: `dashboard/components/metric-table.tsx`
- Create: `dashboard/components/lineage-tree.tsx`
- Create: `dashboard/components/genome-detail.tsx`
- Create: `dashboard/components/command-center.tsx`
- Create: `dashboard/components/command-center.test.tsx`
- Create: `dashboard/app/page.tsx`

**Interfaces:**
- Consumes: `GenomeSummary`, `DashboardSnapshot`, and `loadDashboardSnapshot`.
- Produces: `buildLineage(genomes: GenomeSummary[]): LineageLayout`, `CommandCenter({ snapshot })`, and the `/` page.

- [ ] **Step 1: Write failing lineage tests**

Assert a deterministic column per version and explicit roots:

```ts
it("keeps rejected branches and converts a missing parent into an orphan root", () => {
  const layout = buildLineage([root, rejectedChild, { ...champion, parentId: "missing" }]);
  expect(layout.nodes.map((node) => [node.id, node.kind])).toEqual([
    ["g-0001", "root"], ["g-0002", "branch"], ["g-0004", "orphan"],
  ]);
  expect(layout.edges).toEqual([{ from: "g-0001", to: "g-0002" }]);
});
```

Cover empty input, shuffled input, and duplicate version values without using
array position as identity.

- [ ] **Step 2: Run the lineage tests and verify RED**

Run: `cd dashboard && npm test -- lib/lineage.test.ts`

Expected: FAIL because `buildLineage` does not exist.

- [ ] **Step 3: Implement the pure lineage layout**

Return:

```ts
type LineageLayout = {
  nodes: Array<{ id: string; genome: GenomeSummary; column: number; row: number; kind: "root" | "branch" | "orphan" }>;
  edges: Array<{ from: string; to: string }>;
};
```

Sort by version then id. Place roots/orphans in their own row and children in
the next available row below their parent column. Keep rejected nodes rather
than filtering by score availability.

- [ ] **Step 4: Write failing Command Center component tests**

Render real components with fixtures and assert:

```ts
expect(screen.getByRole("heading", { name: /immune system command center/i })).toBeVisible();
expect(screen.getByRole("button", { name: /g-0002 rejected/i })).toBeVisible();
expect(screen.getByText(/held-out score unavailable/i)).toBeVisible();
expect(screen.getByRole("table", { name: /held-out metric values/i })).toBeVisible();
```

Click `g-0002` and assert its rationale/diff replace the selected detail. Assert
the reference appears in chart/table copy but has no lineage-node button.

- [ ] **Step 5: Run component tests and verify RED**

Run: `cd dashboard && npm test -- components/command-center.test.tsx`

Expected: FAIL because the components do not exist.

- [ ] **Step 6: Implement the view with native SVG and accessible fallback**

`MetricChart` uses an SVG `viewBox`, three labelled series, circles only for
non-null values, and a dashed reference line. `MetricTable` exposes the exact
same numbers in a visually compact table. `LineageTree` renders an SVG edge
layer plus real `<button>` nodes with status text. `CommandCenter` owns the
selected genome id and synchronizes chart/tree selection with `GenomeDetail`.

The server page exports `dynamic = "force-dynamic"` and calls
`loadDashboardSnapshot()` directly. Catch Atlas errors and render a retryable
error panel without sample metrics.

- [ ] **Step 7: Verify and commit**

Run:

```bash
cd dashboard
npm test -- lib/lineage.test.ts components/command-center.test.tsx
npm run typecheck
npm run lint
git add dashboard
git commit -m "feat(dashboard): visualize genome evolution"
```

---

### Task 4: Live event stream and herd-immunity console

**Files:**
- Create: `dashboard/lib/event-feed.ts`
- Create: `dashboard/lib/event-feed.test.ts`
- Create: `dashboard/app/api/events/route.ts`
- Create: `dashboard/app/api/events/route.test.ts`
- Create: `dashboard/components/event-card.tsx`
- Create: `dashboard/components/ops-console.tsx`
- Create: `dashboard/components/ops-console.test.tsx`
- Create: `dashboard/app/ops/page.tsx`

**Interfaces:**
- Consumes: `GatekeeperEvent`, `AgentSummary`, `normalizeEvent`, and `getDb`.
- Produces: `encodeSseEvent`, `reduceEventFeed`, `routeEventsByAgent`, `GET /api/events`, `OpsConsole`, and `/ops`.

- [ ] **Step 1: Write failing event-feed tests**

```ts
it("deduplicates replayed events without discarding prior feed entries", () => {
  const first = reduceEventFeed([older], newer);
  expect(reduceEventFeed(first, newer)).toEqual(first);
});

it("routes agentless promotions to the shared timeline", () => {
  const routed = routeEventsByAgent([agentAEvent, promotionEvent]);
  expect(routed.agents["agent-a"]).toEqual([agentAEvent]);
  expect(routed.global).toEqual([promotionEvent]);
});
```

Also assert a 200-event cap and newest-last order.

- [ ] **Step 2: Run tests and verify RED**

Run: `cd dashboard && npm test -- lib/event-feed.test.ts`

Expected: FAIL because the reducer does not exist.

- [ ] **Step 3: Implement event-feed functions**

Use event id for deduplication. `encodeSseEvent` must emit exactly:

```text
id: <event id>
event: gatekeeper
data: <single-line JSON>

```

Keep unknown event types neutral and visible.

- [ ] **Step 4: Write failing SSE and Ops tests**

For the route, inject a fake async change stream and assert response headers,
one encoded event, and `changeStream.close()` on cancellation. For the UI,
assert both agent panels, a reconnecting status, global promotion placement,
and a banner containing `agent-b hot-swapped to g-0008 in 1400 ms`.

Render an event whose payload contains `<img src=x onerror=alert(1)>` and assert
the text is visible while `container.querySelector("img")` is null.

- [ ] **Step 5: Run tests and verify RED**

Run: `cd dashboard && npm test -- app/api/events/route.test.ts components/ops-console.test.tsx`

Expected: FAIL because the route and UI do not exist.

- [ ] **Step 6: Implement SSE and the split-screen console**

The route uses Node runtime and `db.collection("events").watch([], { fullDocument: "updateLookup" })`.
Return `Content-Type: text/event-stream`, `Cache-Control: no-cache, no-transform`,
and `Connection: keep-alive`. Enqueue a `: heartbeat\n\n` comment every 15
seconds and close the change stream when the request aborts.

`OpsConsole` starts with snapshot events, connects an `EventSource`, dispatches
normalized events through `reduceEventFeed`, marks the feed reconnecting on
error, and fetches `/api/dashboard` on the next open event to reconcile gaps.
The `/ops` server page exports `dynamic = "force-dynamic"` and loads the same
snapshot directly so the first render contains both agent panels.

- [ ] **Step 7: Verify and commit**

Run:

```bash
cd dashboard
npm test -- lib/event-feed.test.ts app/api/events/route.test.ts components/ops-console.test.tsx
npm run typecheck
npm run lint
git add dashboard
git commit -m "feat(dashboard): stream herd-immunity events"
```

---

### Task 5: Safe harness proxy and live controls

**Files:**
- Create: `dashboard/lib/harness.ts`
- Create: `dashboard/lib/harness.test.ts`
- Create: `dashboard/app/api/harness/[action]/route.ts`
- Create: `dashboard/app/api/harness/[action]/route.test.ts`
- Create: `dashboard/components/harness-controls.tsx`
- Create: `dashboard/components/harness-controls.test.tsx`
- Modify: `dashboard/components/ops-console.tsx`

**Interfaces:**
- Consumes: `HARNESS_API_URL` and Task 4 `OpsConsole`.
- Produces: `HarnessAction = "health" | "screen" | "redteam" | "evolve" | "immune"`, `forwardHarness(action, request, fetcher?)`, allowlisted `/api/harness/[action]`, and `HarnessControls`.

- [ ] **Step 1: Write failing proxy tests**

Assert the exact mapping:

```ts
expect(resolveHarnessAction("redteam")).toEqual({ method: "POST", path: "/redteam/attack", timeoutMs: 90_000 });
expect(resolveHarnessAction("unknown")).toBeNull();
```

Test that `forwardHarness` keeps a backend 409 status and normalized message,
returns 503 for missing `HARNESS_API_URL`, returns 504 after timeout, and never
accepts a caller-provided URL.

- [ ] **Step 2: Run proxy tests and verify RED**

Run: `cd dashboard && npm test -- lib/harness.test.ts`

Expected: FAIL because the proxy functions do not exist.

- [ ] **Step 3: Implement the allowlist and route**

Use this fixed map:

```ts
const ACTIONS = {
  health: { method: "GET", path: "/health", timeoutMs: 10_000 },
  screen: { method: "POST", path: "/screen", timeoutMs: 90_000 },
  redteam: { method: "POST", path: "/redteam/attack", timeoutMs: 90_000 },
  evolve: { method: "POST", path: "/evolve/step", timeoutMs: 600_000 },
  immune: { method: "POST", path: "/immune/step", timeoutMs: 600_000 },
} as const;
```

Strip the trailing slash from the configured base, use `AbortSignal.timeout`,
parse JSON only when available, and return `{ error: string }` for network or
timeout failures. The dynamic route accepts GET only for health and POST only
for all other actions.

- [ ] **Step 4: Write failing control tests**

Select `agent-b`, choose `compliance_preapproval`, click “Launch red-team
attack,” and assert the request body is
`{ target_agent: "agent-b", family: "compliance_preapproval" }`. Verify only
that button disables during its request. For an evolve 409, assert the visible
message is “Another harness step is already running.”

- [ ] **Step 5: Run control tests and verify RED**

Run: `cd dashboard && npm test -- components/harness-controls.test.tsx`

Expected: FAIL because `HarnessControls` does not exist.

- [ ] **Step 6: Implement controls and verify GREEN**

Provide three focused actions: red-team attack, run immune step, run evolution
step. Keep independent pending/result state per action and rely on the event
stream for timeline updates. Mount the controls above the split screen.

Run:

```bash
cd dashboard
npm test -- lib/harness.test.ts app/api/harness/[action]/route.test.ts components/harness-controls.test.tsx
npm run typecheck
npm run lint
git add dashboard
git commit -m "feat(dashboard): connect live harness controls"
```

---

### Task 6: Vendor screening and trace inspection

**Files:**
- Create: `dashboard/components/screen-form.tsx`
- Create: `dashboard/components/screen-result.tsx`
- Create: `dashboard/components/trace-view.tsx`
- Create: `dashboard/components/screen-form.test.tsx`
- Create: `dashboard/app/screen/page.tsx`

**Interfaces:**
- Consumes: `POST /api/harness/screen`, `GET /api/traces/:id`, `GenomeSummary`, and Task 1 `TraceView`.
- Produces: `ScreenForm`, `ScreenResult`, `TraceView`, and `/screen`.

- [ ] **Step 1: Write failing form-flow tests**

Fill the form and assert the exact request shape:

```ts
expect(screenRequest).toEqual({
  agent_instance: "agent-b",
  genome_id: "g-0001",
  vendor: { name: "Renaissance Capital", country: "RU", lei: null, website: null },
  request: { amount_usd: 40000, justification: "New supplier onboarding" },
});
```

Assert required name/country and positive amount errors are announced without
a request. Simulate an offline 503 and confirm all entered values remain.
Simulate a success and assert decision, memo, cost, block reason, and trace
steps render.

Render memo/trace content containing `<script>window.pwned=true</script>` and
assert literal text is visible while `container.querySelector("script")` is
null.

- [ ] **Step 2: Run tests and verify RED**

Run: `cd dashboard && npm test -- components/screen-form.test.tsx`

Expected: FAIL because the screening components do not exist.

- [ ] **Step 3: Implement the form and result flow**

Use controlled fields with these defaults: `agent-a`, no genome override,
`Renaissance Capital`, `RU`, amount `40000`, and `New supplier onboarding`.
Convert blank optional fields to `null`. On success, render the returned
decision first, then memo, cost, blocked actions, and fetch the trace id for an
expandable step list. If the trace request fails, keep the decision visible and
show “Trace details unavailable.”

The `/screen` server page exports `dynamic = "force-dynamic"`, loads genome
summaries for a labelled override select, and falls back to an empty override
list with an Atlas-offline notice while keeping manual screening available.

- [ ] **Step 4: Verify and commit**

Run:

```bash
cd dashboard
npm test -- components/screen-form.test.tsx
npm run typecheck
npm run lint
git add dashboard
git commit -m "feat(dashboard): add vendor screening console"
```

---

### Task 7: Shared shell, production styling, and deployment contract

**Files:**
- Create: `dashboard/app/layout.tsx`
- Create: `dashboard/app/globals.css`
- Create: `dashboard/app/loading.tsx`
- Create: `dashboard/app/ops/loading.tsx`
- Create: `dashboard/components/app-shell.tsx`
- Create: `dashboard/components/app-shell.test.tsx`
- Create: `dashboard/.env.example`
- Create: `dashboard/vercel.json`
- Create: `dashboard/README.md`
- Modify: `README.md`

**Interfaces:**
- Consumes: all three pages and `GET /api/harness/health`.
- Produces: responsive navigation, connection/champion status, documented local/Vercel setup, and Vercel project configuration.

- [ ] **Step 1: Write failing shell tests**

Assert all three navigation links, a visible current champion badge, Atlas
connected/error states, harness online/offline states, keyboard-visible link
labels, and an `aria-current="page"` marker for the active route.

- [ ] **Step 2: Run tests and verify RED**

Run: `cd dashboard && npm test -- components/app-shell.test.tsx`

Expected: FAIL because the shell does not exist.

- [ ] **Step 3: Implement the shared shell and design system**

Define CSS variables for navy surfaces, borders, text, muted text, green,
amber, red, and cyan. Use a 4/8 px spacing rhythm, 6/10 px radii, tabular
numbers for metrics, and no gradients. Add `:focus-visible`, reduced-motion,
empty/error/skeleton styles, chart/lineage layouts, event treatments, and the
below-900-px stacked layout. The shell polls health at a low frequency and
labels connection state with text in addition to color.

Both loading files render the same fixed-height chart/tree and agent-panel
skeleton regions used by the completed pages, with `aria-label="Loading dashboard"`
and no animated motion when `prefers-reduced-motion` is set.

- [ ] **Step 4: Add deployment documentation**

`dashboard/.env.example` contains names only:

```dotenv
MONGODB_URI=
MONGODB_DB=gatekeeper
HARNESS_API_URL=http://localhost:8000
```

`dashboard/vercel.json` is exact and deliberately avoids account-specific
settings:

```json
{
  "framework": "nextjs",
  "buildCommand": "npm run build"
}
```

Export `export const maxDuration = 60` from the SSE route, which gives change-stream
connections a bounded lifetime and lets EventSource reconnect. `dashboard/README.md`
documents `npm install`, `npm run dev`, required environment variables, local
FastAPI startup, Vercel root directory `dashboard`, and the requirement for a
network-reachable harness URL in production. Add one root README paragraph and
link to the dashboard README without rewriting Utsav’s harness documentation.

- [ ] **Step 5: Verify and commit**

Run:

```bash
cd dashboard
npm test -- components/app-shell.test.tsx
npm test
npm run typecheck
npm run lint
npm run build
cd ..
uv run pytest -q
git diff --check
git add dashboard README.md
git commit -m "feat(dashboard): finish Vercel demo experience"
```

Expected: dashboard tests, typecheck, lint, production build, and the complete
Python test suite pass.

---

### Task 8: Integrated browser verification, deployment, and PR

**Files:**
- Modify only files required to correct defects found by verification.

**Interfaces:**
- Consumes: completed `/dashboard`, Atlas credentials, local FastAPI harness, and Vercel CLI/session.
- Produces: verified Vercel deployment, pushed branch, and review PR.

- [ ] **Step 1: Run the integrated stack**

In separate terminals:

```bash
uv run uvicorn harness.server:app --port 8000
cd dashboard && npm run dev
```

Open `/`, `/ops`, and `/screen`. Verify real Atlas metrics, lineage selection,
both agents, event-stream updates, a baseline genome override screen, and one
safe live action. Do not trigger evolution/immune steps unless the current
Atlas/demo state is intended to change.

- [ ] **Step 2: Verify failure and responsive states**

Temporarily use an unreachable harness URL in the local process, not in a
committed file. Confirm read-only Atlas views remain usable and entered screen
form data survives the error. Resize below 900 px, test keyboard navigation,
and verify EventSource reconnection retains prior events.

- [ ] **Step 3: Correct only verified defects**

For each defect, add a focused failing test, run it to observe RED, apply the
minimal fix, and rerun the affected test plus the full dashboard suite. Commit
each independent correction as `fix(dashboard): <observed behavior>`.

- [ ] **Step 4: Run final verification**

Run:

```bash
cd dashboard
npm test
npm run typecheck
npm run lint
npm run build
cd ..
uv run pytest -q
git status --short
git diff origin/main...HEAD --check
```

Inspect `git diff origin/main...HEAD` for secrets and confirm `.superpowers`,
`.env*`, `.next`, `node_modules`, coverage, and `.vercel` are absent.

- [ ] **Step 5: Deploy and smoke-test production**

From `/dashboard`, link or create the intended Vercel project with root
directory `dashboard`, set `MONGODB_URI`, `MONGODB_DB`, and `HARNESS_API_URL`
through Vercel’s secret UI/CLI prompts, then run:

```bash
vercel --prod
```

Open the production URL and smoke-test the Command Center data. Test live
actions only when `HARNESS_API_URL` is network-reachable.

- [ ] **Step 6: Push and open the review PR**

Run:

```bash
git push -u origin codex/dashboard-integration
gh pr create --base main --head codex/dashboard-integration --title "feat(dashboard): add Atlas-backed harness console" --body-file /tmp/gatekeeper-dashboard-pr.md
```

The PR body must list: all three routes, Atlas collections/projections,
FastAPI endpoints consumed, environment names, production URL, exact test
results, known deployment dependency on a reachable harness, and screenshots
of Command Center and Live Ops. Do not merge without Utsav’s review.
