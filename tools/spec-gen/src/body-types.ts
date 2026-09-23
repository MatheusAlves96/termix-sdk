/**
 * E4 (docs/spec-generation-strategy-v2.md): fills in what the backend-only Phases 2-4
 * analysis left as a request-body gap, using Phase 7's frontend cross-check — necessarily a
 * post-process step, since frontendCrossChecks is itself computed from `analyses`. Three parts:
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
 * 3. A field the frontend body type has that the backend walk never found AT ALL — not even
 *    as an `unknown`-typed placeholder — because the field is read off the body from inside a
 *    helper function the backend walk (extractBodyFields in handler-analysis.ts) doesn't
 *    follow into. Confirmed real case: `POST /rbac/host/{id}/share` and its three siblings
 *    all validate their `targets` array by calling `parseShareTargets(req.body ?? {})`, which
 *    reads `body.targets` from inside its own function body rather than the route handler
 *    destructuring or `.`-accessing it directly — so `targets`, the one field that actually
 *    names who a share goes to, never made it into the schema at all, even though the
 *    frontend's own `ShareTarget[]` typing for it (src/ui/api/rbac-api.ts) was right there.
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
  /** Fields the backend walk never found at all, added wholesale from the frontend's body type. */
  newFields: number;
}

export function enrichRequestBodiesFromFrontend(
  routesIr: RoutesIR,
  analyses: RouteAnalysis[],
  frontendCrossChecks: FrontendCrossCheck[],
): FrontendEnrichmentStats {
  const routesById = new Map(routesIr.routes.map((r) => [r.id, r]));
  const stats: FrontendEnrichmentStats = { wholeBodyRoutes: 0, mergedFields: 0, newFields: 0 };

  for (const analysis of analyses) {
    const route = routesById.get(analysis.routeId);
    if (!route || route.anyMethod || !["POST", "PUT", "PATCH", "DELETE"].includes(route.method)) continue;

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

    // 3: a field the frontend body has that isn't in the backend-derived property set at all
    // (not even as an `unknown` placeholder) — see part 3 of the module doc above.
    const frontendRequired = new Set(frontendBody.required ?? []);
    for (const [name, frontendProp] of Object.entries(frontendBody.properties ?? {})) {
      if (name in jsonVariant.schema.properties) continue;
      if (!frontendProp.type || frontendProp.type === "unknown") continue;
      jsonVariant.schema.properties[name] = frontendProp;
      if (frontendRequired.has(name)) {
        jsonVariant.schema.required = [...new Set([...(jsonVariant.schema.required ?? []), name])];
      }
      stats.newFields++;
    }
  }

  return stats;
}
