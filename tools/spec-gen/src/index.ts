/** CLI entry point: clone -> phases -> emit -> validate. See docs/spec-generation-strategy.md. */

import { readFileSync, writeFileSync, mkdirSync, existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { cleanupClone, obtainTermixSource } from "./clone.js";
import { loadBackendProject, loadFrontendProject } from "./project.js";
import { discoverRoutes } from "./routes.js";
import { extractDrizzleSchema } from "./drizzle.js";
import { buildAnalysisContext, analyzeRoute } from "./handler-analysis.js";
import type { RouteAnalysis } from "./types.js";
import { buildOpenApiDocument } from "./openapi.js";
import { buildReport, lintOpenApi } from "./validate.js";
import { extractTestExamples } from "./tests-examples.js";
import { extractFrontendCrossChecks } from "./frontend-client.js";
import { extractJsdocText } from "./jsdoc-text.js";

const __dirname = dirname(fileURLToPath(import.meta.url));

function parseArgs(argv: string[]): Record<string, string | boolean> {
  const out: Record<string, string | boolean> = {};
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (!a.startsWith("--")) continue;
    const key = a.slice(2);
    const next = argv[i + 1];
    if (next && !next.startsWith("--")) {
      out[key] = next;
      i++;
    } else {
      out[key] = true;
    }
  }
  return out;
}

async function main(): Promise<void> {
  const args = parseArgs(process.argv.slice(2));
  const repoPathArg = typeof args.repo === "string" ? args.repo : undefined;
  const tagArg = typeof args.tag === "string" && args.tag !== "latest" ? args.tag : undefined;
  const keep = args.keep === true;

  const clone = await obtainTermixSource({
    repoPath: repoPathArg,
    tag: tagArg,
    installDeps: repoPathArg ? false : true,
  });

  try {
    console.error(`[spec-gen] source: ${clone.repoPath} (tag=${clone.tag}, commit=${clone.commit})`);

    const servicesConfigPath = join(__dirname, "..", "config", "services.json");
    const servicesConfig = JSON.parse(readFileSync(servicesConfigPath, "utf8"));
    delete servicesConfig._comment;

    const project = loadBackendProject(clone.repoPath);
    console.error(`[spec-gen] loaded ${project.getSourceFiles().length} backend source files`);

    const { ir, handlerIndex } = discoverRoutes(project, clone.repoPath, servicesConfig);
    ir.meta.tag = clone.tag;
    ir.meta.commit = clone.commit;

    console.error(
      `[spec-gen] Phase 1: ${ir.routes.length} routes across ${ir.services.length} services, ` +
        `${ir.unresolved.length} unresolved`,
    );

    const outDir = join(__dirname, "..", "..", "..", "spec");
    if (!existsSync(outDir)) mkdirSync(outDir, { recursive: true });
    const outPath = join(outDir, "termix-routes-ir.json");
    writeFileSync(outPath, JSON.stringify(ir, null, 2) + "\n", "utf8");
    console.error(`[spec-gen] wrote ${outPath}`);

    if (ir.unresolved.length > 0) {
      console.error(`[spec-gen] ${ir.unresolved.length} unresolved route(s):`);
      for (const u of ir.unresolved.slice(0, 20)) {
        console.error(`  ${u.file}:${u.line} - ${u.reason}`);
      }
    }

    const drizzleIr = extractDrizzleSchema(project, clone.repoPath);
    const totalColumns = drizzleIr.tables.reduce((n, t) => n + t.columns.length, 0);
    console.error(`[spec-gen] Phase 5: ${drizzleIr.tables.length} tables, ${totalColumns} columns`);
    const drizzleOutPath = join(outDir, "termix-drizzle-ir.json");
    writeFileSync(drizzleOutPath, JSON.stringify(drizzleIr, null, 2) + "\n", "utf8");
    console.error(`[spec-gen] wrote ${drizzleOutPath}`);

    const transformersConfigPath = join(__dirname, "..", "config", "transformers.json");
    const transformersConfig = JSON.parse(readFileSync(transformersConfigPath, "utf8"));
    const analysisCtx = buildAnalysisContext(drizzleIr.tables, transformersConfig);

    const serviceByKey = new Map(ir.services.map((s) => [s.key, s]));
    const analyses: RouteAnalysis[] = [];
    let opaqueCount = 0;
    for (const route of ir.routes) {
      const handle = handlerIndex.get(route.id);
      if (!handle) continue;
      const analysis = analyzeRoute(route, handle.handler, serviceByKey.get(route.service), analysisCtx);
      if (analysis.opaque) opaqueCount++;
      analyses.push(analysis);
    }
    console.error(`[spec-gen] Phases 2-4: analyzed ${analyses.length} routes (${opaqueCount} opaque handlers)`);
    const analysesOutPath = join(outDir, "termix-analysis-ir.json");
    writeFileSync(analysesOutPath, JSON.stringify(analyses, null, 2) + "\n", "utf8");
    console.error(`[spec-gen] wrote ${analysesOutPath}`);

    const testExamples = extractTestExamples(project, clone.repoPath, ir);
    console.error(`[spec-gen] Phase 6: mined ${testExamples.length} example(s) from the test suite`);
    const testExamplesOutPath = join(outDir, "termix-test-examples.json");
    writeFileSync(testExamplesOutPath, JSON.stringify(testExamples, null, 2) + "\n", "utf8");
    console.error(`[spec-gen] wrote ${testExamplesOutPath}`);

    const frontendProject = loadFrontendProject(clone.repoPath);
    const frontendCrossChecks = extractFrontendCrossChecks(frontendProject, clone.repoPath, ir, analyses);
    console.error(`[spec-gen] Phase 7: cross-checked ${frontendCrossChecks.length} frontend call(s) against routes`);
    const frontendOutPath = join(outDir, "termix-frontend-crosscheck.json");
    writeFileSync(frontendOutPath, JSON.stringify(frontendCrossChecks, null, 2) + "\n", "utf8");
    console.error(`[spec-gen] wrote ${frontendOutPath}`);

    const jsdocText = extractJsdocText(project);
    console.error(`[spec-gen] Phase 8: reused text from ${jsdocText.size} existing @openapi block(s)`);

    const openapi = buildOpenApiDocument(ir, drizzleIr, analyses, testExamples, frontendCrossChecks, jsdocText);
    const openapiPath = join(outDir, "termix-openapi.json");
    writeFileSync(openapiPath, JSON.stringify(openapi, null, 2) + "\n", "utf8");
    console.error(`[spec-gen] Phase 9: wrote ${openapiPath} (${Object.keys(openapi.paths).length} paths)`);

    const lintSummary = lintOpenApi(openapiPath);
    const report =
      buildReport(ir, drizzleIr, analyses, testExamples, frontendCrossChecks, jsdocText.size) + "\n" + lintSummary;
    const reportPath = join(outDir, "report.md");
    writeFileSync(reportPath, report, "utf8");
    console.error(`[spec-gen] Phase 10: wrote ${reportPath}`);
  } finally {
    if (!keep) cleanupClone(clone);
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
