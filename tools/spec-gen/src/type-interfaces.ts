/**
 * E3 (docs/spec-generation-strategy-v2.md): indexes `src/types/index.ts`'s own interfaces and
 * inline-object type aliases, so a request-body field that E0/E1/E2/E5 couldn't type can,
 * when the route's whole field set overlaps heavily with one of these, borrow that
 * interface's property type. This is where the string enums live (`authType: "password" |
 * "key" | "credential" | ...`) that never appear in any handler validator and aren't a
 * Drizzle column either (the column backing them is just `text`).
 *
 * Self-contained: deliberately does NOT reuse handler-analysis.ts's schemaFromType (which
 * needs an AnalysisContext for Drizzle-record `$ref` resolution that's irrelevant here) —
 * E3 only ever matches a request body's own top-level, flat fields against an interface's
 * top-level properties, so a small primitive/union/array walk is all that's needed.
 */

import { Node, Project, Type } from "ts-morph";
import type { Confidence, SchemaNode } from "./types.js";
import { relFile } from "./project.js";

const TYPES_INDEX_FILE = "src/types/index.ts";

export interface TypeInterfaceEntry {
  name: string;
  fields: Set<string>;
  properties: Map<string, SchemaNode>;
}

function schemaFromInterfaceType(type: Type, depth: number): SchemaNode {
  const conf: Confidence = "matched-type";
  if (type.isAny() || type.isUnknown()) return { type: "unknown", confidence: "unknown" };
  if (type.isNull()) return { type: "null", nullable: true, confidence: conf };
  if (type.isUndefined() || type.isVoid()) return { type: "unknown", confidence: "unknown" };
  if (type.isBooleanLiteral() || type.isBoolean()) return { type: "boolean", confidence: conf };
  if (type.isNumberLiteral() || type.isNumber()) return { type: "number", confidence: conf };
  if (type.isStringLiteral() || type.isString()) return { type: "string", confidence: conf };

  if (type.isUnion()) {
    const variants = type.getUnionTypes();
    const nullable = variants.some((v) => v.isUndefined() || v.isNull());
    const rest = variants.filter((v) => !v.isUndefined() && !v.isNull());
    if (rest.length === 1) {
      const inner = schemaFromInterfaceType(rest[0], depth);
      return nullable ? { ...inner, nullable: true } : inner;
    }
    if (rest.length > 0 && rest.every((v) => v.isStringLiteral())) {
      return { type: "string", enumValues: rest.map((v) => String(v.getLiteralValue())), confidence: conf, ...(nullable ? { nullable: true } : {}) };
    }
    // A mixed union (e.g. `string | StatsConfig`) is exactly the "not expanded" case — no
    // false precision, stays unknown same as it would have without E3.
    return { type: "unknown", confidence: "unknown", note: "union type, not expanded" };
  }

  if (type.isArray()) {
    if (depth >= 2) return { type: "array", confidence: "unknown" };
    return { type: "array", items: schemaFromInterfaceType(type.getArrayElementTypeOrThrow(), depth + 1), confidence: conf };
  }

  // Nested objects/named types: out of scope for E3's flat top-level matching.
  return { type: "unknown", confidence: "unknown" };
}

export function extractTypeInterfaces(frontendProject: Project, repoPath: string): TypeInterfaceEntry[] {
  const sf = frontendProject.getSourceFiles().find((f) => relFile(repoPath, f.getFilePath()) === TYPES_INDEX_FILE);
  if (!sf) return [];
  const out: TypeInterfaceEntry[] = [];

  for (const iface of sf.getInterfaces()) {
    const properties = new Map<string, SchemaNode>();
    for (const prop of iface.getProperties()) properties.set(prop.getName(), schemaFromInterfaceType(prop.getType(), 0));
    if (properties.size > 0) out.push({ name: iface.getName(), fields: new Set(properties.keys()), properties });
  }

  for (const alias of sf.getTypeAliases()) {
    const typeNode = alias.getTypeNode();
    if (!typeNode || !Node.isTypeLiteral(typeNode)) continue;
    const properties = new Map<string, SchemaNode>();
    for (const member of typeNode.getMembers()) {
      if (!Node.isPropertySignature(member)) continue;
      properties.set(member.getName(), schemaFromInterfaceType(member.getType(), 0));
    }
    if (properties.size > 0) out.push({ name: alias.getName(), fields: new Set(properties.keys()), properties });
  }

  return out;
}
