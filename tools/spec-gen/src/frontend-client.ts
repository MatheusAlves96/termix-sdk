/**
 * Phase 7: cross-checks the backend analysis against the frontend HTTP client
 * (`src/ui/main-axios.ts`, `src/ui/api/*.ts`).
 *
 * The axios instances are exported as `export let xApi: AxiosInstance;` with no
 * initializer, assigned later by a plain `xApi = createApiInstance(getApiUrl(prefix,
 * PORT), "LABEL");` inside an async init function — so resolving `sshHostApi.post(...)`
 * back to a service means finding that assignment, not a variable declaration's own
 * initializer. The port literal passed to `getApiUrl` is the same number as
 * `ServiceInfo.port`, which is what makes correlating a frontend call to a specific
 * backend route reliable without ever needing to know the instance's base URL.
 *
 * See tools/spec-gen/docs/spec-generation-strategy.md, Phase 7.
 */

import { Node, Project, SyntaxKind, Type } from "ts-morph";
import type {
  Confidence,
  FrontendCallInfo,
  FrontendCrossCheck,
  HttpMethod,
  ResponseInfo,
  RouteAnalysis,
  RouteRecord,
  RoutesIR,
  SchemaNode,
} from "./types.js";
import { relFile } from "./project.js";

const HTTP_METHODS = ["get", "post", "put", "patch", "delete"] as const;

// ---- type -> schema (frontend-flavored: confidence is always "frontend-type") ----

const OPAQUE_TRANSPORT_TYPES = new Set(["FormData", "Blob", "File", "ArrayBuffer", "URLSearchParams"]);

function schemaFromFrontendType(type: Type, depth: number): SchemaNode {
  const CONF: Confidence = "frontend-type";
  const aliasSymbol = type.getAliasSymbol() ?? type.getSymbol();
  if (aliasSymbol?.getName() === "Promise") {
    const args = type.getTypeArguments();
    if (args[0]) return schemaFromFrontendType(args[0], depth);
  }
  // A FormData/Blob/etc. instance's own properties are its *methods* (append, delete, get,
  // ...) — enumerating them as if they were body fields is nonsense. These always mean the
  // request is multipart, whose real fields are `.append()`ed and invisible to static typing.
  if (aliasSymbol && OPAQUE_TRANSPORT_TYPES.has(aliasSymbol.getName())) {
    return { type: "string", format: "binary", confidence: CONF, note: `${aliasSymbol.getName()} body (multipart); fields not enumerated` };
  }
  if (type.isAny() || type.isUnknown()) return { type: "unknown", confidence: CONF };
  if (type.isNull()) return { type: "null", nullable: true, confidence: CONF };
  if (type.isUndefined() || type.isVoid()) return { type: "unknown", confidence: CONF };
  if (type.isBooleanLiteral() || type.isBoolean()) return { type: "boolean", confidence: CONF };
  if (type.isNumberLiteral() || type.isNumber()) return { type: "number", confidence: CONF };
  if (type.isStringLiteral() || type.isString()) return { type: "string", confidence: CONF };

  if (type.isUnion()) {
    const variants = type.getUnionTypes();
    const nullable = variants.some((v) => v.isUndefined() || v.isNull());
    const rest = variants.filter((v) => !v.isUndefined() && !v.isNull());
    if (rest.length === 1) {
      const inner = schemaFromFrontendType(rest[0], depth);
      return nullable ? { ...inner, nullable: true } : inner;
    }
    if (rest.length > 0 && rest.every((v) => v.isStringLiteral())) {
      return { type: "string", enumValues: rest.map((v) => String(v.getLiteralValue())), confidence: CONF, ...(nullable ? { nullable: true } : {}) };
    }
    return { type: "unknown", confidence: CONF, note: "union type, not expanded" };
  }

  if (type.isArray()) {
    return { type: "array", items: schemaFromFrontendType(type.getArrayElementTypeOrThrow(), depth + 1), confidence: CONF };
  }

  if (depth >= 3) return { type: "object", confidence: CONF, note: "object type, depth limit reached" };

  if (type.isObject()) {
    const props = type.getProperties();
    if (props.length === 0 || props.length > 80) return { type: "object", confidence: CONF };
    const properties: Record<string, SchemaNode> = {};
    const required: string[] = [];
    for (const p of props) {
      const decl = p.getValueDeclaration() ?? p.getDeclarations()[0];
      if (!decl) continue;
      properties[p.getName()] = schemaFromFrontendType(p.getTypeAtLocation(decl), depth + 1);
      if (!p.isOptional()) required.push(p.getName());
    }
    return { type: "object", properties, required, confidence: CONF };
  }

  return { type: "unknown", confidence: CONF };
}

