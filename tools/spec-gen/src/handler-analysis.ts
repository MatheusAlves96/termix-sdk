/**
 * Phases 2-4, combined: for a single route's resolved handler function, derive
 * auth requirements, path/query/header parameters, the request body schema(s),
 * and every response the handler (or a helper it forwards `res` to) can emit.
 *
 * Kept as one module because all four facets are read off the same handler
 * AST in one pass; splitting them into separate files (as the phase-numbered
 * layout in docs/spec-generation-strategy.md suggests) would mean re-walking
 * the same function body three or four times for no benefit.
 *
 * See tools/spec-gen/docs/spec-generation-strategy.md, Phases 2-4.
 */

import { Node, SyntaxKind, Type } from "ts-morph";
import type {
  AuthInfo,
  Confidence,
  HeaderParamInfo,
  JsonPrimitive,
  PathParamInfo,
  QueryParamInfo,
  RequestBodyVariant,
  ResponseInfo,
  RouteAnalysis,
  RouteRecord,
  SchemaNode,
  ServiceInfo,
  TableSchema,
} from "./types.js";
import { applyKnownTransformer } from "./transformers.js";
import type { RepositoryTables } from "./repository-tables.js";
import { type TypeInterfaceEntry } from "./type-interfaces.js";

export interface AnalysisContext {
  recordSchemaNames: Set<string>;
  hostsTable: TableSchema | undefined;
  expandedTransformers: Set<string>;
  opaqueTransformers: Set<string>;
  /** E2 (docs/spec-generation-strategy-v2.md): factory function name -> the table(s) it
   *  operates on, e.g. "createCurrentHostRepository" -> { primary: hosts, secondary: [] }. */
  repositoryTables: Map<string, RepositoryTables>;
  /** E3: every interface/inline-object type alias exported from src/types/index.ts. */
  typeInterfaces: TypeInterfaceEntry[];
}

export function buildAnalysisContext(
  tables: TableSchema[],
  transformerConfig: { expanded: string[]; opaque: string[] },
  repositoryTables: Map<string, RepositoryTables> = new Map(),
  typeInterfaces: TypeInterfaceEntry[] = [],
): AnalysisContext {
  return {
    recordSchemaNames: new Set(tables.map((t) => t.schemaName)),
    hostsTable: tables.find((t) => t.tsVarName === "hosts"),
    expandedTransformers: new Set(transformerConfig.expanded),
    opaqueTransformers: new Set(transformerConfig.opaque),
    repositoryTables,
    typeInterfaces,
  };
}

// ---- handler / callee resolution ----

function resolveFunctionNode(nodeIn: Node, depth = 0): Node | null {
  if (depth > 10) return null;
  let node: Node = nodeIn;
  while (Node.isParenthesizedExpression(node)) node = node.getExpression();
  if (Node.isArrowFunction(node) || Node.isFunctionExpression(node) || Node.isFunctionDeclaration(node)) {
    return node;
  }
  if (Node.isIdentifier(node)) {
    const symbol = node.getSymbol();
    if (!symbol) return null;
    let resolved = symbol;
    for (let i = 0; i < 10; i++) {
      const aliased = resolved.getAliasedSymbol();
      if (!aliased) break;
      resolved = aliased;
    }
    for (const decl of resolved.getDeclarations()) {
      if (Node.isFunctionDeclaration(decl)) return decl;
      if (Node.isVariableDeclaration(decl)) {
        const init = decl.getInitializer();
        if (init) {
          const r = resolveFunctionNode(init, depth + 1);
          if (r) return r;
        }
      }
    }
  }
  return null;
}

function getFunctionParams(fn: Node): { getName(): string }[] {
  if (Node.isArrowFunction(fn) || Node.isFunctionExpression(fn) || Node.isFunctionDeclaration(fn)) {
    return fn.getParameters();
  }
  return [];
}

// ---- response-chain walking ----

interface ChainCall {
  method: string;
  args: Node[];
}

/** Peels a `.a(...).b(...).c(...)` chain into ordered calls, plus the root identifier's text. */
function walkChain(exprIn: Node): { rootText: string; calls: ChainCall[] } | null {
  const calls: ChainCall[] = [];
  let cur: Node = exprIn;
  while (Node.isCallExpression(cur)) {
    const callee = cur.getExpression();
    if (Node.isPropertyAccessExpression(callee)) {
      calls.unshift({ method: callee.getName(), args: cur.getArguments() });
      cur = callee.getExpression();
      continue;
    }
    return null;
  }
  if (Node.isIdentifier(cur)) return { rootText: cur.getText(), calls };
  return null;
}

const RESPONSE_TERMINAL_METHODS = new Set([
  "json",
  "send",
  "sendStatus",
  "redirect",
  "sendFile",
  "download",
  "end",
  "write",
  "writeHead",
]);
const RESPONSE_IGNORED_METHODS = new Set([
  "cookie",
  "clearCookie",
  "flushHeaders",
  "setHeader",
  "type",
  "attachment",
  "vary",
  "append",
  "location",
  "status", // never terminal by itself; only meaningful chained before a terminal method
]);

interface RawResponseHit {
  statusCode: number | "default";
  finalMethod: string;
  finalArgs: Node[];
  writeHeadContentType: string | null;
}

