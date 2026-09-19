/**
 * Passo 0 (docs/spec-generation-strategy-v2.md): a fixed set of request-body routes whose
 * pre-plan field types are frozen in `config/golden-baseline.json`. Every strategy added by
 * the v2 plan (E0-E5) is only allowed to turn an `unknown` field into something concrete —
 * never to change the type of a field that already had one from an explicit validator (or
 * any other pre-plan signal). This module snapshots those routes from a fresh analysis run
 * and flags any field that regressed.
 */

import type { Confidence, HttpMethod, RouteAnalysis, RoutesIR, SchemaNode } from "./types.js";

export interface GoldenRoute {
  method: HttpMethod;
  path: string;
  /** Why this route is in the set — which guard/case it exercises. */
  note: string;
}

export const GOLDEN_ROUTES: GoldenRoute[] = [
  {
    method: "POST",
    path: "/host/db/host",
    note: "86 fields; every guard case at once: int-as-boolean (`x ? 1 : 0`), JSON-in-text and CSV-in-text columns, the authType enum",
  },
  {
    method: "PATCH",
    path: "/open-tabs/:id",
    note: "`req.body as Partial<{...}>` assigned to a plain identifier, then passed whole to a repository call — never destructured or accessed field-by-field, so today's extractor finds zero fields",
  },
  {
    method: "POST",
    path: "/notification-channels",
    note: "`req.body as {...}` plus `typeof name !== \"string\"` and `type !== \"webhook\" && type !== \"ntfy\" && ...` validators",
  },
  {
    method: "POST",
    path: "/users/sso-providers",
    note: "default literals (`enabled = true`, `displayOrder = 0`) and field names that match Drizzle columns",
  },
  {
    method: "PUT",
    path: "/snippets/reorder",
    note: "body passed whole to a helper typed `unknown` — stays unknown except through the frontend (E4); nothing to regress here, only room to improve",
  },
  {
    method: "POST",
    path: "/ssh/file_manager/ssh/createFile",
    note: "no Drizzle table, no src/types interface, no frontend call — sessionId/path/fileName should legitimately stay unknown",
  },
];

type GoldenFieldSnapshot = Record<string, { type: SchemaNode["type"]; confidence: Confidence }>;
export type GoldenSnapshot = Record<string, GoldenFieldSnapshot>;

function goldenKey(method: string, path: string): string {
  return `${method} ${path}`;
}

/** Reads the current field types/confidences for every GOLDEN_ROUTES entry out of a fresh analysis run. */
export function snapshotGoldenRoutes(routesIr: RoutesIR, analyses: RouteAnalysis[]): GoldenSnapshot {
  const analysisById = new Map(analyses.map((a) => [a.routeId, a]));
  const out: GoldenSnapshot = {};
  for (const g of GOLDEN_ROUTES) {
    const route = routesIr.routes.find((r) => r.method === g.method && r.path === g.path && !r.anyMethod);
    if (!route) continue;
    const analysis = analysisById.get(route.id);
    const variant = analysis?.requestBody.find((v) => v.contentType === "application/json") ?? analysis?.requestBody[0];
    const fields: GoldenFieldSnapshot = {};
    for (const [name, node] of Object.entries(variant?.schema.properties ?? {})) {
      fields[name] = { type: node.type, confidence: node.confidence };
    }
    out[goldenKey(g.method, g.path)] = fields;
  }
  return out;
}

export interface GoldenViolation {
  route: string;
  field: string;
  baselineType: SchemaNode["type"];
  baselineConfidence: Confidence;
  currentType: SchemaNode["type"] | undefined;
  currentConfidence: Confidence | undefined;
}

/**
 * A field the baseline already typed (confidence !== "unknown") must keep the exact same
 * type in every later run — that's the invariant every E0-E5 heuristic promises to respect.
 * Fields the baseline left `unknown` are unconstrained: turning them into something concrete
 * is the entire point of this plan, not a regression.
 */
export function checkGoldenRoutes(baseline: GoldenSnapshot, current: GoldenSnapshot): GoldenViolation[] {
  const violations: GoldenViolation[] = [];
  for (const [route, fields] of Object.entries(baseline)) {
    const currentFields = current[route] ?? {};
    for (const [field, base] of Object.entries(fields)) {
      if (base.confidence === "unknown") continue;
      const cur = currentFields[field];
      if (!cur || cur.type !== base.type) {
        violations.push({
          route,
          field,
          baselineType: base.type,
          baselineConfidence: base.confidence,
          currentType: cur?.type,
          currentConfidence: cur?.confidence,
        });
      }
    }
  }
  return violations;
}
