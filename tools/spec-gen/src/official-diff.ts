/**
 * Phase 10, criterion 4: diffs our generated spec against the *official* one.
 *
 * "Official" here means regenerated the same way Termix's own release process does it —
 * `npm run generate:openapi`, which runs `tsc` then `swaggerJSDoc(swaggerOptions)` and
 * writes `openapi.json` at the repo root (see `src/backend/utils/swagger.ts`) — rather
 * than scraping the published docs site. That's deliberate: the docs site
 * (docs.termix.site/api/termix-api) is a Docusaurus build that bakes the spec into
 * static HTML at *its own* build time, from *its own* repo, so there's no stable raw-JSON
 * URL to fetch, and matching it exactly would mean reverse-engineering a third party's
 * build pipeline instead of just running the one Termix already ships. Regenerating
 * locally from the same clone this tool already has is reproducible, has no dependency on
 * a third-party site's uptime or structure, and is confirmed to match the docs site's
 * published counts (413 method+path pairs, 7 servers, both in the release-2.7.1-tag spec
 * regenerated this way and in the earlier manual audit of the published docs page).
 *
 * See tools/spec-gen/docs/spec-generation-strategy.md, Phase 10.
 */

import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { run } from "./clone.js";
import type { OfficialSpecDiff, RoutesIR } from "./types.js";

const HTTP_METHOD_KEYS = new Set(["get", "post", "put", "patch", "delete", "head", "options"]);

/** Runs `npm run generate:openapi` in the given checkout and returns the parsed spec, or
 *  null if generation failed for any reason (a different Termix version might not even
 *  have this script, or its build might fail) — never fatal to the rest of the pipeline. */
export function generateOfficialSpec(repoPath: string): Record<string, unknown> | null {
  try {
    run("npm", ["run", "generate:openapi"], repoPath);
  } catch (err) {
    console.error(`[official-diff] \`npm run generate:openapi\` failed: ${err instanceof Error ? err.message : String(err)}`);
    return null;
  }

  const outPath = join(repoPath, "openapi.json");
  if (!existsSync(outPath)) {
    console.error("[official-diff] generate:openapi ran but openapi.json was not written at the repo root");
    return null;
  }
  try {
    return JSON.parse(readFileSync(outPath, "utf8")) as Record<string, unknown>;
  } catch (err) {
    console.error(`[official-diff] failed to parse the official openapi.json: ${err instanceof Error ? err.message : String(err)}`);
    return null;
  }
}

function officialOperationKeys(spec: Record<string, unknown>): Set<string> {
  const out = new Set<string>();
  const paths = spec.paths;
  if (!paths || typeof paths !== "object") return out;
  for (const [path, itemRaw] of Object.entries(paths as Record<string, unknown>)) {
    if (!itemRaw || typeof itemRaw !== "object") continue;
    for (const method of Object.keys(itemRaw as Record<string, unknown>)) {
      if (HTTP_METHOD_KEYS.has(method.toLowerCase())) out.add(`${method.toUpperCase()} ${path}`);
    }
  }
  return out;
}

export function diffAgainstOfficial(routesIr: RoutesIR, officialSpec: Record<string, unknown> | null): OfficialSpecDiff {
  if (!officialSpec) {
    return {
      available: false,
      reason: "could not regenerate the official openapi.json (see the [official-diff] log line above)",
      officialOperationCount: 0,
      generatedOperationCount: 0,
      onlyInOfficial: [],
      onlyInGenerated: [],
      matchedCount: 0,
    };
  }

  const official = officialOperationKeys(officialSpec);
  const generated = new Set<string>();
  for (const r of routesIr.routes) {
    const pathKey = r.path.replace(/:([A-Za-z_][A-Za-z0-9_]*)/g, "{$1}");
    if (r.anyMethod) {
      // Registered via X.use(), so it genuinely answers every method — Phase 9 can't
      // represent that as one OpenAPI operation (hence x-any-method-routes instead of
      // `paths`), but for this diff it should count as a match against whichever single
      // method the hand-written docs happened to pick.
      for (const m of HTTP_METHOD_KEYS) generated.add(`${m.toUpperCase()} ${pathKey}`);
      continue;
    }
    generated.add(`${r.method} ${pathKey}`);
  }

  const onlyInOfficial = [...official].filter((k) => !generated.has(k)).sort();
  const onlyInGenerated = [...generated].filter((k) => !official.has(k)).sort();

  return {
    available: true,
    officialOperationCount: official.size,
    generatedOperationCount: generated.size,
    onlyInOfficial,
    onlyInGenerated,
    matchedCount: official.size - onlyInOfficial.length,
  };
}
