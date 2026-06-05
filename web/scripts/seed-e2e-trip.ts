/**
 * E2E seed script — slice 4.4 commit 1 (p8l).
 *
 * Creates a deterministic test trip + test user for Playwright auth-gated
 * smoke tests to render against. Idempotent: re-running on an already-
 * seeded DB is a no-op.
 *
 * Run via `pnpm seed:e2e-trip`. Companion to `mint-playwright-auth.ts`
 * which builds the storageState cookie; both are commit-1 prerequisites
 * for the chromium-authed Playwright project.
 *
 * Seed shape (load-bearing for slice 4.4 map smoke + future visual slices):
 *   - destination: "Coorg, Karnataka, India" (matches the
 *     destination-coords substring lookup in slice 4.4 commit 2)
 *   - 3 days × ~4 blocks each = 13 total blocks
 *   - block types cover all 4: venue, meal, transit, rest (verifies
 *     Material Symbols mapping across all 4 types per slice 4.3 §9.5)
 *   - JobRun row: status=succeeded, agent_summary populated
 *   - status: "draft" (legacy column, unchanged)
 *
 * Predictable UUIDs:
 *   user.id = 11111111-1111-1111-1111-111111111111
 *   trip.id = 22222222-2222-2222-2222-222222222222
 *
 * Auth.js v5 with @auth/pg-adapter expects the users table to use
 * camelCase quoted columns (slice 4.1 mvs aligned this). We seed with
 * the exact schema the adapter writes against.
 *
 * Idempotency strategy: each INSERT uses ON CONFLICT (id) DO NOTHING,
 * so re-running is safe. No UPDATE branch — the seed is point-in-time.
 * If you change the seed shape, drop the test trip first and re-run.
 */

import { randomUUID } from "node:crypto";

import pg from "pg";

const { Client } = pg;

const SEED_USER_ID = "11111111-1111-1111-1111-111111111111";
const SEED_USER_EMAIL = "e2e-test@trip-concierge.local";
const SEED_TRIP_ID = "22222222-2222-2222-2222-222222222222";

const DAYS = [
  {
    id: "33333333-3333-3333-3333-333333333331",
    day_number: 1,
    date: "2026-07-01",
    summary: "Arrival + coffee estate orientation",
    blocks: [
      { type: "transit", venue_name: "Bengaluru → Coorg drive", start_time: "08:00", duration_minutes: 360 },
      { type: "venue", venue_name: "Tata Coffee Plantation tour, Pollibetta", start_time: "15:00", duration_minutes: 120, est_cost: "500.00" },
      { type: "meal", venue_name: "Coorg Cuisine Restaurant, Madikeri", start_time: "19:00", duration_minutes: 75, est_cost: "600.00" },
      { type: "rest", venue_name: "Golden Beans Homestay — overnight", start_time: "21:00", duration_minutes: 540 },
    ],
  },
  {
    id: "33333333-3333-3333-3333-333333333332",
    day_number: 2,
    date: "2026-07-02",
    summary: "Madikeri + Abbey Falls exploration",
    blocks: [
      { type: "meal", venue_name: "Breakfast at Golden Beans Homestay", start_time: "08:00", duration_minutes: 60 },
      { type: "transit", venue_name: "Drive to Madikeri town", start_time: "09:30", duration_minutes: 60 },
      { type: "venue", venue_name: "Abbey Falls", start_time: "11:00", duration_minutes: 90, est_cost: "30.00" },
      { type: "meal", venue_name: "Lunch at East End Hotel, Madikeri", start_time: "13:30", duration_minutes: 60, est_cost: "400.00" },
      { type: "venue", venue_name: "Raja's Seat sunset point", start_time: "17:00", duration_minutes: 90 },
    ],
  },
  {
    id: "33333333-3333-3333-3333-333333333333",
    day_number: 3,
    date: "2026-07-03",
    summary: "Dubare Elephant Camp + departure",
    blocks: [
      { type: "venue", venue_name: "Dubare Elephant Camp", start_time: "09:00", duration_minutes: 180, est_cost: "1500.00" },
      { type: "meal", venue_name: "Lunch at Camp restaurant", start_time: "13:00", duration_minutes: 60, est_cost: "450.00" },
      { type: "transit", venue_name: "Drive Coorg → Bengaluru", start_time: "15:00", duration_minutes: 360 },
    ],
  },
];

