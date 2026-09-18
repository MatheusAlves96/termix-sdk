/**
 * Phase 10: validation and report. See tools/spec-gen/docs/spec-generation-strategy.md.
 *
 * Implements the mechanical checks (route counts, response coverage, confidence
 * distribution, opaque handlers). The diff against the official openapi.json and the
 * @redocly/cli lint pass are not wired in yet — see the "not yet implemented" note this
 * report ends with.
 */

import { execFileSync } from "node:child_process";
import { existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import type { Confidence, DrizzleIR, RouteAnalysis, RoutesIR, SchemaNode } from "./types.js";

const __dirname = dirname(fileURLToPath(import.meta.url));

/** Runs the locally-installed @redocly/cli lint against the generated spec (Phase 10, criterion 3). */
export function lintOpenApi(specPath: string): string {
  // Invoke the package's actual JS entry point with `node` directly, rather than the
  // node_modules/.bin/redocly(.cmd) shim — avoids relying on a shell (and the arg-escaping
  // footgun that comes with execFileSync's `shell: true`) to run a Windows .cmd wrapper.
  const cliEntry = join(__dirname, "..", "node_modules", "@redocly", "cli", "bin", "cli.js");
  if (!existsSync(cliEntry)) {
    return "## OpenAPI lint\n\n@redocly/cli is not installed (run `npm install` in tools/spec-gen); skipped.\n";
  }
  try {
    const out = execFileSync(process.execPath, [cliEntry, "lint", specPath, "--format=json"], { encoding: "utf8" });
    const parsed = JSON.parse(out) as { totals?: { errors: number; warnings: number; ignored: number } };
    const totals = parsed.totals ?? { errors: 0, warnings: 0, ignored: 0 };
    return `## OpenAPI lint (@redocly/cli)\n\n- Errors: **${totals.errors}**\n- Warnings: **${totals.warnings}**\n- Ignored: **${totals.ignored}**\n\n${totals.errors === 0 ? "Spec is structurally valid OpenAPI 3.1." : "Spec has structural errors — see `npx redocly lint spec/termix-openapi.json` for details."}\n`;
  } catch (err) {
    // redocly exits non-zero when there are lint errors; still try to parse its stdout.
    const stdout = (err as { stdout?: string }).stdout;
    if (stdout) {
      try {
        const parsed = JSON.parse(stdout) as { totals?: { errors: number; warnings: number; ignored: number } };
        const totals = parsed.totals ?? { errors: 0, warnings: 0, ignored: 0 };
        return `## OpenAPI lint (@redocly/cli)\n\n- Errors: **${totals.errors}**\n- Warnings: **${totals.warnings}**\n- Ignored: **${totals.ignored}**\n`;
      } catch {
        /* fall through to generic failure message */
      }
    }
    return `## OpenAPI lint\n\nFailed to run @redocly/cli: ${err instanceof Error ? err.message : String(err)}\n`;
  }
}

function walkConfidence(node: SchemaNode | undefined, counts: Record<Confidence, number>): void {
  if (!node) return;
  counts[node.confidence] = (counts[node.confidence] ?? 0) + 1;
  if (node.items) walkConfidence(node.items, counts);
  if (node.properties) for (const v of Object.values(node.properties)) walkConfidence(v, counts);
  if (node.oneOf) for (const v of node.oneOf) walkConfidence(v, counts);
}

function emptyConfidenceCounts(): Record<Confidence, number> {
  return { test: 0, "repository-type": 0, "handler-literal": 0, "frontend-type": 0, "matched-type": 0, inferred: 0, unknown: 0 };
}

export function buildReport(routesIr: RoutesIR, drizzleIr: DrizzleIR, analyses: RouteAnalysis[]): string {
  const lines: string[] = [];
  const push = (s: string) => lines.push(s);

  const byService = new Map<string, number>();
  for (const r of routesIr.routes) byService.set(r.service, (byService.get(r.service) ?? 0) + 1);

  const analysisById = new Map(analyses.map((a) => [a.routeId, a]));
  const opaqueRoutes = routesIr.routes.filter((r) => analysisById.get(r.id)?.opaque);
  const withoutSuccessResponse = routesIr.routes.filter((r) => {
    if (r.anyMethod) return false;
    const a = analysisById.get(r.id);
    if (!a) return true;
    return !a.responses.some((resp) => typeof resp.status === "number" && resp.status >= 200 && resp.status < 400);
  });

  const requestConfidence = emptyConfidenceCounts();
  const responseConfidence = emptyConfidenceCounts();
  for (const a of analyses) {
    for (const v of a.requestBody) walkConfidence(v.schema, requestConfidence);
    for (const r of a.responses) walkConfidence(r.schema, responseConfidence);
  }

  const unknownHeavyRoutes = routesIr.routes.filter((r) => {
    const a = analysisById.get(r.id);
    if (!a || a.responses.length === 0) return false;
    return a.responses.every((resp) => !resp.schema || resp.schema.confidence === "unknown");
  });

  push("# termix-sdk spec-gen report");
  push("");
  push(`Generated from tag \`${routesIr.meta.tag}\` (commit \`${routesIr.meta.commit}\`) on ${routesIr.meta.generatedAt}.`);
  push("");

  push("## Route counts");
  push("");
  const anyMethodCount = routesIr.routes.filter((r) => r.anyMethod).length;
  push(`- Total route registrations: **${routesIr.routes.length}** (${anyMethodCount} of which are \`X.use()\` method catch-alls, listed under \`x-any-method-routes\` instead of \`paths\`)`);
  push(`- Unresolved routes (origin never reached an express() app): **${routesIr.unresolved.length}**`);
  push("");
  push("| Service | Port | Routes | Global auth |");
  push("|---|---|---|---|");
  for (const s of routesIr.services) {
    push(`| ${s.key} | ${s.port ?? "?"} | ${byService.get(s.key) ?? 0} | ${s.globalAuth ? `yes (from line ${s.globalAuthLine})` : "no (per-route)"} |`);
  }
  push("");

  if (routesIr.unresolved.length > 0) {
    push("### Unresolved routes");
    push("");
    for (const u of routesIr.unresolved.slice(0, 50)) {
      push(`- \`${u.file}:${u.line}\` — ${u.reason}`);
    }
    push("");
  }

  push("## Drizzle schema");
  push("");
  push(`- Tables: **${drizzleIr.tables.length}**`);
  push(`- Columns: **${drizzleIr.tables.reduce((n, t) => n + t.columns.length, 0)}**`);
  push("");

  push("## Handler analysis coverage");
  push("");
  push(`- Routes with a resolvable handler: **${analyses.length - opaqueRoutes.length}/${analyses.length}**`);
  push(`- Opaque handlers (could not be statically resolved): **${opaqueRoutes.length}**`);
  push(`- Routes with no documented 2xx/3xx response: **${withoutSuccessResponse.length}**`);
  push(`- Routes whose every response is \`x-confidence: unknown\`: **${unknownHeavyRoutes.length}**`);
  push("");

  push("### Request body field confidence");
  push("");
  push("| Confidence | Count |");
  push("|---|---|");
  for (const [k, v] of Object.entries(requestConfidence)) if (v > 0) push(`| ${k} | ${v} |`);
  push("");

  push("### Response field confidence");
  push("");
  push("| Confidence | Count |");
  push("|---|---|");
  for (const [k, v] of Object.entries(responseConfidence)) if (v > 0) push(`| ${k} | ${v} |`);
  push("");

  if (opaqueRoutes.length > 0) {
    push("### Opaque handlers (worth a manual look)");
    push("");
    for (const r of opaqueRoutes.slice(0, 40)) push(`- ${r.method} ${r.path} — \`${r.file}:${r.line}\` (handlerKind: ${r.handlerKind})`);
    push("");
  }

  if (withoutSuccessResponse.length > 0) {
    push("### Routes with no documented success response");
    push("");
    for (const r of withoutSuccessResponse.slice(0, 40)) push(`- ${r.method} ${r.path} — \`${r.file}:${r.line}\``);
    push("");
  }

  push("## Not yet implemented");
  push("");
  push("- Diff against the official Termix openapi.json (design doc Phase 10, criterion 4).");
  push("- Phase 6 (cross-check against `tests/database/routes/*.test.ts` examples) and Phase 7 (cross-check against the frontend axios client) are not wired into this CLI run yet; `RouteAnalysis` and the routes IR carry enough (file/line, route ids) for both to be added without reworking earlier phases.");
  push("");

  return lines.join("\n");
}
