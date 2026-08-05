/**
 * WOLF collector: a daily Cloudflare Worker that accumulates public market
 * facts nobody can revoke.
 *
 * Why this exists at all. Historical index membership and delisted price
 * history are the two things data vendors actually charge for, and both are
 * only expensive because you are buying *the past*. Recorded forward, day by
 * day, they cost nothing. Every day this runs, the dataset gets one day better
 * and is survivorship-free by construction rather than by reconstruction.
 *
 * Why SEC EDGAR. It is the only source in the whole comparison that is free,
 * unlimited, unauthenticated, and public domain, so it is also the only one we
 * may legally redistribute. US Government works carry no terms of service to
 * violate. One request returns every filing the SEC accepted that day.
 *
 * What this is NOT. It is not a backend WOLF depends on. The app fetches from
 * source directly and treats this only as a mirror, because "no service behind
 * it" is a promise on the website and a user's portfolio must never require
 * someone else's Cloudflare account.
 */

/** SEC fair access refuses clients that offer no way to contact them. */
const USER_AGENT = "WOLF/0.1 (wolf@clive5.com)";

/** SEC allows 10 requests/second. One a day is not the constraint here. */
const IDX = (y, q, ymd) =>
  `https://www.sec.gov/Archives/edgar/daily-index/${y}/QTR${q}/form.${ymd}.idx`;

/**
 * Forms worth keeping.
 *
 * 4      insider transactions, filed within 2 business days with exact share
 *        counts and prices. The timeliest informed-trading signal that is free.
 * 25-NSE the exchange's own delisting notice, carrying a ruleProvision that
 *        distinguishes a merger from a compliance failure. That distinction is
 *        what stops a backtest treating an acquisition like a bankruptcy.
 * 25     the issuer's voluntary withdrawal equivalent.
 * 13D    an activist crossing 5%.
 */
const KEEP = new Set(["4", "25-NSE", "25", "SC 13D"]);

const pad = (n) => String(n).padStart(2, "0");
const ymd = (d) => `${d.getUTCFullYear()}${pad(d.getUTCMonth() + 1)}${pad(d.getUTCDate())}`;
const iso = (d) => d.toISOString().slice(0, 10);

/**
 * EDGAR publishes no index on weekends or federal holidays. Rather than model
 * the holiday calendar, walk back until a day answers 200. A missing index is
 * indistinguishable from a market closure, and both mean "nothing to collect".
 */
function previousBusinessDay(from) {
  const d = new Date(from);
  do {
    d.setUTCDate(d.getUTCDate() - 1);
  } while (d.getUTCDay() === 0 || d.getUTCDay() === 6);
  return d;
}

/**
 * Parse the SEC's daily form index.
 *
 * The layout resists every obvious approach. The header wraps across two lines
 * ("Form Type  Company Name  CIK" then "Date Filed  File Name"), and the rule
 * beneath it is one unbroken run of dashes, so neither yields column widths.
 * Splitting on whitespace fails too, because form types contain spaces
 * ("SC 13D", "1-A POS") and so do company names.
 *
 * So anchor from the right, where the shapes are unambiguous: the path always
 * begins "edgar/", the date is always exactly eight digits, and the CIK is the
 * digits before it. Whatever remains splits into form and company at the first
 * run of two or more spaces, which single-spaced names cannot contain.
 */
const TAIL = /\s+(\d{1,10})\s+(\d{8})\s+(edgar\/\S+)\s*$/;

export function parseFormIndex(text) {
  const rows = [];
  let seen = 0;
  for (const line of text.split("\n")) {
    const tail = TAIL.exec(line);
    if (!tail) continue;
    seen += 1;
    const [, cik, filed, path] = tail;
    const head = line.slice(0, tail.index);
    const split = /\s{2,}/.exec(head);
    if (!split) continue;
    const form = head.slice(0, split.index).trim();
    if (!KEEP.has(form)) continue;
    rows.push({
      form,
      company: head.slice(split.index).trim(),
      cik: cik.padStart(10, "0"),
      // Stored ISO so it sorts lexically and joins against everything else.
      filed: `${filed.slice(0, 4)}-${filed.slice(4, 6)}-${filed.slice(6, 8)}`,
      // The accession is the filename stem, and it is the SEC's own key.
      accession: path.split("/").pop().replace(/\.txt$/, ""),
      path,
    });
  }
  // A layout change would show up as zero parsable lines in a file that plainly
  // has thousands. Failing loudly beats silently collecting nothing for months.
  if (seen === 0) throw new Error("form index yielded no parsable rows; layout changed");
  return rows;
}