// ---- path template -> matchable form ----

/** `/db/host/${hostId}` -> `/db/host/*`; a plain string literal is returned as-is. */
function templatePathToMatchable(exprIn: Node): string | null {
  let expr: Node = exprIn;
  while (Node.isParenthesizedExpression(expr)) expr = expr.getExpression();
  if (Node.isStringLiteral(expr) || Node.isNoSubstitutionTemplateLiteral(expr)) return expr.getLiteralText();
  if (Node.isTemplateExpression(expr)) {
    let out = expr.getHead().getLiteralText();
    for (const span of expr.getTemplateSpans()) out += "*" + span.getLiteral().getLiteralText();
    return out;
  }
  return null;
}

/** `{param}` (OpenAPI) and `:param` (Express) segments both collapse to `*` for matching. */
function normalizeForMatch(path: string): string {
  return path
    .split("/")
    .map((seg) => (/^[:{]/.test(seg) || seg === "*" ? "*" : seg))
    .join("/");
}

function displayPath(matchable: string): string {
  let i = 0;
  return matchable
    .split("/")
    .map((seg) => (seg === "*" ? `{param${++i}}` : seg))
    .join("/");
}

// ---- resolving an axios instance identifier to a service ----

interface InstanceInfo {
  port: number;
  /** e.g. "/host" for hostApi (`getApiUrl("/host", 30001)`) — baked into the instance's own
   *  baseURL, so every call's own path argument is relative to *this*, not to the route root.
   *  `sshHostApi.post("/db/host", ...)` really means `/host/db/host`. */
  prefix: string;
}

function buildInstancePortMap(mainAxiosFile: import("ts-morph").SourceFile): Map<string, InstanceInfo> {
  const out = new Map<string, InstanceInfo>();
  const aliasAssignments: { name: string; of: string }[] = [];

  for (const bin of mainAxiosFile.getDescendantsOfKind(SyntaxKind.BinaryExpression)) {
    if (bin.getOperatorToken().getText() !== "=") continue;
    const left = bin.getLeft();
    const right = bin.getRight();
    if (!Node.isIdentifier(left)) continue;

    if (Node.isCallExpression(right)) {
      const callee = right.getExpression();
      if (Node.isIdentifier(callee) && callee.getText() === "createApiInstance") {
        const urlArg = right.getArguments()[0];
        if (urlArg && Node.isCallExpression(urlArg)) {
          const urlCallee = urlArg.getExpression();
          if (Node.isIdentifier(urlCallee) && urlCallee.getText() === "getApiUrl") {
            const [prefixArg, portArg] = urlArg.getArguments();
            const prefix =
              prefixArg && (Node.isStringLiteral(prefixArg) || Node.isNoSubstitutionTemplateLiteral(prefixArg))
                ? prefixArg.getLiteralText()
                : "";
            if (portArg && Node.isNumericLiteral(portArg)) out.set(left.getText(), { port: Number(portArg.getText()), prefix });
          }
        }
      }
      continue;
    }
    // `sshHostApi = hostApi;` — a bare alias to an instance built elsewhere in this same file.
    if (Node.isIdentifier(right)) aliasAssignments.push({ name: left.getText(), of: right.getText() });
  }

  // Resolve aliases as a small fixed point (2 passes covers every chain depth seen today,
  // and a 3rd pass is cheap insurance if a future version adds one more hop).
  for (let pass = 0; pass < 3; pass++) {
    for (const { name, of } of aliasAssignments) {
      if (!out.has(name) && out.has(of)) out.set(name, out.get(of)!);
    }
  }
  return out;
}

function resolveInstanceName(identifier: Node): string | null {
  if (!Node.isIdentifier(identifier)) return null;
  const symbol = identifier.getSymbol();
  if (!symbol) return null;
  let resolved = symbol;
  for (let i = 0; i < 10; i++) {
    const aliased = resolved.getAliasedSymbol();
    if (!aliased) break;
    resolved = aliased;
  }
  return resolved.getName();
}

// ---- enclosing exported function, for naming + return type ----

function findEnclosingFunction(node: Node): { name: string; node: Node } | null {
  let cur: Node | undefined = node.getParent();
  while (cur) {
    if (Node.isFunctionDeclaration(cur)) {
      const name = cur.getName();
      if (name) return { name, node: cur };
    }
    if (Node.isVariableDeclaration(cur)) {
      const init = cur.getInitializer();
      if (init && (Node.isArrowFunction(init) || Node.isFunctionExpression(init))) {
        return { name: cur.getName(), node: init };
      }
    }
    cur = cur.getParent();
  }
  return null;
}

function transportNotesFromArgs(args: Node[]): string[] {
  const notes: string[] = [];
  for (const arg of args) {
    if (!Node.isObjectLiteralExpression(arg)) continue;
    for (const prop of arg.getProperties()) {
      if (!Node.isPropertyAssignment(prop)) continue;
      if (prop.getName() === "headers") {
        const init = prop.getInitializer();
        if (init && Node.isObjectLiteralExpression(init)) {
          for (const h of init.getProperties()) {
            if (Node.isPropertyAssignment(h) && h.getName().toLowerCase().includes("content-type")) {
              const v = h.getInitializer();
              if (v && (Node.isStringLiteral(v) || Node.isNoSubstitutionTemplateLiteral(v))) {
                notes.push(`Content-Type: ${v.getLiteralText()}`);
              }
            }
          }
        }
      }
      if (prop.getName() === "responseType") {
        const init = prop.getInitializer();
        if (init && (Node.isStringLiteral(init) || Node.isNoSubstitutionTemplateLiteral(init))) {
          notes.push(`responseType: ${init.getLiteralText()}`);
        }
      }
    }
  }
  return notes;
}

export function extractFrontendCrossChecks(
  frontendProject: Project,
  repoPath: string,
  routesIr: RoutesIR,
  analyses: RouteAnalysis[],
): FrontendCrossCheck[] {
  const mainAxios = frontendProject.getSourceFiles().find((f) => f.getFilePath().endsWith("src/ui/main-axios.ts"));
  if (!mainAxios) return [];

  const instancePortMap = buildInstancePortMap(mainAxios);
  const portToService = new Map(routesIr.services.filter((s) => s.port !== null).map((s) => [s.port as number, s.key]));

  const calls: FrontendCallInfo[] = [];

  for (const sf of frontendProject.getSourceFiles()) {
    const fileRel = relFile(repoPath, sf.getFilePath());
    if (!fileRel.startsWith("src/ui/")) continue;

    for (const call of sf.getDescendantsOfKind(SyntaxKind.CallExpression)) {
      const callee = call.getExpression();
      if (!Node.isPropertyAccessExpression(callee)) continue;
      const method = callee.getName();
      if (!(HTTP_METHODS as readonly string[]).includes(method)) continue;
      const obj = callee.getExpression();
      if (!Node.isIdentifier(obj)) continue;

      const instanceName = resolveInstanceName(obj);
      if (!instanceName || !instancePortMap.has(instanceName)) continue; // not one of our known api instances

      const args = call.getArguments();
      const pathArg = args[0];
      if (!pathArg) continue;
      const matchablePath = templatePathToMatchable(pathArg);
      if (matchablePath === null) continue;

      const instanceInfo = instancePortMap.get(instanceName)!;
      const fullPath = instanceInfo.prefix ? instanceInfo.prefix.replace(/\/$/, "") + matchablePath : matchablePath;
      const service = portToService.get(instanceInfo.port) ?? null;

      const isBodyMethod = method === "post" || method === "put" || method === "patch";
      const bodyArg = isBodyMethod ? args[1] : undefined;
      const bodyType = bodyArg ? schemaFromFrontendType(bodyArg.getType(), 0) : null;

      const enclosing = findEnclosingFunction(call);
      let returnType: SchemaNode | null = null;
      if (enclosing && (Node.isFunctionDeclaration(enclosing.node) || Node.isArrowFunction(enclosing.node) || Node.isFunctionExpression(enclosing.node))) {
        returnType = schemaFromFrontendType(enclosing.node.getReturnType(), 0);
      }

      calls.push({
        functionName: enclosing?.name ?? "(anonymous)",
        file: fileRel,
        line: call.getStartLineNumber(),
        method: method.toUpperCase() as HttpMethod,
        path: displayPath(normalizeForMatch(fullPath)),
        service,
        bodyType,
        returnType,
        transportNotes: transportNotesFromArgs(args.slice(1)),
      });
    }
  }

  // ---- correlate to routes ----

  const routesByMethod = new Map<string, RouteRecord[]>();
  for (const r of routesIr.routes) {
    if (r.anyMethod) continue;
    const key = r.method;
    const list = routesByMethod.get(key) ?? [];
    list.push(r);
    routesByMethod.set(key, list);
  }
  const analysisById = new Map(analyses.map((a) => [a.routeId, a]));

  const crossChecks: FrontendCrossCheck[] = [];
  for (const call of calls) {
    const candidates = (routesByMethod.get(call.method) ?? []).filter(
      (r) => normalizeForMatch(r.path) === normalizeForMatch(call.path),
    );
    if (candidates.length === 0) continue;
    // Prefer a same-service match when more than one route shares this normalized shape
    // (doesn't happen today — 491 routes were confirmed unique by method+path — but stay
    // correct if a future Termix version reuses the same path across two services).
    const best =
      candidates.length > 1 && call.service
        ? (candidates.find((r) => r.service === call.service) ?? candidates[0])
        : candidates[0];

    const warnings: string[] = [];
    const analysis = analysisById.get(best.id);
    if (analysis) {
      const successResponse = analysis.responses.find(
        (r): r is ResponseInfo & { status: number } => typeof r.status === "number" && r.status >= 200 && r.status < 300,
      );
      if (successResponse && (!successResponse.schema || successResponse.schema.confidence === "unknown") && call.returnType && call.returnType.type !== "unknown") {
        warnings.push("backend response schema is unknown; frontend return type is available as a fallback");
      }
      if (call.bodyType?.type === "object" && call.bodyType.properties) {
        const backendFields = new Set(
          analysis.requestBody.flatMap((v) => Object.keys(v.schema.properties ?? {})),
        );
        const frontendFields = Object.keys(call.bodyType.properties);
        if (backendFields.size > 0) {
          const missingInBackend = frontendFields.filter((f) => !backendFields.has(f));
          if (missingInBackend.length > 2) {
            warnings.push(
              `frontend body type has ${missingInBackend.length} field(s) not seen in the backend's own destructuring: ${missingInBackend.slice(0, 8).join(", ")}`,
            );
          }
        }
      }
    }

    crossChecks.push({ routeId: best.id, call, warnings });
  }

  return crossChecks;
}
