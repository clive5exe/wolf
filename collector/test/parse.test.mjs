/**
 * The parser is the only fragile part of the collector, because the SEC's
 * layout is a fixed-width format with no machine-readable schema. These cases
 * are the ones that actually broke a naive implementation.
 *
 * Run: node --test collector/test/
 */
import assert from "node:assert/strict";
import { test } from "node:test";
import { parseFormIndex } from "../src/index.js";

const header = [
  "Description:           Daily Index of EDGAR Dissemination Feed by Form Type",
  "Form Type   Company Name                                                  CIK",
  "      Date Filed  File Name",
  "-".repeat(141),
].join("\n");

const row = (form, company, cik, date, path) =>
  `${form.padEnd(17)}${company.padEnd(62)}${cik.padEnd(12)}${date}    ${path}`;

test("parses a plain Form 4 row", () => {
  const [f] = parseFormIndex(
    header + "\n" + row("4", "4D Molecular Therapeutics, Inc.", "1650648", "20260804",
      "edgar/data/1650648/0001193125-26-333014.txt"),
  );
  assert.equal(f.form, "4");
  assert.equal(f.company, "4D Molecular Therapeutics, Inc.");
  assert.equal(f.cik, "0001650648", "CIK must be zero-padded so joins are exact");
  assert.equal(f.filed, "2026-08-04", "stored ISO so it sorts lexically");
  assert.equal(f.accession, "0001193125-26-333014");
});

test("keeps multi-word form types, which whitespace splitting would break", () => {
  const rows = parseFormIndex(
    header + "\n" +
    row("SC 13D", "ACTIVIST FUND LP", "1111111", "20260804", "edgar/data/1/a.txt") + "\n" +
    row("25-NSE", "Cboe BZX Exchange, Inc.", "1417835", "20260804", "edgar/data/2/b.txt"),
  );
  assert.deepEqual(rows.map((r) => r.form), ["SC 13D", "25-NSE"]);
});

test("keeps company names containing digits and punctuation", () => {
  const [f] = parseFormIndex(
    header + "\n" + row("4", "1-800-FLOWERS.COM, INC.", "1084869", "20260804",
      "edgar/data/1084869/c.txt"),
  );
  assert.equal(f.company, "1-800-FLOWERS.COM, INC.");
});

test("drops forms outside the allowlist", () => {
  const rows = parseFormIndex(
    header + "\n" +
    row("1-A", "Arte Consulting Inc.", "2137570", "20260804", "edgar/data/1/d.txt") + "\n" +
    row("4", "REAL ONE", "1650648", "20260804", "edgar/data/2/e.txt"),
  );
  assert.deepEqual(rows.map((r) => r.form), ["4"]);
});

test("throws rather than silently collecting nothing if the layout changes", () => {
  // A file with no parsable rows means the format moved. Returning [] here
  // would look identical to a quiet day and could go unnoticed for months.
  assert.throws(() => parseFormIndex("Description: something\n" + "-".repeat(20)),
    /layout changed/);
});

test("a genuinely empty day is not an error, only an empty result", () => {
  const rows = parseFormIndex(
    header + "\n" + row("1-A", "IGNORED CO", "1", "20260804", "edgar/data/1/f.txt"),
  );
  assert.deepEqual(rows, [], "parsable but unwanted forms yield no rows and no throw");
});
