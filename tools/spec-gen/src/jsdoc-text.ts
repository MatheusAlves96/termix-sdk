/**
 * Phase 8: reuses `summary`/`description`/`tags`/parameter descriptions from the
 * existing hand-written `/** @openapi ... *\/` JSDoc comments above route handlers.
 *
 * These comments are real YAML (that's what `swagger-jsdoc`, which builds the
 * official spec, parses them as) and `@openapi` is recognized by TypeScript's own
 * JSDoc parser as a normal custom tag, so `tag.getComment()` hands back the YAML
 * body already stripped of the `/** ` / ` * ` / ` *\/` comment framing — no need to
 * hand-roll a comment-stripping parser.
 *
 * Never used as a source of `requestBody`/`responses` schema (see
 * api-schema-validation.md / the design doc's Background section for why: 98.4% of
 * response objects in the official spec have no schema at all, and the ones with a
 * body are frequently missing fields the real handler reads). Only prose survives.
 *
 * See tools/spec-gen/docs/spec-generation-strategy.md, Phase 8.
 */

import { Project, SyntaxKind } from "ts-morph";
import { parse as parseYaml } from "yaml";
import type { HttpMethod } from "./types.js";

export interface JsdocRouteText {
  summary?: string;
  description?: string;
  tags?: string[];
  /** Parameter name -> its documented description */
  parameters?: Record<string, string>;
}

const HTTP_METHOD_KEYS = new Set(["get", "post", "put", "patch", "delete", "head", "options"]);

function commentToString(comment: ReturnType<import("ts-morph").JSDocTag["getComment"]>): string | null {
  if (comment === undefined) return null;
  if (typeof comment === "string") return comment;
  return comment
    .map((part) => (part && "getText" in part ? part.getText() : String(part ?? "")))
    .join("");
}

function coerceStringArray(value: unknown): string[] | undefined {
  if (Array.isArray(value)) {
    const strings = value.filter((v): v is string => typeof v === "string");
    return strings.length > 0 ? strings : undefined;
  }
  if (typeof value === "string") return [value];
  return undefined;
}

/** Builds `key(method, path)` the same way for both the JSDoc map and the route lookup. */
export function jsdocTextKey(method: HttpMethod | string, path: string): string {
  return `${method.toString().toUpperCase()} ${path}`;
}

/**
 * Parses every `@openapi` JSDoc block in the backend project into a flat map keyed
 * by "METHOD /path" (path already in `{param}` OpenAPI form, exactly as these
 * comments write it and exactly as Phase 9 keys `paths`) — no per-file correlation
 * needed, the YAML's own path key is the full resolved path a human would write.
 */
export function extractJsdocText(project: Project): Map<string, JsdocRouteText> {
  const out = new Map<string, JsdocRouteText>();
  let parseFailures = 0;

  for (const sf of project.getSourceFiles()) {
    for (const doc of sf.getDescendantsOfKind(SyntaxKind.JSDoc)) {
      const tag = doc.getTags().find((t) => t.getTagName() === "openapi");
      if (!tag) continue;
      const yamlText = commentToString(tag.getComment());
      if (!yamlText) continue;

      let parsed: unknown;
      try {
        parsed = parseYaml(yamlText);
      } catch {
        parseFailures++;
        continue;
      }
      if (!parsed || typeof parsed !== "object") continue;

      for (const [path, methodsRaw] of Object.entries(parsed as Record<string, unknown>)) {
        if (!methodsRaw || typeof methodsRaw !== "object") continue;
        for (const [methodKey, opRaw] of Object.entries(methodsRaw as Record<string, unknown>)) {
          const method = methodKey.toLowerCase();
          if (!HTTP_METHOD_KEYS.has(method)) continue;
          if (!opRaw || typeof opRaw !== "object") continue;
          const op = opRaw as Record<string, unknown>;

          const entry: JsdocRouteText = {};
          if (typeof op.summary === "string") entry.summary = op.summary;
          if (typeof op.description === "string") entry.description = op.description;
          const tags = coerceStringArray(op.tags);
          if (tags) entry.tags = tags;

          if (Array.isArray(op.parameters)) {
            const params: Record<string, string> = {};
            for (const p of op.parameters) {
              if (p && typeof p === "object" && typeof (p as Record<string, unknown>).name === "string" && typeof (p as Record<string, unknown>).description === "string") {
                params[(p as Record<string, unknown>).name as string] = (p as Record<string, unknown>).description as string;
              }
            }
            if (Object.keys(params).length > 0) entry.parameters = params;
          }

          if (Object.keys(entry).length === 0) continue;
          out.set(jsdocTextKey(method, path), entry);
        }
      }
    }
  }

  if (parseFailures > 0) {
    console.error(`[jsdoc-text] ${parseFailures} @openapi block(s) failed to parse as YAML and were skipped`);
  }

  return out;
}