async function collectDay(env, day) {
  const quarter = Math.floor(day.getUTCMonth() / 3) + 1;
  const url = IDX(day.getUTCFullYear(), quarter, ymd(day));

  const res = await fetch(url, {
    headers: { "User-Agent": USER_AGENT, "Accept-Encoding": "gzip" },
    cf: { cacheTtl: 3600 },
  });
  if (res.status === 404) return { day: iso(day), skipped: "no index published" };
  if (!res.ok) throw new Error(`EDGAR returned HTTP ${res.status} for ${url}`);

  const rows = parseFormIndex(await res.text());

  // Insert in batches. D1 free allows 100k row writes a day and a busy session
  // is under 2,500 rows, so the limit is not the constraint. The batch exists
  // so one malformed row cannot abort the whole day.
  const stmt = env.DB.prepare(
    `INSERT OR IGNORE INTO filings
       (accession, form, cik, company, filed, path, collected_at)
     VALUES (?, ?, ?, ?, ?, ?, ?)`,
  );
  const collectedAt = new Date().toISOString();
  const batch = rows.map((r) =>
    stmt.bind(r.accession, r.form, r.cik, r.company, r.filed, r.path, collectedAt),
  );
  for (let i = 0; i < batch.length; i += 500) {
    await env.DB.batch(batch.slice(i, i + 500));
  }

  const counts = {};
  for (const r of rows) counts[r.form] = (counts[r.form] || 0) + 1;

  await env.DB.prepare(
    `INSERT OR REPLACE INTO runs (day, rows, detail, ran_at) VALUES (?, ?, ?, ?)`,
  )
    .bind(iso(day), rows.length, JSON.stringify(counts), collectedAt)
    .run();

  return { day: iso(day), rows: rows.length, counts };
}

export default {
  /** Cron target. Wrangler schedules this; see wrangler.toml. */
  async scheduled(event, env, ctx) {
    ctx.waitUntil(
      collectDay(env, previousBusinessDay(new Date())).then(
        (r) => console.log("collected", JSON.stringify(r)),
        // A failed day must be visible and must not poison the next run.
        (e) => console.error("collection failed:", e.message),
      ),
    );
  },

  /**
   * Read-only HTTP surface. Deliberately has no write path: the only thing
   * that writes here is the cron, so a leaked URL cannot corrupt the record.
   */
  async fetch(request, env) {
    const url = new URL(request.url);

    if (url.pathname === "/health") {
      const last = await env.DB.prepare(
        "SELECT day, rows, ran_at FROM runs ORDER BY day DESC LIMIT 1",
      ).first();
      return Response.json({ ok: true, last_run: last ?? null });
    }

    if (url.pathname === "/filings") {
      const form = url.searchParams.get("form");
      const cik = url.searchParams.get("cik");
      const limit = Math.min(Number(url.searchParams.get("limit") ?? 100), 1000);
      let sql = "SELECT * FROM filings";
      const where = [];
      const args = [];
      if (form) (where.push("form = ?"), args.push(form));
      if (cik) (where.push("cik = ?"), args.push(cik.padStart(10, "0")));
      if (where.length) sql += ` WHERE ${where.join(" AND ")}`;
      sql += " ORDER BY filed DESC, accession DESC LIMIT ?";
      args.push(limit);
      const { results } = await env.DB.prepare(sql).bind(...args).all();
      return Response.json({ count: results.length, filings: results });
    }

    // Manual backfill, so a missed day can be recovered without waiting a week.
    if (url.pathname === "/collect" && request.method === "POST") {
      if (env.COLLECT_TOKEN && url.searchParams.get("token") !== env.COLLECT_TOKEN) {
        return new Response("forbidden", { status: 403 });
      }
      const raw = url.searchParams.get("day");
      const day = raw ? new Date(`${raw}T00:00:00Z`) : previousBusinessDay(new Date());
      if (Number.isNaN(day.getTime())) return new Response("bad day", { status: 400 });
      return Response.json(await collectDay(env, day));
    }

    return new Response(
      "WOLF collector. Public SEC filing index, collected daily.\n" +
        "  GET  /health\n  GET  /filings?form=4&cik=0000320193&limit=100\n",
      { headers: { "content-type": "text/plain" } },
    );
  },
};