const AGENT_SUMMARY = [
  { agent: "Researcher", step: 1, duration_ms: 32500, tokens: 1840 },
  { agent: "Local Expert", step: 2, duration_ms: 28100, tokens: 1560 },
  { agent: "Logistics", step: 3, duration_ms: 41200, tokens: 2310 },
  { agent: "Budget Auditor", step: 4, duration_ms: 18900, tokens: 980 },
];

async function main() {
  const databaseUrl =
    process.env.DATABASE_URL ?? "postgresql://postgres:postgres@localhost:5432/trip_concierge";
  // pg-client doesn't speak SQLAlchemy URL prefixes; strip the +psycopg.
  const pgUrl = databaseUrl.replace("postgresql+psycopg://", "postgresql://");

  const client = new Client({ connectionString: pgUrl });
  await client.connect();
  console.log(`Connected to ${pgUrl.replace(/:[^@/]+@/, ":***@")}`);

  try {
    await client.query("BEGIN");

    // User (auth.js camelCase schema per @auth/pg-adapter)
    const userResult = await client.query(
      `INSERT INTO users (id, email, name, "emailVerified")
       VALUES ($1, $2, $3, NOW())
       ON CONFLICT (id) DO NOTHING
       RETURNING id`,
      [SEED_USER_ID, SEED_USER_EMAIL, "E2E Test User"],
    );
    console.log(
      userResult.rowCount === 0
        ? `User ${SEED_USER_ID} already exists (no-op)`
        : `User ${SEED_USER_ID} created`,
    );

    // Trip
    const tripResult = await client.query(
      `INSERT INTO trips (id, user_id, destination, currency, group_size, pace, budget_total)
       VALUES ($1, $2, $3, $4, $5, $6, $7)
       ON CONFLICT (id) DO NOTHING
       RETURNING id`,
      [SEED_TRIP_ID, SEED_USER_ID, "Coorg, Karnataka, India", "INR", 2, "balanced", "40000.00"],
    );
    console.log(
      tripResult.rowCount === 0
        ? `Trip ${SEED_TRIP_ID} already exists (no-op)`
        : `Trip ${SEED_TRIP_ID} created`,
    );

    // Days + blocks (skip if any day for this trip already exists)
    const existingDays = await client.query("SELECT id FROM days WHERE trip_id = $1 LIMIT 1", [
      SEED_TRIP_ID,
    ]);
    if (existingDays.rowCount === 0) {
      for (const day of DAYS) {
        await client.query(
          `INSERT INTO days (id, trip_id, day_number, date, summary) VALUES ($1, $2, $3, $4, $5)`,
          [day.id, SEED_TRIP_ID, day.day_number, day.date, day.summary],
        );
        let order = 1;
        for (const block of day.blocks) {
          await client.query(
            `INSERT INTO blocks (id, day_id, "order", type, venue_name, start_time, duration_minutes, est_cost, currency, notes)
             VALUES ($1, $2, $3, $4, $5, $6, $7, $8, 'INR', '')`,
            [
              randomUUID(),
              day.id,
              order++,
              block.type,
              block.venue_name,
              block.start_time,
              block.duration_minutes,
              ("est_cost" in block ? block.est_cost : null) ?? null,
            ],
          );
        }
      }
      console.log(`Seeded ${DAYS.length} days + ${DAYS.flatMap((d) => d.blocks).length} blocks`);
    } else {
      console.log("Days+blocks already seeded (no-op)");
    }

    // JobRun (status=succeeded, agent_summary populated for F8 panel test)
    const jobResult = await client.query(
      `INSERT INTO job_runs (job_id, trip_id, kind, status, approved, agent_summary, total_tokens, total_cost, total_duration_ms, started_at, finished_at)
       VALUES ($1, $2, 'plan', 'succeeded', true, $3, 0, 0, 0, NOW(), NOW())
       ON CONFLICT (job_id) DO NOTHING
       RETURNING id`,
      ["e2e-coorg-job-1", SEED_TRIP_ID, JSON.stringify(AGENT_SUMMARY)],
    );
    console.log(
      jobResult.rowCount === 0
        ? `JobRun already exists (no-op)`
        : `JobRun e2e-coorg-job-1 created`,
    );

    await client.query("COMMIT");
    console.log("\nSeed complete. Trip ID:", SEED_TRIP_ID);
  } catch (err) {
    await client.query("ROLLBACK");
    console.error("Seed failed:", err);
    process.exitCode = 1;
  } finally {
    await client.end();
  }
}

main();
