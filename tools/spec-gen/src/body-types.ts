/**
 * E4 (docs/spec-generation-strategy-v2.md): fills in what the backend-only Phases 2-4
 * analysis left as a request-body gap, using Phase 7's frontend cross-check — necessarily a
 * post-process step, since frontendCrossChecks is itself computed from `analyses`. Two parts:
 *
 * 1. A route where the backend analysis found NO body field at all (`requestBody: []`) but a
 *    matched frontend call's own body type has real properties -> use that whole body. This
 *    closes a real gap: the emission-time fallback that already existed in openapi.ts only
 *    ever applied to a JSON variant that already existed with zero properties (the busboy-
 *    parsed-body case) — it never ran for a route with an empty requestBody array, which is
 *    the common shape (13 of 55 such routes have a usable frontend body type).
 * 2. Any field still `unknown` after E0-E3/E5, in a route that does have a JSON variant,
 *    inherits the type of the same-named property in a matched frontend call's body type,
 *    when that property itself has a concrete type.
 *
 * Confidence for everything filled in here is already "frontend-type" — schemaFromFrontendType
 * (frontend-client.ts) stamps that recursively when it builds a call's bodyType, so this
 * module just copies nodes, it doesn't need to set confidence itself.
 */

import type { FrontendCrossCheck, RouteAnalysis, RoutesIR, SchemaNode } from "./types.js";

function frontendBodyForRoute(routeId: string, frontendCrossChecks: FrontendCrossCheck[]): SchemaNode | null {
  // Same selection rule openapi.ts already used for its narrower fallback: prefer a matched
  // call whose body type actually has properties (an empty object, or a multipart/Blob body,
  // tells us nothing more than the backend already didn't).
  const match = frontendCrossChecks.find(
    (fc) =>
      fc.routeId === routeId &&
      fc.call.bodyType?.type === "object" &&
      Object.keys(fc.call.bodyType.properties ?? {}).length > 0,
  );
  return match?.call.bodyType ?? null;
}

export interface FrontendEnrichmentStats {
  /** Routes that had zero body fields before this and now have a whole frontend-typed body. */
  wholeBodyRoutes: number;
  /** Individual fields that were `unknown` and now carry the frontend's own type. */
  mergedFields: number;
}

export function enrichRequestBodiesFromFrontend(
  routesIr: RoutesIR,
  analyses: RouteAnalysis[],
  frontendCrossChecks: FrontendCrossCheck[],
): FrontendEnrichmentStats {
  const routesById = new Map(routesIr.routes.map((r) => [r.id, r]));
  const stats: FrontendEnrichmentStats = { wholeBodyRoutes: 0, mergedFields: 0 };

  for (const analysis of analyses) {
    const route = routesById.get(analysis.routeId);
    if (!route || route.anyMethod || !["POST", "PUT", "PATCH"].includes(route.method)) continue;

    const frontendBody = frontendBodyForRoute(analysis.routeId, frontendCrossChecks);
    if (!frontendBody) continue;

    if (analysis.requestBody.length === 0) {
      analysis.requestBody.push({ contentType: "application/json", schema: frontendBody });
      stats.wholeBodyRoutes++;
      continue;
    }

    const jsonVariant = analysis.requestBody.find((v) => v.contentType === "application/json");
    if (!jsonVariant?.schema.properties) continue;
    for (const [name, prop] of Object.entries(jsonVariant.schema.properties)) {
      if (prop.confidence !== "unknown") continue;
      const frontendProp = frontendBody.properties?.[name];
      if (!frontendProp?.type || frontendProp.type === "unknown") continue;
      jsonVariant.schema.properties[name] = frontendProp;
      stats.mergedFields++;
    }
  }

  return stats;
}