/** Collects every `res.<...>` (or helper(res, ...) forwarded) terminal call in a function, up to depth 3. */
function collectResponseHits(
  fnNode: Node,
  resParamName: string,
  depth: number,
  visited: Set<string>,
  out: RawResponseHit[],
): void {
  if (depth > 3) return;
  for (const call of fnNode.getDescendantsOfKind(SyntaxKind.CallExpression)) {
    const parent = call.getParent();
    const isChainLink = parent && Node.isPropertyAccessExpression(parent) && parent.getExpression() === call;
    if (isChainLink) continue; // handled when we reach the outermost call of this chain

    const chain = walkChain(call);
    if (chain && chain.rootText === resParamName) {
      const statusCall = chain.calls.find((c) => c.method === "status");
      const writeHeadCall = chain.calls.find((c) => c.method === "writeHead");
      let statusCode: number | "default" = 200;
      if (statusCall && Node.isNumericLiteral(statusCall.args[0])) statusCode = Number(statusCall.args[0].getText());
      else if (writeHeadCall && Node.isNumericLiteral(writeHeadCall.args[0])) {
        statusCode = Number(writeHeadCall.args[0].getText());
      }

      const last = chain.calls[chain.calls.length - 1];
      if (!last) continue;
      if (last.method === "sendStatus" && Node.isNumericLiteral(last.args[0])) {
        statusCode = Number(last.args[0].getText());
      }
      if (last.method === "redirect") {
        if (last.args[0] && Node.isNumericLiteral(last.args[0])) statusCode = Number(last.args[0].getText());
        else statusCode = 302;
      }

      let writeHeadContentType: string | null = null;
      if (writeHeadCall) {
        const headersArg = writeHeadCall.args.find((a) => Node.isObjectLiteralExpression(a));
        if (headersArg && Node.isObjectLiteralExpression(headersArg)) {
          for (const prop of headersArg.getProperties()) {
            if (Node.isPropertyAssignment(prop) && prop.getName().toLowerCase() === '"content-type"'.replace(/"/g, "")) {
              const init = prop.getInitializer();
              if (init && (Node.isStringLiteral(init) || Node.isNoSubstitutionTemplateLiteral(init))) {
                writeHeadContentType = init.getLiteralText();
              }
            }
          }
        }
      }

      if (RESPONSE_TERMINAL_METHODS.has(last.method)) {
        out.push({ statusCode, finalMethod: last.method, finalArgs: last.args, writeHeadContentType });
      } else if (!RESPONSE_IGNORED_METHODS.has(last.method)) {
        // Unknown method on res/response-like object — record as an opaque response so it
        // isn't silently dropped, but don't try to interpret its arguments.
        out.push({ statusCode, finalMethod: last.method, finalArgs: [], writeHeadContentType });
      }
      continue;
    }

    // helper(res, ...) forwarding: recurse into the callee with the matching parameter name.
    const callee = call.getExpression();
    if (Node.isIdentifier(callee)) {
      const args = call.getArguments();
      const resArgIndex = args.findIndex((a) => Node.isIdentifier(a) && a.getText() === resParamName);
      if (resArgIndex >= 0) {
        const key = `${callee.getText()}@${call.getSourceFile().getFilePath()}:${call.getStart()}`;
        if (visited.has(key)) continue;
        visited.add(key);
        const targetFn = resolveFunctionNode(callee);
        if (targetFn) {
          const params = getFunctionParams(targetFn);
          const targetParamName = params[resArgIndex]?.getName() ?? resParamName;
          collectResponseHits(targetFn, targetParamName, depth + 1, visited, out);
        }
      }
    }
  }
}

// ---- expression -> SchemaNode ----

function getReturnExpression(body: Node): Node | null {
  if (!Node.isBlock(body)) return body; // concise arrow body is itself the returned expression
  for (const stmt of body.getStatements()) {
    if (Node.isReturnStatement(stmt)) {
      const expr = stmt.getExpression();
      if (expr) return expr;
    }
  }
  return null;
}

/**
 * `conf` is the confidence stamped on every concretely-resolved node (arrays/objects/refs
 * propagate it to their children). Defaults to "repository-type" for the original call sites
 * (response schemas resolved off a repository's return type). E0 (docs/
 * spec-generation-strategy-v2.md) reuses this same walk for a request body's own `req.body
 * as {...}` cast, where the right confidence is "handler-literal" instead — the type came
 * from the handler's own source, not from a Drizzle-backed repository return type. `unknown`/
 * `any` stay `unknown` regardless of the caller: not being able to resolve a type at all means
 * the same thing no matter who asked.
 */
function schemaFromType(type: Type, ctx: AnalysisContext, depth: number, conf: Confidence = "repository-type"): SchemaNode {
  let t = type;
  const aliasSymbol = t.getAliasSymbol() ?? t.getSymbol();
  if (aliasSymbol?.getName() === "Promise") {
    const args = t.getTypeArguments();
    if (args[0]) return schemaFromType(args[0], ctx, depth, conf);
  }
  if (t.isAny() || t.isUnknown()) return { type: "unknown", confidence: "unknown" };
  if (t.isNull()) return { type: "null", nullable: true, confidence: conf };
  if (t.isUndefined() || t.isVoid()) return { type: "unknown", confidence: "unknown" };
  if (t.isBooleanLiteral() || t.isBoolean()) return { type: "boolean", confidence: conf };
  if (t.isNumberLiteral() || t.isNumber()) return { type: "number", confidence: conf };
  if (t.isStringLiteral() || t.isString()) return { type: "string", confidence: conf };

  if (t.isUnion()) {
    const variants = t.getUnionTypes();
    const nullable = variants.some((v) => v.isUndefined() || v.isNull());
    const rest = variants.filter((v) => !v.isUndefined() && !v.isNull());
    if (rest.length === 1) {
      const inner = schemaFromType(rest[0], ctx, depth, conf);
      return nullable ? { ...inner, nullable: true } : inner;
    }
    // All-string-literal union -> enum
    if (rest.every((v) => v.isStringLiteral())) {
      return {
        type: "string",
        enumValues: rest.map((v) => String(v.getLiteralValue())),
        confidence: conf,
        ...(nullable ? { nullable: true } : {}),
      };
    }
    return { type: "unknown", confidence: "inferred", note: "union type, not expanded" };
  }

  if (t.isArray()) {
    return { type: "array", items: schemaFromType(t.getArrayElementTypeOrThrow(), ctx, depth + 1, conf), confidence: conf };
  }

  const named = aliasSymbol?.getName();
  if (named && ctx.recordSchemaNames.has(named)) {
    return { ref: named, confidence: conf };
  }

  if (depth >= 3) return { type: "object", confidence: "inferred", note: "object type, depth limit reached" };

  if (t.isObject()) {
    const props = t.getProperties();
    if (props.length === 0 || props.length > 80) return { type: "object", confidence: "unknown" };
    const properties: Record<string, SchemaNode> = {};
    const required: string[] = [];
    for (const p of props) {
      const decl = p.getValueDeclaration() ?? p.getDeclarations()[0];
      if (!decl) continue;
      const propType = p.getTypeAtLocation(decl);
      properties[p.getName()] = schemaFromType(propType, ctx, depth + 1, conf);
      if (!p.isOptional()) required.push(p.getName());
    }
    return { type: "object", properties, required, confidence: conf };
  }

  return { type: "unknown", confidence: "unknown" };
}

function schemaFromExpression(exprIn: Node, ctx: AnalysisContext, depth: number): SchemaNode {
  if (depth > 6) return { type: "unknown", confidence: "unknown" };
  let expr: Node = exprIn;
  while (Node.isParenthesizedExpression(expr)) expr = expr.getExpression();
  if (Node.isAwaitExpression(expr)) return schemaFromExpression(expr.getExpression(), ctx, depth);
  if (Node.isNonNullExpression(expr)) return schemaFromExpression(expr.getExpression(), ctx, depth);

  if (expr.getKind() === SyntaxKind.TrueKeyword) return { const: true, type: "boolean", confidence: "handler-literal" };
  if (expr.getKind() === SyntaxKind.FalseKeyword) return { const: false, type: "boolean", confidence: "handler-literal" };
  if (expr.getKind() === SyntaxKind.NullKeyword) return { type: "null", nullable: true, confidence: "handler-literal" };
  if (Node.isStringLiteral(expr) || Node.isNoSubstitutionTemplateLiteral(expr)) {
    return { const: expr.getLiteralText(), type: "string", confidence: "handler-literal" };
  }
  if (Node.isNumericLiteral(expr)) return { const: Number(expr.getText()), type: "number", confidence: "handler-literal" };

  if (Node.isArrayLiteralExpression(expr)) {
    const els = expr.getElements();
    return {
      type: "array",
      items: els[0] ? schemaFromExpression(els[0], ctx, depth + 1) : { type: "unknown", confidence: "unknown" },
      confidence: "handler-literal",
    };
  }

  if (Node.isObjectLiteralExpression(expr)) {
    const properties: Record<string, SchemaNode> = {};
    const required: string[] = [];
    let note: string | undefined;
    for (const prop of expr.getProperties()) {
      if (Node.isPropertyAssignment(prop)) {
        const init = prop.getInitializer();
        if (!init) continue;
        properties[prop.getName()] = schemaFromExpression(init, ctx, depth + 1);
        required.push(prop.getName());
      } else if (Node.isShorthandPropertyAssignment(prop)) {
        properties[prop.getName()] = schemaFromType(prop.getType(), ctx, depth + 1);
        required.push(prop.getName());
      } else if (Node.isSpreadAssignment(prop)) {
        const spreadSchema = schemaFromExpression(prop.getExpression(), ctx, depth + 1);
        if (spreadSchema.type === "object" && spreadSchema.properties) {
          Object.assign(properties, spreadSchema.properties);
          required.push(...(spreadSchema.required ?? []));
        } else {
          note = spreadSchema.note ?? "includes a spread that could not be expanded";
        }
      }
    }
    return { type: "object", properties, required, confidence: "handler-literal", ...(note ? { note } : {}) };
  }

  if (Node.isCallExpression(expr)) {
    const callee = expr.getExpression();

    if (Node.isIdentifier(callee)) {
      const name = callee.getText();
      if (ctx.expandedTransformers.has(name)) {
        const built = applyKnownTransformer(name, ctx.hostsTable, undefined);
        if (built) return built;
      }
      if (ctx.opaqueTransformers.has(name)) {
        return { type: "object", confidence: "inferred", note: `passed through ${name}(); shape not expanded (see config/transformers.json)` };
      }
    }

    if (Node.isPropertyAccessExpression(callee) && callee.getName() === "map") {
      const arrayExpr = callee.getExpression();
      const mapper = expr.getArguments()[0];
      const baseSchema = schemaFromExpression(arrayExpr, ctx, depth + 1);
      const baseItem = baseSchema.type === "array" ? baseSchema.items : undefined;
      let itemSchema: SchemaNode = { type: "unknown", confidence: "unknown" };
      if (mapper && (Node.isArrowFunction(mapper) || Node.isFunctionExpression(mapper))) {
        const ret = getReturnExpression(mapper.getBody());
        if (ret) itemSchema = schemaFromExpression(ret, ctx, depth + 1);
      } else if (mapper && Node.isIdentifier(mapper) && ctx.expandedTransformers.has(mapper.getText())) {
        const built = applyKnownTransformer(mapper.getText(), ctx.hostsTable, undefined);
        itemSchema = built ?? baseItem ?? { type: "unknown", confidence: "unknown" };
      }
      return { type: "array", items: itemSchema, confidence: "inferred" };
    }

    return schemaFromType(expr.getType(), ctx, depth);
  }

  /** Merges two branches of a conditional/`||`/`??`: fields in only one branch become optional. */
  function mergeBranches(a: SchemaNode, b: SchemaNode, note: string): SchemaNode | null {
    if (a.type !== "object" && b.type !== "object") return null;
    const properties = { ...(b.properties ?? {}), ...(a.properties ?? {}) };
    const aReq = new Set(a.required ?? []);
    const bReq = new Set(b.required ?? []);
    const required = Object.keys(properties).filter((k) => aReq.has(k) && bReq.has(k));
    return { type: "object", properties, required, confidence: "inferred", note };
  }

  if (Node.isConditionalExpression(expr)) {
    // `cond ? {a} : {}` (e.g. the login route's conditional `token` field) — merge both
    // branches instead of falling back to the union type, which loses object shape entirely.
    const whenTrue = schemaFromExpression(expr.getWhenTrue(), ctx, depth + 1);
    const whenFalse = schemaFromExpression(expr.getWhenFalse(), ctx, depth + 1);
    const merged = mergeBranches(whenTrue, whenFalse, "merged from a conditional expression's two branches");
    if (merged) return merged;
    return schemaFromType(expr.getType(), ctx, depth);
  }

  if (Node.isBinaryExpression(expr)) {
    const op = expr.getOperatorToken().getText();
    if (op === "||" || op === "??") {
      const left = schemaFromExpression(expr.getLeft(), ctx, depth + 1);
      const right = schemaFromExpression(expr.getRight(), ctx, depth + 1);
      const merged = mergeBranches(left, right, `merged from both sides of a \`${op}\` fallback`);
      if (merged) return merged;
    }
    return schemaFromType(expr.getType(), ctx, depth);
  }

  if (Node.isIdentifier(expr)) {
    // Prefer a local const's own initializer expression over its declared type — a type
    // annotation (e.g. `Record<string, unknown>`) or a `.map()`/ternary/`||` chain often
    // widens or blurs what the checker reports, losing shape our literal-aware walk can keep.
    const symbol = expr.getSymbol();
    if (symbol) {
      for (const decl of symbol.getDeclarations()) {
        if (Node.isVariableDeclaration(decl)) {
          const init = decl.getInitializer();
          if (init) return schemaFromExpression(init, ctx, depth + 1);
        }
      }
    }
    return schemaFromType(expr.getType(), ctx, depth);
  }

  if (
    Node.isPropertyAccessExpression(expr) ||
    Node.isElementAccessExpression(expr) ||
    Node.isAsExpression(expr) ||
    Node.isPrefixUnaryExpression(expr) // e.g. `!!userRecord.isAdmin` -> boolean, via the checker
  ) {
    return schemaFromType(expr.getType(), ctx, depth);
  }

  return { type: "unknown", confidence: "unknown" };
}

function responseHitToInfo(hit: RawResponseHit, ctx: AnalysisContext): ResponseInfo {
  switch (hit.finalMethod) {
    case "json":
      return {
        status: hit.statusCode,
        contentType: "application/json",
        schema: hit.finalArgs[0] ? schemaFromExpression(hit.finalArgs[0], ctx, 0) : { type: "null", confidence: "handler-literal" },
      };
    case "send": {
      const arg = hit.finalArgs[0];
      if (!arg) return { status: hit.statusCode, contentType: null };
      if (Node.isStringLiteral(arg) || Node.isNoSubstitutionTemplateLiteral(arg) || Node.isTemplateExpression(arg)) {
        return { status: hit.statusCode, contentType: "text/html", schema: { type: "string", confidence: "handler-literal" } };
      }
      return {
        status: hit.statusCode,
        contentType: "application/octet-stream",
        schema: { type: "string", format: "binary", confidence: "inferred" },
      };
    }
    case "sendStatus":
      return { status: hit.statusCode, contentType: null };
    case "redirect":
      return { status: hit.statusCode, contentType: null, headers: ["Location"] };
    case "sendFile":
    case "download":
      return {
        status: 200,
        contentType: "application/octet-stream",
        schema: { type: "string", format: "binary", confidence: "inferred" },
      };
    case "writeHead":
    case "write":
    case "end": {
      const isSse = hit.writeHeadContentType?.includes("event-stream") ?? false;
      return {
        status: hit.statusCode,
        contentType: hit.writeHeadContentType ?? "application/octet-stream",
        ...(isSse ? { description: "Server-Sent Events stream; individual event payloads are not modeled." } : {}),
      };
    }
    default:
      return {
        status: hit.statusCode,
        contentType: null,
        description: `res.${hit.finalMethod}(...) — not modeled by the generator`,
      };
  }
}

function schemaKey(s: SchemaNode | undefined): string {
  if (!s) return "";
  // Cheap structural fingerprint: good enough to dedupe identical shapes without a full
  // deep-equality pass, and stable regardless of property insertion order.
  return JSON.stringify(s, Object.keys(s).sort());
}

/**
 * Groups response hits by (status, contentType). Distinct schemas at the same key are kept
 * as `oneOf` variants rather than one overwriting the other — e.g. `/users/login`'s 200
 * response has two unrelated shapes (pending-TOTP vs. full login) depending on account state,
 * and collapsing them to a single "winner" would silently document only one.
 */
function mergeResponses(hits: ResponseInfo[]): ResponseInfo[] {
  const byKey = new Map<string, ResponseInfo & { variants: Map<string, SchemaNode> }>();
  for (const r of hits) {
    const key = `${r.status}:${r.contentType ?? ""}`;
    let entry = byKey.get(key);
    if (!entry) {
      entry = { ...r, variants: new Map() };
      byKey.set(key, entry);
    }
    if (r.schema) entry.variants.set(schemaKey(r.schema), r.schema);
    if (r.headers) entry.headers = [...new Set([...(entry.headers ?? []), ...r.headers])];
    if (r.description && !entry.description) entry.description = r.description;
  }
  const out: ResponseInfo[] = [];
  for (const entry of byKey.values()) {
    const variants = [...entry.variants.values()];
    const { variants: _drop, ...rest } = entry;
    void _drop;
    if (variants.length <= 1) {
      out.push({ ...rest, schema: variants[0] });
    } else {
      out.push({ ...rest, schema: { type: "unknown", confidence: "handler-literal", oneOf: variants } });
    }
  }
  return out.sort((a, b) => {
    const as = a.status === "default" ? 999 : a.status;
    const bs = b.status === "default" ? 999 : b.status;
    return as - bs;
  });
}

// ---- request body ----

/**
 * Best-effort field typing from validator/coercion call sites, scanned as text over the
 * handler's own source rather than full control-flow analysis (see Phase 3 in the design doc).
 * Checked in priority order and the FIRST match wins — unlike a boolean-coercion (`!!x`)
 * rule tried earlier, later/weaker signals must never overwrite an earlier explicit one
 * (e.g. `isNonEmptyString(username)` must not be clobbered by an unrelated `!!username`
 * inside the same function's logging call, which is a real, confirmed false positive).
 */
/**
 * E5 (docs/spec-generation-strategy-v2.md): field is serialized before storage (`JSON.
 * stringify(x)` into a Drizzle `text` column, or `JSON.parse(x)` reading one back). Doesn't
 * give a concrete type on its own — a serialized value is fine as `object` or `array` — but
 * E2 needs to know a field is serialized so it doesn't naively inherit `string` from the
 * `text` column that stores it. Recorded as a note on the field rather than a separate
 * boolean so it survives the same way every other weak signal does.
 */
const STRUCTURED_FIELD_NOTE = "value is JSON-serialized into a `text` column before storage; shape not enumerated";

function fieldTypeFromValidators(
  fieldName: string,
  fnText: string,
): { type: SchemaNode["type"]; required: boolean; enumValues?: string[]; note?: string } {
  const esc = fieldName.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  let required = false;
  let type: SchemaNode["type"] = "unknown";
  let note: string | undefined;

  const enumMatch = new RegExp(`\\[([^\\]]*)\\]\\.includes\\(\\s*${esc}\\b`).exec(fnText);
  let enumValues = enumMatch
    ? enumMatch[1]
        .split(",")
        .map((s) => s.trim().replace(/^["']|["']$/g, ""))
        .filter(Boolean)
    : undefined;

  if (enumValues && enumValues.length > 0) {
    type = "string";
  } else if (new RegExp(`isNonEmptyString\\(\\s*${esc}\\b`).test(fnText)) {
    type = "string";
  } else if (
    new RegExp(`typeof\\s+${esc}\\s*!==?\\s*["']number["']`).test(fnText) ||
    new RegExp(`typeof\\s+${esc}\\s*===?\\s*["']number["']`).test(fnText)
  ) {
    type = "number";
  } else if (new RegExp(`Array\\.isArray\\(\\s*${esc}\\b`).test(fnText)) {
    type = "array";
  } else if (new RegExp(`\\b(Number|parseInt)\\(\\s*${esc}\\b`).test(fnText)) {
    type = "integer";
    // E5: patterns below are only tried once the pre-existing ones above found nothing —
    // never allowed to override a signal that already worked before this plan.
  } else if (
    new RegExp(`typeof\\s+${esc}\\s*!==?\\s*["']string["']`).test(fnText) ||
    new RegExp(`typeof\\s+${esc}\\s*===?\\s*["']string["']`).test(fnText)
  ) {
    type = "string";
  } else if (new RegExp(`\\b${esc}\\s*\\?\\s*1\\s*:\\s*0\\b`).test(fnText)) {
    // Confirmed real case: host.ts's create-host handler coerces every boolean flag this way
    // (`useWarpgate ? 1 : 0`) into an `integer` Drizzle column that has no `mode: "boolean"` —
    // the API-facing type is still boolean regardless of how the column stores it.
    type = "boolean";
  } else if (new RegExp(`\\b${esc}\\s*\\?\\s*["']true["']\\s*:\\s*["']false["']`).test(fnText)) {
    // Same idiom, into a `text` column instead of an `integer` one — confirmed real case:
    // `forceKeyboardInteractive ? "true" : "false"` in host.ts, `enabled ? "true" : "false"`
    // in user-settings-routes.ts. Without this, E2 would later match the `text` column and
    // report `string`, which is wrong on the wire even though it's exactly how the column
    // stores it.
    type = "boolean";
  } else if (new RegExp(`typeof\\s+${esc}\\s*!==?\\s*["']boolean["']`).test(fnText)) {
    type = "boolean";
  } else if (new RegExp(`\\b${esc}\\s*[!=]==?\\s*(true|false)\\b`).test(fnText)) {
    // `enableTerminalToolbar === false ? 0 : 1` — same int-as-boolean idiom as above, just
    // with the comparison spelled out instead of using the field as a bare truthy condition.
    type = "boolean";
  } else if (new RegExp(`typeof\\s+${esc}\\s*!==?\\s*["']object["']`).test(fnText)) {
    type = "object";
  } else if (new RegExp(`JSON\\.parse\\(\\s*${esc}\\b`).test(fnText)) {
    // The handler parses this field as JSON — so on the wire (what the API accepts) it's a
    // string, whatever shape the parsed result takes.
    type = "string";
  } else {
    // No `.includes()` enum and no other signal yet — a plain `x === "literal"` chain (e.g.
    // `type !== "webhook" && type !== "ntfy" && type !== "discord"`) is the same enum shape
    // `fieldTypeFromValidators` already recognizes via `.includes()`, just spelled out with
    // separate comparisons instead. Collect every distinct string literal compared against
    // this field; two or more is enough to be confident it's an enum, not a stray one-off check.
    const literalMatches = [...fnText.matchAll(new RegExp(`\\b${esc}\\s*[!=]==?\\s*["']([^"']*)["']`, "g"))];
    const literals = [...new Set(literalMatches.map((m) => m[1]))];
    if (literals.length >= 2) {
      type = "string";
      enumValues = literals;
    } else if (new RegExp(`JSON\\.stringify\\(\\s*${esc}\\b`).test(fnText)) {
      note = STRUCTURED_FIELD_NOTE;
    }
  }

  if (
    new RegExp(`isNonEmptyString\\(\\s*${esc}\\b`).test(fnText) ||
    new RegExp(`Array\\.isArray\\(\\s*${esc}\\b`).test(fnText) ||
    new RegExp(`if\\s*\\(\\s*!${esc}\\s*\\)`).test(fnText)
  ) {
    required = true;
  }

  return { type, required, enumValues, note };
}

/** Peels parentheses, `as X` casts and `?? {}` / `|| {}` defensive fallbacks down to the real
 *  expression. */
function unwrapBodyExpr(n: Node): Node {
  let e = n;
  while (true) {
    if (Node.isParenthesizedExpression(e)) {
      // `(req.body as Record<string, unknown> | undefined)?.logout_token` — the parentheses a
      // cast needs before a property access were hiding the body from the `.x` pass below.
      e = e.getExpression();
      continue;
    }
    if (Node.isAsExpression(e)) {
      e = e.getExpression();
      continue;
    }
    // `req.body ?? {}` / `req.body || {}` — a defensive fallback, still req.body underneath.
    // Confirmed real case: POST /automations destructures exactly this way and was silently
    // dropping all 5 of its body fields before this was added.
    if (Node.isBinaryExpression(e) && (e.getOperatorToken().getText() === "??" || e.getOperatorToken().getText() === "||")) {
      e = e.getLeft();
      continue;
    }
    break;
  }
  return e;
}

function isReqBodyExpr(n: Node): boolean {
  const e = unwrapBodyExpr(n);
  return Node.isPropertyAccessExpression(e) && e.getExpression().getText() === "req" && e.getName() === "body";
}

interface DeclaredField {
  schema: SchemaNode;
  required: boolean;
  /** Confidence to stamp when this declaration is what ends up typing the field. Defaults to
   *  "handler-literal" (E0's own `req.body as {...}` cast); E6 supplies its own. */
  confidence?: Confidence;
  /** Note to stamp alongside it, same defaulting rule as `confidence`. */
  note?: string;
}

/**
 * E0 (docs/spec-generation-strategy-v2.md): `req.body as { name: string; enabled?: boolean }`
 * or `req.body as Partial<{...}>` is the handler telling us the body's shape directly — no
 * weaker a signal than an explicit validator call, just a different one. `initExpr` is a
 * variable declaration's initializer (or an assignment's right-hand side); returns the
 * per-field schema map when it resolves to `req.body` cast to an inline object type, `null`
 * otherwise (e.g. no cast, or cast to a named type/interface — out of scope for E0, that's E3).
 */
/** Peels only `?? {}` / `|| {}` defensive fallbacks — unlike unwrapBodyExpr, keeps an `as` cast
 *  intact, since extractDeclaredBodyFieldTypes needs that cast's own type node. */
function peelDefensiveFallback(n: Node): Node {
  let e = n;
  while (Node.isBinaryExpression(e) && (e.getOperatorToken().getText() === "??" || e.getOperatorToken().getText() === "||")) {
    e = e.getLeft();
  }
  return e;
}

function extractDeclaredBodyFieldTypes(initExpr: Node, ctx: AnalysisContext): Map<string, DeclaredField> | null {
  const inner = peelDefensiveFallback(initExpr);
  if (!Node.isAsExpression(inner)) return null;
  const castedInner = peelDefensiveFallback(inner.getExpression());
  const isBody = Node.isPropertyAccessExpression(castedInner) && castedInner.getExpression().getText() === "req" && castedInner.getName() === "body";
  if (!isBody) return null;
  // Only an inline object type (`{...}` or `Partial<{...}>`) is in scope for E0 — a cast to a
  // named interface/type alias is E3's job (matching by name against src/types), not this one.
  const typeNode = inner.getTypeNode();
  const isPartialOfInline =
    typeNode &&
    Node.isTypeReference(typeNode) &&
    typeNode.getTypeName().getText() === "Partial" &&
    Node.isTypeLiteral(typeNode.getTypeArguments()[0]);
  if (!typeNode || !(Node.isTypeLiteral(typeNode) || isPartialOfInline)) return null;

  // Resolve through the type checker (`inner.getType()`) rather than walking the TypeLiteral's
  // own AST members by hand — schemaFromType's existing object-type branch already does
  // exactly what's needed (per-property optionality, nested objects/arrays/enums), so this
  // reuses it instead of re-implementing object-shape parsing at the AST level. Confirmed:
  // a `hostId: number | null` field comes back as plain `number`, with no `nullable` on
  // either path — Termix's tsconfig.node.json has `strictNullChecks: false`, so `T | null`
  // collapses to `T` before the checker ever represents it as a union at all. Not fixable
  // here; the field's non-null type is still correct, `nullable` just can't be recovered.
  const schema = schemaFromType(inner.getType(), ctx, 0, "handler-literal");
  if (schema.type !== "object" || !schema.properties) return null;
  const requiredNames = new Set(schema.required ?? []);
  const out = new Map<string, DeclaredField>();
  for (const [name, propSchema] of Object.entries(schema.properties)) {
    out.set(name, { schema: propSchema, required: requiredNames.has(name) });
  }
  return out.size > 0 ? out : null;
}

/** True for an argument that *is* the request body: `req.body` itself, or an identifier the
 *  handler assigned `req.body` to. `{ ...req.body }` and friends are deliberately excluded —
 *  only a whole-body forward tells us the parameter's type is the body's type. */
function isForwardedBodyArg(arg: Node, bodyAliases: Set<string>): boolean {
  if (isReqBodyExpr(arg)) return true;
  const inner = unwrapBodyExpr(arg);
  return Node.isIdentifier(inner) && bodyAliases.has(inner.getText());
}

/** Last segment of a callee expression: `createCurrentSnippetRepository().updateSnippet` -> `updateSnippet`. */
function calleeDisplayName(call: Node): string {
  const callee = (call as import("ts-morph").CallExpression).getExpression();
  return Node.isPropertyAccessExpression(callee) ? callee.getName() : callee.getText();
}

/**
 * E6: the handler never destructures the body and never casts it — it just forwards the whole
 * thing to something else (`const updateData = req.body; ... repo.updateSnippet(userId, id,
 * updateData)`). E0-E5 all come up empty on that shape, and so does E4 when the frontend
 * client types its own argument as `Record<string, unknown>` — which is exactly how
 * `PUT /snippets/{id}` ended up in the spec with no requestBody at all, making the whole
 * operation unusable from a generated SDK.
 *
 * The callee's own parameter type is the missing signal, and it's a real dataflow edge rather
 * than a name match: whatever `updateSnippet(userId, snippetId, input: SnippetUpdateInput)`
 * declares its third parameter to be IS the body's shape, as checked by tsc on every build.
 *
 * Deliberately narrow: only fires when nothing else found a single field, only for a single
 * (non-overloaded) call signature, and only when the parameter resolves to an object type
 * that actually has named properties — a parameter typed `unknown`/`any`/`Record<string,
 * unknown>` (PUT /snippets/reorder's `extractSnippetReorderUpdates(body: unknown)`) yields
 * nothing and is skipped, same as before.
 */
function forwardedBodyDeclaredFields(
  fnNode: Node,
  bodyAliases: Set<string>,
  ctx: AnalysisContext,
): Map<string, DeclaredField> | null {
  for (const call of fnNode.getDescendantsOfKind(SyntaxKind.CallExpression)) {
    const argIndex = call.getArguments().findIndex((a) => isForwardedBodyArg(a, bodyAliases));
    if (argIndex < 0) continue;

    // An overloaded callee would mean picking one signature's parameter over another's; that's
    // a guess, and this whole module's rule is to leave a field alone rather than guess at it.
    const signatures = call.getExpression().getType().getCallSignatures();
    if (signatures.length !== 1) continue;
    const param = signatures[0].getParameters()[argIndex];
    if (!param) continue;
    const decl = param.getValueDeclaration() ?? param.getDeclarations()[0];
    if (!decl || !Node.isParameterDeclaration(decl) || decl.isRestParameter()) continue;

    // A repository's own input interface is the same class of signal as its return type
    // (both are the Drizzle-backed layer's declared TS types); anything else is a plain
    // type match, no stronger than E2/E3.
    const fromRepository = decl.getSourceFile().getFilePath().includes("/repositories/");
    const conf: Confidence = fromRepository ? "repository-type" : "matched-type";
    const paramType = param.getTypeAtLocation(decl);
    const schema = schemaFromType(paramType, ctx, 0, conf);
    if (schema.type !== "object" || !schema.properties) continue;
    const names = Object.keys(schema.properties);
    if (names.length === 0) continue;

    // The annotation as written (`Partial<AiProviderUpdate>`) rather than the checker's own
    // name for it (just `Partial`), falling back to the symbol when the parameter is only
    // typed by inference. An inline object literal type is skipped — it can be pages long,
    // and the fields it declares are already right there in the schema.
    const annotation = decl.getTypeNode()?.getText();
    const symbolName = (paramType.getAliasSymbol() ?? paramType.getSymbol())?.getName();
    const typeName =
      annotation && annotation.length <= 60 && !annotation.includes("{")
        ? annotation
        : symbolName && symbolName !== "__type"
          ? symbolName
          : null;
    const note =
      `body forwarded whole to \`${calleeDisplayName(call)}()\`; typed by its ` +
      `\`${param.getName()}${typeName ? `: ${typeName}` : ""}\` parameter`;
    const requiredNames = new Set(schema.required ?? []);
    const out = new Map<string, DeclaredField>();
    for (const name of names) {
      out.set(name, { schema: schema.properties[name], required: requiredNames.has(name), confidence: conf, note });
    }
    return out;
  }
  return null;
}

/**
 * E7: unlike E6 (whole body forwarded, nothing else in the handler touches it), a route can
 * destructure some fields directly off req.body AND separately forward the whole body into a
 * locally-defined helper that itself reads exactly one property off it and returns that
 * property's validated value (or null/undefined when validation fails) — confirmed real case:
 * all four `/rbac/*\/share` routes destructure `durationHours`/`permissionLevel` directly but
 * get `targets` — the one field that actually names who a share goes to — only via `const
 * targets = parseShareTargets(req.body ?? {})`, which reads `body.targets` from inside its own
 * function body. E6's own gate (`fields.size === 0`) means it never even looks once another
 * field was already found this way, so this runs unconditionally instead and only ever adds a
 * field name neither the passes above nor an earlier E7 match in the same handler found yet —
 * it can never overwrite one.
 *
 * The signal: the callee's own return type, with `| null`/`| undefined` stripped, is what a
 * "read one field, validate it, return the validated value or null" helper's plucked-out field
 * actually is — the same class of real dataflow edge E6 already trusts (a callee's declared
 * type, checked by tsc on every build), just read off the *return* side instead of the
 * *parameter* side. Deliberately narrow: skipped when the callee reads more than one property
 * off its body parameter (ambiguous — which field does the return type belong to?) or when the
 * callee isn't a single, locally-resolvable, non-overloaded function.
 */
function forwardedBodySingleFieldsFromHelperReturns(
  fnNode: Node,
  bodyAliases: Set<string>,
  existingFieldNames: Set<string>,
  ctx: AnalysisContext,
): Map<string, DeclaredField> {
  const out = new Map<string, DeclaredField>();
  for (const call of fnNode.getDescendantsOfKind(SyntaxKind.CallExpression)) {
    const argIndex = call.getArguments().findIndex((a) => isForwardedBodyArg(a, bodyAliases));
    if (argIndex < 0) continue;

    const callee = call.getExpression();
    if (!Node.isIdentifier(callee)) continue;
    const calleeFn = resolveFunctionNode(callee);
    if (!calleeFn) continue;
    const params = getFunctionParams(calleeFn);
    const paramName = params[argIndex]?.getName();
    if (!paramName) continue;

    const propNames = new Set<string>();
    for (const pae of calleeFn.getDescendantsOfKind(SyntaxKind.PropertyAccessExpression)) {
      const obj = pae.getExpression();
      if (Node.isIdentifier(obj) && obj.getText() === paramName) propNames.add(pae.getName());
    }
    if (propNames.size !== 1) continue;
    const [fieldName] = [...propNames];
    if (existingFieldNames.has(fieldName) || out.has(fieldName)) continue;

    const signatures = call.getExpression().getType().getCallSignatures();
    if (signatures.length !== 1) continue;
    const returnType = signatures[0].getReturnType();
    const schema = schemaFromType(returnType, ctx, 0, "matched-type");
    if (!schema.type || schema.type === "unknown") continue;

    out.set(fieldName, {
      schema,
      required: false,
      confidence: "matched-type",
      note:
        `body forwarded whole to \`${callee.getText()}()\`, which reads \`body.${fieldName}\` and ` +
        `returns its validated value (or null/undefined on failure); typed from that return type`,
    });
  }
  return out;
}

function extractBodyFields(
  fnNode: Node,
  ctx: AnalysisContext,
): { name: string; default?: SchemaNode["default"]; declared?: DeclaredField }[] {
  const fields = new Map<string, { name: string; default?: SchemaNode["default"]; declared?: DeclaredField }>();
  const bodyAliases = new Set<string>();
  // Field name -> declared schema, collected from every `req.body as {...}` cast seen in this
  // handler (direct or through an alias). In this codebase a handler never casts req.body to
  // an inline object type more than once, so a flat map (not one per alias) is enough.
  const declaredTypes = new Map<string, DeclaredField>();

  for (const varDecl of fnNode.getDescendantsOfKind(SyntaxKind.VariableDeclaration)) {
    const init = varDecl.getInitializer();
    if (!init) continue;
    const nameNode = varDecl.getNameNode();
    if (isReqBodyExpr(init)) {
      const declared = extractDeclaredBodyFieldTypes(init, ctx);
      if (declared) for (const [name, field] of declared) declaredTypes.set(name, field);
      if (!Node.isObjectBindingPattern(nameNode)) bodyAliases.add(varDecl.getName());
    }
  }
  // Also catch the common `let body: T; if (...) { body = req.body; } else { ... }` idiom,
  // e.g. host.ts's create-host handler picks req.body vs. a multipart-parsed object this way —
  // a plain assignment, not a VariableDeclaration initializer.
  for (const bin of fnNode.getDescendantsOfKind(SyntaxKind.BinaryExpression)) {
    if (bin.getOperatorToken().getText() !== "=") continue;
    const left = bin.getLeft();
    const right = bin.getRight();
    if (Node.isIdentifier(left) && isReqBodyExpr(right)) bodyAliases.add(left.getText());
  }

  for (const varDecl of fnNode.getDescendantsOfKind(SyntaxKind.VariableDeclaration)) {
    const init = varDecl.getInitializer();
    if (!init) continue;
    const nameNode = varDecl.getNameNode();
    if (!Node.isObjectBindingPattern(nameNode)) continue;
    const initIsBody = isReqBodyExpr(init) || (Node.isIdentifier(init) && bodyAliases.has(init.getText()));
    if (!initIsBody) continue;
    for (const el of nameNode.getElements()) {
      if (el.getKind() !== SyntaxKind.BindingElement) continue;
      const propName = el.getPropertyNameNode()?.getText() ?? el.getName();
      const defaultInit = el.getInitializer();
      let def: SchemaNode["default"];
      if (defaultInit) {
        if (defaultInit.getKind() === SyntaxKind.TrueKeyword) def = true;
        else if (defaultInit.getKind() === SyntaxKind.FalseKeyword) def = false;
        else if (Node.isNumericLiteral(defaultInit)) def = Number(defaultInit.getText());
        else if (Node.isStringLiteral(defaultInit)) def = defaultInit.getLiteralText();
      }
      fields.set(propName, { name: propName, default: def });
    }
  }

  for (const pae of fnNode.getDescendantsOfKind(SyntaxKind.PropertyAccessExpression)) {
    const obj = unwrapBodyExpr(pae.getExpression());
    const isDirect = isReqBodyExpr(obj);
    const isAliased = Node.isIdentifier(obj) && bodyAliases.has(obj.getText());
    if (isDirect || isAliased) {
      const name = pae.getName();
      if (!fields.has(name)) fields.set(name, { name });
    }
  }

  // Confirmed real case: PATCH /open-tabs/:id casts `req.body as Partial<{...}>` into a plain
  // identifier that's never destructured or `.x`-accessed — it's forwarded whole to a
  // repository call. Neither pass above finds a single field. When that happens and we do
  // have a declared type, its own properties ARE the field list.
  if (fields.size === 0 && declaredTypes.size > 0) {
    for (const [name, declared] of declaredTypes) fields.set(name, { name, declared });
  }

  // E6: same "forwarded whole, never touched" shape as above, minus the cast that made the
  // declared type available — so the type has to come from the callee's own parameter instead.
  if (fields.size === 0) {
    const forwarded = forwardedBodyDeclaredFields(fnNode, bodyAliases, ctx);
    if (forwarded) for (const [name, declared] of forwarded) fields.set(name, { name, declared });
  }

  // E7: on top of everything above (not gated on emptiness — see its own doc), a field read
  // out of the body by a locally-defined single-property helper, alongside whatever fields
  // were already found directly.
  for (const [name, declared] of forwardedBodySingleFieldsFromHelperReturns(fnNode, bodyAliases, new Set(fields.keys()), ctx)) {
    fields.set(name, { name, declared });
  }

  for (const field of fields.values()) {
    if (!field.declared) field.declared = declaredTypes.get(field.name);
  }

  return [...fields.values()];
}

/**
 * E1 (docs/spec-generation-strategy-v2.md): when nothing else signals a field's type, the
 * type of its own destructuring default (`{ enabled = false }`) is the code itself saying
 * what the field is — no risk of false positive, just rarely present (9 fields at
 * release-2.7.1-tag). Only called when `fieldTypeFromValidators` came up empty.
 */
function typeFromDefaultLiteral(def: SchemaNode["default"]): JsonPrimitive | "boolean" | undefined {
  switch (typeof def) {
    case "boolean":
      return "boolean";
    case "number":
      return "number";
    case "string":
      return "string";
    default:
      return undefined;
  }
}

/**
 * E2 step 2 (docs/spec-generation-strategy-v2.md): which `createCurrentXRepository()`
 * factories does this handler itself call? Scoped to the handler's own function body, not
 * the whole file's imports — `host.ts` alone imports 14 different factories, `delete-user-
 * data.ts` imports 39, so a file-wide match would blow the collision guard below wide open.
 */
function calledRepositoryFactories(fnNode: Node, ctx: AnalysisContext): string[] {
  const out: string[] = [];
  for (const call of fnNode.getDescendantsOfKind(SyntaxKind.CallExpression)) {
    const callee = call.getExpression();
    if (Node.isIdentifier(callee) && ctx.repositoryTables.has(callee.getText())) out.push(callee.getText());
  }
  return out;
}

/**
 * E2 step 3: match `fieldName` against a column of a table the handler's own called
 * factories resolved to. Primary tables (the one each repository "owns") are tried before
 * any secondary table, and a name that resolves to conflicting column types within the same
 * tier is left alone rather than guessed — this is deliberately scoped to just the 1-3 tables
 * a single handler's own repository calls touch, not a global search across all 72 tables,
 * which is what keeps common column names (`name`, `id`, `enabled`) from colliding.
 */
function columnTypeFromCalledRepositories(
  fieldName: string,
  calledFactories: string[],
  ctx: AnalysisContext,
): { jsonType: SchemaNode["type"]; nullable: boolean; tableName: string } | null {
  const primaries: TableSchema[] = [];
  const secondaries: TableSchema[] = [];
  for (const factoryName of calledFactories) {
    const rt = ctx.repositoryTables.get(factoryName);
    if (!rt) continue;
    if (rt.primary) primaries.push(rt.primary);
    secondaries.push(...rt.secondary);
  }
  for (const tier of [primaries, secondaries]) {
    const matches = tier.flatMap((table) => {
      const col = table.columns.find((c) => c.tsName === fieldName);
      return col ? [{ table, col }] : [];
    });
    if (matches.length === 0) continue;
    const distinctTypes = new Set(matches.map((m) => m.col.jsonType));
    if (distinctTypes.size > 1) return null; // conflicting types within the same tier — don't guess
    const { table, col } = matches[0];
    return { jsonType: col.jsonType, nullable: col.nullable, tableName: table.dbTableName };
  }
  return null;
}

/**
 * E3 (docs/spec-generation-strategy-v2.md): a route's whole destructured field set (not just
 * the still-unknown ones — overlap only means something measured against everything the
 * route actually asked for) is compared against every src/types/index.ts interface. Needs
 * >=5 fields and >=70% overlap, per the plan's mitigation against a small, generic route
 * (`name`/`description`/`enabled`) coincidentally matching the wrong interface; picks the
 * single highest-overlap interface rather than trying more than one.
 */
function findBestTypeInterfaceMatch(fieldNames: Set<string>, typeInterfaces: TypeInterfaceEntry[]): TypeInterfaceEntry | null {
  if (fieldNames.size < 5) return null;
  let best: TypeInterfaceEntry | null = null;
  let bestRatio = 0;
  for (const iface of typeInterfaces) {
    const overlap = [...fieldNames].filter((n) => iface.fields.has(n)).length;
    const ratio = overlap / fieldNames.size;
    if (ratio >= 0.7 && ratio > bestRatio) {
      best = iface;
      bestRatio = ratio;
    }
  }
  return best;
}

function analyzeRequestBody(fnNode: Node, fnText: string, middlewares: string[], ctx: AnalysisContext): RequestBodyVariant[] {
  const fields = extractBodyFields(fnNode, ctx);

  const uploadMiddleware = middlewares.find((m) => /^upload\.single\(/.test(m));
  const uploadFileField = uploadMiddleware
    ? (/^upload\.single\(\s*["']([^"']+)["']\s*\)/.exec(uploadMiddleware)?.[1] ?? "file")
    : null;
  const streamed = /\bBusboy\(/.test(fnText) || /req\.pipe\(/.test(fnText);

  // No JSON field anywhere doesn't mean no body: an `upload.single("file")` route accepts a
  // multipart file whether or not its handler ever reads a text field beside it (POST
  // /database/import reads only `req.file`), and a busboy/`req.pipe` route consumes the raw
  // stream by definition. Returning [] for those emitted a write operation with no
  // requestBody at all — an SDK generated from it can't send the upload the route exists for.
  if (fields.length === 0) {
    if (uploadFileField) {
      return [
        {
          contentType: "multipart/form-data",
          schema: {
            type: "object",
            properties: { [uploadFileField]: { type: "string", format: "binary", confidence: "inferred" } },
            required: [uploadFileField],
            confidence: "inferred",
          },
        },
      ];
    }
    if (streamed) {
      return [{ contentType: "multipart/form-data", schema: { type: "object", confidence: "unknown", note: "parsed via busboy/stream; fields not enumerated" } }];
    }
    return [];
  }

  const calledFactories = calledRepositoryFactories(fnNode, ctx);
  const typeMatch = findBestTypeInterfaceMatch(new Set(fields.map((f) => f.name)), ctx.typeInterfaces);
  const properties: Record<string, SchemaNode> = {};
  const required: string[] = [];
  for (const f of fields) {
    let { type, required: req, enumValues, note: validatorNote } = fieldTypeFromValidators(f.name, fnText);
    let confidence: Confidence = type === "unknown" ? "unknown" : "inferred";
    let nullable: boolean | undefined;
    let note: string | undefined = validatorNote;
    // True once the declared type (E0's cast or E6's callee parameter) is what typed this
    // field — which is also what makes that declaration's own optionality meaningful below.
    let typedFromDeclared = false;
    // An array/object declared type carries shape (`items`/`properties`/`required`) that the
    // scalar fields below don't capture — confirmed real case: E7's `targets` field (an array
    // of `{type, id}` objects) was coming out as a bare `array` with no `items` at all before
    // this, because nothing downstream of the `type`/`confidence`/`enumValues`/`nullable`/
    // `note` fields ever copied it over.
    let declaredStructural: Pick<SchemaNode, "items" | "properties" | "required"> | undefined;

    // E0: an explicit validator in the handler's own control flow is still the strongest
    // signal (it's what the server actually enforces at runtime) — only fall back to the
    // declared cast type when the validator pass found nothing.
    if (type === "unknown" && f.declared && f.declared.schema.type && f.declared.schema.type !== "unknown") {
      type = f.declared.schema.type;
      confidence = f.declared.confidence ?? "handler-literal";
      nullable = f.declared.schema.nullable;
      if (f.declared.schema.enumValues) enumValues = f.declared.schema.enumValues.map(String);
      note = f.declared.note ?? "declared via `req.body as {...}`";
      typedFromDeclared = true;
      if (type === "array" || type === "object") {
        declaredStructural = {
          ...(f.declared.schema.items ? { items: f.declared.schema.items } : {}),
          ...(f.declared.schema.properties ? { properties: f.declared.schema.properties } : {}),
          ...(f.declared.schema.required ? { required: f.declared.schema.required } : {}),
        };
      }
    }

    // E1: no explicit validator and no declared cast — the destructuring default's own
    // literal type is the last resort before giving up.
    if (type === "unknown" && f.default !== undefined) {
      const defaultType = typeFromDefaultLiteral(f.default);
      if (defaultType) {
        type = defaultType;
        confidence = "inferred";
        note = undefined;
      }
    }

    // E2: nothing in the handler itself signals a type — see if the field's name matches a
    // column of a table the handler's own repository calls resolve to. A `text` column is
    // not trusted for a field E5 already flagged as JSON-serialized (the column's storage
    // type is `string`; the field's real shape is whatever got serialized into it).
    if (type === "unknown" && calledFactories.length > 0) {
      const match = columnTypeFromCalledRepositories(f.name, calledFactories, ctx);
      if (match && !(note === STRUCTURED_FIELD_NOTE && match.jsonType === "string")) {
        type = match.jsonType;
        confidence = "matched-type";
        if (match.nullable) nullable = true;
        note = `matched column \`${match.tableName}.${f.name}\``;
      }
    }

    // E3: still nothing, and this field isn't a Drizzle column either — try src/types/
    // index.ts's own interfaces. This is where string enums like `authType` live, since
    // they never appear in a handler validator and the backing column is just `text`.
    if (type === "unknown" && typeMatch) {
      const matchedProp = typeMatch.properties.get(f.name);
      if (matchedProp && matchedProp.type && matchedProp.type !== "unknown" && !(note === STRUCTURED_FIELD_NOTE && matchedProp.type === "string")) {
        type = matchedProp.type;
        confidence = "matched-type";
        if (matchedProp.enumValues) enumValues = matchedProp.enumValues.map(String);
        if (matchedProp.nullable) nullable = true;
        note = `matched \`src/types/index.ts\`'s \`${typeMatch.name}\` interface`;
      }
    }

    properties[f.name] = {
      type,
      confidence,
      ...(f.default !== undefined ? { default: f.default } : {}),
      ...(enumValues && enumValues.length > 0 ? { enumValues } : {}),
      ...(nullable ? { nullable } : {}),
      ...(note ? { note } : {}),
      ...(declaredStructural ?? {}),
    };
    if (req || f.default !== undefined || (f.declared?.required && typedFromDeclared)) required.push(f.name);
  }
  const schema: SchemaNode = { type: "object", properties, required, confidence: "inferred" };

  if (uploadFileField) {
    const multipartProps: Record<string, SchemaNode> = {
      ...properties,
      [uploadFileField]: { type: "string", format: "binary", confidence: "inferred" },
    };
    return [
      { contentType: "multipart/form-data", schema: { type: "object", properties: multipartProps, required, confidence: "inferred" } },
      { contentType: "application/json", schema },
    ];
  }

  if (streamed) {
    return [{ contentType: "multipart/form-data", schema: { type: "object", confidence: "unknown", note: "parsed via busboy/stream; fields not enumerated" } }];
  }

  return [{ contentType: "application/json", schema }];
}

// ---- query / path / headers ----

function analyzePathParams(routePath: string, fnText: string): PathParamInfo[] {
  const names = [...routePath.matchAll(/:([A-Za-z_][A-Za-z0-9_]*)/g)].map((m) => m[1]);
  return names.map((name) => {
    const esc = name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const numeric =
      new RegExp(`\\b(Number|parseInt)\\(\\s*req\\.params\\.${esc}\\b`).test(fnText) ||
      new RegExp(`\\b(Number|parseInt)\\(\\s*req\\.params\\[["']${esc}["']\\]`).test(fnText);
    return { name, type: numeric ? "integer" : "string" };
  });
}

function analyzeQueryParams(fnNode: Node, fnText: string): QueryParamInfo[] {
  const names = new Map<string, { default?: string | number | boolean }>();

  for (const varDecl of fnNode.getDescendantsOfKind(SyntaxKind.VariableDeclaration)) {
    const init = varDecl.getInitializer();
    const nameNode = varDecl.getNameNode();
    if (!init || !Node.isObjectBindingPattern(nameNode)) continue;
    if (!(Node.isPropertyAccessExpression(init) && init.getExpression().getText() === "req" && init.getName() === "query")) continue;
    for (const el of nameNode.getElements()) {
      if (el.getKind() !== SyntaxKind.BindingElement) continue;
      const propName = el.getPropertyNameNode()?.getText() ?? el.getName();
      const defaultInit = el.getInitializer();
      let def: string | number | boolean | undefined;
      if (defaultInit) {
        if (Node.isNumericLiteral(defaultInit)) def = Number(defaultInit.getText());
        else if (Node.isStringLiteral(defaultInit)) def = defaultInit.getLiteralText();
        else if (defaultInit.getKind() === SyntaxKind.TrueKeyword) def = true;
        else if (defaultInit.getKind() === SyntaxKind.FalseKeyword) def = false;
      }
      names.set(propName, { default: def });
    }
  }

  for (const pae of fnNode.getDescendantsOfKind(SyntaxKind.PropertyAccessExpression)) {
    const obj = pae.getExpression();
    if (Node.isPropertyAccessExpression(obj) && obj.getExpression().getText() === "req" && obj.getName() === "query") {
      if (!names.has(pae.getName())) names.set(pae.getName(), {});
    }
  }

  return [...names.entries()].map(([name, info]) => {
    const esc = name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    let type: JsonPrimitive = "string";
    if (new RegExp(`\\b(Number|parseInt)\\(\\s*req\\.query\\.${esc}\\b`).test(fnText)) type = "integer";
    else if (new RegExp(`req\\.query\\.${esc}\\s*===?\\s*["']true["']`).test(fnText)) type = "boolean";
    else if (typeof info.default === "number") type = "integer";
    else if (typeof info.default === "boolean") type = "boolean";

    const required = new RegExp(`if\\s*\\(\\s*!${esc}\\s*\\)`).test(fnText);
    return { name, type, required: required && info.default === undefined, ...(info.default !== undefined ? { default: info.default } : {}) };
  });
}

function analyzeHeaders(fnText: string): HeaderParamInfo[] {
  const names = new Set<string>();
  for (const m of fnText.matchAll(/req\.headers\[["']([^"']+)["']\]/g)) names.add(m[1]);
  for (const m of fnText.matchAll(/req\.(?:get|header)\(["']([^"']+)["']\)/g)) names.add(m[1]);
  return [...names].map((name) => ({ name }));
}

// ---- auth ----

function analyzeAuth(route: RouteRecord, service: ServiceInfo | undefined): AuthInfo {
  const mw = route.middlewares;
  const hasJWT = mw.some((m) => m === "authenticateJWT" || m.startsWith("authenticateJWT("));
  // route.line is only comparable to service.globalAuthLine when the route is registered
  // directly in the service's own root file (e.g. metrics/index.ts's one pre-auth route,
  // /internal/login-alert). Most routes on a global-auth service are reached through
  // registerXRoutes() calls defined in a different file, where route.line is a line number
  // in *that* file and comparing it to globalAuthLine (a line in the root file) is
  // meaningless. In every confirmed case in this codebase the registerXRoutes(app, ...)
  // call itself always happens after the auth middleware is installed, so routes reached
  // that way default to being covered rather than being silently misjudged as public.
  const globalCovers =
    !!service?.globalAuth &&
    service.globalAuthLine !== null &&
    (route.file !== service.file || route.line > service.globalAuthLine);
  const requiresAdmin = mw.some((m) => m === "requireAdmin" || m.startsWith("requireAdmin("));
  const requiresDataAccess = mw.some((m) => m === "requireDataAccess" || m.startsWith("requireDataAccess("));
  const required = hasJWT || globalCovers || requiresAdmin || requiresDataAccess;
  return { required, requiresAdmin, requiresDataAccess, adminImpersonation: required };
}

// ---- managerHandler() wrapper (hosts/metrics/managers/route-helpers.ts) ----
//
// 30 of the host-metrics-manager routes (cron/firewall/health/logs/packages/processes/
// services/ssl/tailscale/users/wireguard) register `managerHandler(runOnHost, level, op, fn)`
// directly as the route handler, where `managerHandler` itself returns the real
// `(req, res) => {...}` — so the per-route callback `fn` never sees `res` at all, and the
// generic "resolve to a function, scan it for res.xxx()" path above can't find anything.
// Modeled explicitly, the same way transformHostResponse/stripSensitiveFields are: read
// once from route-helpers.ts (confirmed at release-2.7.1-tag), reapplied at every call site.

function getManagerHandlerCallback(nodeIn: Node): Node | null {
  let node: Node = nodeIn;
  while (Node.isParenthesizedExpression(node)) node = node.getExpression();
  if (!Node.isCallExpression(node)) return null;
  const callee = node.getExpression();
  if (!Node.isIdentifier(callee) || callee.getText() !== "managerHandler") return null;
  const args = node.getArguments();
  const fn = args[args.length - 1];
  if (fn && (Node.isArrowFunction(fn) || Node.isFunctionExpression(fn))) return fn;
  return null;
}

/** Return statements belonging to `fn` itself, not to any function nested inside it. */
function collectOwnReturnExpressions(fn: Node): Node[] {
  const body = Node.isArrowFunction(fn) || Node.isFunctionExpression(fn) ? fn.getBody() : fn;
  if (!Node.isBlock(body)) return [body]; // concise arrow body is itself the returned expression
  const out: Node[] = [];
  for (const stmt of body.getDescendantsOfKind(SyntaxKind.ReturnStatement)) {
    const owner = stmt.getFirstAncestor(
      (a) => Node.isArrowFunction(a) || Node.isFunctionExpression(a) || Node.isFunctionDeclaration(a),
    );
    if (owner !== fn) continue;
    const e = stmt.getExpression();
    if (e) out.push(e);
  }
  return out;
}

function managerHandlerErrorResponses(): ResponseInfo[] {
  const errorObj = (extra?: Record<string, SchemaNode>): SchemaNode => ({
    type: "object",
    properties: { error: { type: "string", confidence: "handler-literal" }, ...(extra ?? {}) },
    required: ["error"],
    confidence: "handler-literal",
  });
  return [
    {
      status: 400,
      contentType: "application/json",
      schema: errorObj(),
      description: "ManagerInputError, from the managerHandler() wrapper",
    },
    {
      status: 403,
      contentType: "application/json",
      schema: errorObj({ code: { type: "string", confidence: "handler-literal" } }),
      description: "AccessDeniedError or ElevationError (code only on the latter), from the managerHandler() wrapper",
    },
    {
      status: 500,
      contentType: "application/json",
      schema: errorObj(),
      description: "Uncaught error, from the managerHandler() wrapper",
    },
  ];
}

// ---- top-level ----

export function analyzeRoute(
  route: RouteRecord,
  handlerNode: Node,
  service: ServiceInfo | undefined,
  ctx: AnalysisContext,
): RouteAnalysis {
  const auth = analyzeAuth(route, service);

  const managerCb = getManagerHandlerCallback(handlerNode);
  if (managerCb) {
    const fnText = managerCb.getText();
    const successHits: ResponseInfo[] = collectOwnReturnExpressions(managerCb).map((r) => ({
      status: 200,
      contentType: "application/json",
      schema: schemaFromExpression(r, ctx, 0),
    }));
    const responses = mergeResponses([...successHits, ...managerHandlerErrorResponses()]);
    const pathParams = analyzePathParams(route.path, fnText).map((p) =>
      p.name === "id" ? { ...p, type: "integer" as const } : p,
    );
    const requestBody = ["POST", "PUT", "PATCH"].includes(route.method)
      ? analyzeRequestBody(managerCb, fnText, route.middlewares, ctx)
      : [];
    return {
      routeId: route.id,
      auth,
      pathParams,
      queryParams: analyzeQueryParams(managerCb, fnText),
      headers: analyzeHeaders(fnText),
      requestBody,
      responses,
      opaque: false,
    };
  }

  const fn = resolveFunctionNode(handlerNode);

  if (!fn) {
    return {
      routeId: route.id,
      auth,
      pathParams: analyzePathParams(route.path, ""),
      queryParams: [],
      headers: [],
      requestBody: [],
      responses: [],
      opaque: true,
    };
  }

  const fnText = fn.getText();
  const responseParam = getFunctionParams(fn)[1]?.getName() ?? "res";

  const hits: RawResponseHit[] = [];
  collectResponseHits(fn, responseParam, 0, new Set(), hits);
  const responses = mergeResponses(hits.map((h) => responseHitToInfo(h, ctx)));

  const requestBody = ["POST", "PUT", "PATCH"].includes(route.method) ? analyzeRequestBody(fn, fnText, route.middlewares, ctx) : [];

  return {
    routeId: route.id,
    auth,
    pathParams: analyzePathParams(route.path, fnText),
    queryParams: analyzeQueryParams(fn, fnText),
    headers: analyzeHeaders(fnText),
    requestBody,
    responses,
    opaque: false,
  };
}
