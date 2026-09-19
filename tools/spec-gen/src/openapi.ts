/**
 * Phase 9: assembles the routes IR, Drizzle IR, and per-route analyses into an
 * OpenAPI 3.1 document. See tools/spec-gen/docs/spec-generation-strategy.md, Phase 9.
 */

import type {
  ColumnSchema,
  DrizzleIR,
  FrontendCrossCheck,
  RouteAnalysis,
  RouteRecord,
  RoutesIR,
  SchemaNode,
  ServiceInfo,
  TableSchema,
  TestExample,
} from "./types.js";
import { jsdocTextKey, type JsdocRouteText } from "./jsdoc-text.js";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type JsonSchema = Record<string, any>;

function jsonTypeFor(t: ColumnSchema["jsonType"]): string {
  return t; // "string" | "integer" | "boolean" | "number" already match JSON Schema names
}

function tableToJsonSchema(table: TableSchema): JsonSchema {
  const properties: Record<string, JsonSchema> = {};
  const required: string[] = [];
  for (const col of table.columns) {
    const prop: JsonSchema = {};
    const baseType = jsonTypeFor(col.jsonType);
    prop.type = col.nullable ? [baseType, "null"] : baseType;
    if (col.format) prop.format = col.format;
    if (col.maxLength !== undefined) prop.maxLength = col.maxLength;
    if (col.default?.kind === "literal") prop.default = col.default.value;
    if (col.references) prop["x-references"] = col.references;
    if (col.primaryKey) prop.readOnly = true;
    if (col.unique) prop["x-unique"] = true;
    properties[col.tsName] = prop;
    if (!col.nullable) required.push(col.tsName);
  }
  return {
    type: "object",
    "x-table": table.dbTableName,
    "x-internal": true,
    "x-source": { file: table.file, line: table.line },
    properties,
    ...(required.length ? { required } : {}),
  };
}

function schemaNodeToJsonSchema(node: SchemaNode | undefined): JsonSchema {
  if (!node) return {};
  if (node.ref) return { $ref: `#/components/schemas/${node.ref}` };
  if (node.oneOf && node.oneOf.length > 0) {
    return { oneOf: node.oneOf.map(schemaNodeToJsonSchema), "x-confidence": node.confidence };
  }

  const out: JsonSchema = {};
  if (node.const !== undefined) out.const = node.const;
  if (node.enumValues && node.enumValues.length > 0) out.enum = node.enumValues;

  if (node.type && node.type !== "unknown") {
    out.type = node.nullable && node.type !== "null" ? [node.type, "null"] : node.type;
  } else if (node.nullable) {
    out.type = "null";
  }

  if (node.format) out.format = node.format;
  if (node.default !== undefined) out.default = node.default;

  if (node.type === "array") {
    out.items = node.items ? schemaNodeToJsonSchema(node.items) : {};
  }
  if (node.type === "object" && node.properties) {
    out.properties = Object.fromEntries(Object.entries(node.properties).map(([k, v]) => [k, schemaNodeToJsonSchema(v)]));
    if (node.required && node.required.length > 0) out.required = node.required;
  }

  if (node.note) out["x-note"] = node.note;
  out["x-confidence"] = node.confidence;
  return out;
}

function defaultSummary(method: string, path: string): string {
  const verb: Record<string, string> = { GET: "Get", POST: "Create", PUT: "Replace", PATCH: "Update", DELETE: "Delete" };
  const segments = path.split("/").filter(Boolean).filter((s) => !s.startsWith(":"));
  const resource = segments.join(" ").replace(/[-_]/g, " ");
  return `${verb[method] ?? method} ${resource}`.trim();
}

function deriveTag(file: string): string {
  const base = file
    .split("/")
    .pop()!
    .replace(/\.ts$/, "")
    .replace(/-routes?$/, "");
  return base
    .split(/[-_]/)
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

function operationId(route: RouteRecord): string {
  const slug = route.path
    .split("/")
    .filter(Boolean)
    .map((s) => s.replace(/^:/, "by-"))
    .join("_");
  return `${route.service}_${route.method.toLowerCase()}_${slug || "root"}`;
}

const STATUS_DESCRIPTIONS: Record<number, string> = {
  200: "OK",
  201: "Created",
  202: "Accepted",
  302: "Redirect",
  400: "Bad request",
  401: "Unauthorized",
  403: "Forbidden",
  404: "Not found",
  408: "Request timeout",
  409: "Conflict",
  413: "Payload too large",
  423: "Locked",
  429: "Too many requests",
  500: "Internal server error",
  502: "Bad gateway",
  503: "Service unavailable",
};

/** Turns an it() title into a short camelCase-ish key safe for an OpenAPI `examples` map. */
function exampleKey(title: string, index: number): string {
  const slug = title
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/(^-|-$)/g, "")
    .slice(0, 60);
  return slug ? `test-${slug}` : `test-${index}`;
}

export function buildOpenApiDocument(
  routesIr: RoutesIR,
  drizzleIr: DrizzleIR,
  analyses: RouteAnalysis[],
  testExamples: TestExample[] = [],
  frontendCrossChecks: FrontendCrossCheck[] = [],
  jsdocText: Map<string, JsdocRouteText> = new Map(),
): JsonSchema {
  const analysisById = new Map(analyses.map((a) => [a.routeId, a]));
  const serviceByKey = new Map<string, ServiceInfo>(routesIr.services.map((s) => [s.key, s]));
  const examplesByRoute = new Map<string, TestExample[]>();
  for (const ex of testExamples) {
    const list = examplesByRoute.get(ex.routeId) ?? [];
    list.push(ex);
    examplesByRoute.set(ex.routeId, list);
  }
  const frontendByRoute = new Map<string, FrontendCrossCheck[]>();
  for (const fc of frontendCrossChecks) {
    const list = frontendByRoute.get(fc.routeId) ?? [];
    list.push(fc);
    frontendByRoute.set(fc.routeId, list);
  }

  const schemas: Record<string, JsonSchema> = {};
  for (const table of drizzleIr.tables) schemas[table.schemaName] = tableToJsonSchema(table);
  schemas.Error = {
    type: "object",
    properties: { error: { type: "string" }, code: { type: "string" }, details: { type: "string" } },
    required: ["error"],
  };

  const paths: Record<string, JsonSchema> = {};
  const anyMethodRoutes: JsonSchema[] = [];

  for (const route of routesIr.routes) {
    if (route.anyMethod) {
      anyMethodRoutes.push({
        path: route.path,
        service: route.service,
        source: { file: route.file, line: route.line },
        description: "Registered via app.use()/router.use() as a method catch-all; not representable as a single OpenAPI operation.",
      });
      continue;
    }

    const analysis = analysisById.get(route.id);
    const service = serviceByKey.get(route.service);
    const pathKey = route.path.replace(/:([A-Za-z_][A-Za-z0-9_]*)/g, "{$1}");
    const pathItem = paths[pathKey] ?? (paths[pathKey] = {});
    const jsdoc = jsdocText.get(jsdocTextKey(route.method, pathKey));

    const parameters: JsonSchema[] = [];
    for (const p of analysis?.pathParams ?? []) {
      parameters.push({
        name: p.name,
        in: "path",
        required: true,
        schema: { type: p.type },
        ...(jsdoc?.parameters?.[p.name] ? { description: jsdoc.parameters[p.name] } : {}),
      });
    }
    for (const q of analysis?.queryParams ?? []) {
      const schema: JsonSchema = { type: q.type };
      if (q.default !== undefined) schema.default = q.default;
      const description = jsdoc?.parameters?.[q.name] ?? undefined;
      parameters.push({ name: q.name, in: "query", required: q.required, schema, ...(description ? { description } : {}) });
    }
    for (const h of analysis?.headers ?? []) {
      const description = jsdoc?.parameters?.[h.name] ?? h.note;
      parameters.push({ name: h.name, in: "header", required: false, schema: { type: "string" }, ...(description ? { description } : {}) });
    }

    const routeExamples = examplesByRoute.get(route.id) ?? [];
    const requestExamples = routeExamples.filter((e) => e.request);
    const jsonContentType = analysis?.requestBody.find((v) => v.contentType === "application/json")?.contentType;
    const routeFrontendCalls = frontendByRoute.get(route.id) ?? [];
    const frontendReturnType = routeFrontendCalls.find((fc) => fc.call.returnType && fc.call.returnType.type !== "unknown")?.call
      .returnType;
    const frontendBodyType = routeFrontendCalls.find(
      (fc) => fc.call.bodyType?.type === "object" && Object.keys(fc.call.bodyType.properties ?? {}).length > 0,
    )?.call.bodyType;

    const requestBody =
      analysis && analysis.requestBody.length > 0
        ? {
            content: Object.fromEntries(
              analysis.requestBody.map((v) => {
                // The backend sometimes spreads `...req.body` wholesale (e.g. preference
                // endpoints) instead of destructuring named fields, leaving nothing for
                // Phase 3 to find. When that happens and the frontend's own request type has
                // real fields, use those — same fallback idea as the response side below.
                const backendHasFields = Object.keys(v.schema.properties ?? {}).length > 0;
                const effectiveBodySchema =
                  v.contentType === "application/json" && !backendHasFields && frontendBodyType ? frontendBodyType : v.schema;
                const entry: JsonSchema = { schema: schemaNodeToJsonSchema(effectiveBodySchema) };
                if (v.contentType === jsonContentType && requestExamples.length > 0) {
                  entry.examples = Object.fromEntries(
                    requestExamples.map((e, i) => [
                      exampleKey(e.itTitle, i),
                      {
                        summary: e.itTitle,
                        description: `From \`${e.testFile}\` (${e.describeTitle})`,
                        value: e.request?.body ?? e.request,
                      },
                    ]),
                  );
                }
                return [v.contentType, entry];
              }),
            ),
          }
        : undefined;

    const responses: Record<string, JsonSchema> =
      analysis && analysis.responses.length > 0
        ? Object.fromEntries(
            analysis.responses.map((r) => {
              const key = r.status === "default" ? "default" : String(r.status);
              const body: JsonSchema = {
                description: r.description ?? STATUS_DESCRIPTIONS[r.status as number] ?? "Response",
              };
              const statusExamples = routeExamples.filter(
                (e) => e.response?.body !== undefined && String(e.response.status ?? "") === key,
              );
              // Phase 7: when the static handler analysis came up empty for a 2xx response,
              // the frontend's own declared return type (e.g. `Promise<SSHHost>`) is a real,
              // human-written fact about the same endpoint — better than nothing.
              const isSuccess = typeof r.status === "number" && r.status >= 200 && r.status < 300;
              const effectiveSchema =
                isSuccess && (!r.schema || r.schema.confidence === "unknown") && frontendReturnType
                  ? frontendReturnType
                  : r.schema;
              if (r.contentType && effectiveSchema) {
                const content: JsonSchema = { schema: schemaNodeToJsonSchema(effectiveSchema) };
                if (statusExamples.length > 0) {
                  content.examples = Object.fromEntries(
                    statusExamples.map((e, i) => [
                      exampleKey(e.itTitle, i),
                      {
                        summary: e.itTitle,
                        description: `From \`${e.testFile}\` (${e.describeTitle})${e.response?.partial ? " — partial match (toMatchObject), other fields may also be present" : ""}`,
                        value: e.response?.body,
                      },
                    ]),
                  );
                }
                body.content = { [r.contentType]: content };
              }
              if (r.headers && r.headers.length > 0) {
                body.headers = Object.fromEntries(r.headers.map((h) => [h, { schema: { type: "string" } }]));
              }
              return [key, body];
            }),
          )
        : { default: { description: "Response not analyzed" } };

    // A test can confirm a status the static handler analysis never produced — e.g. it comes
    // from a middleware, or a code path the AST walk didn't reach. The test is right; add it.
    for (const e of routeExamples) {
      if (e.response?.status === undefined) continue;
      const key = String(e.response.status);
      if (responses[key]) continue;
      responses[key] = {
        description: `${STATUS_DESCRIPTIONS[e.response.status] ?? "Response"} — only confirmed by \`${e.testFile}\`, not by static analysis`,
        ...(e.response.body !== undefined
          ? {
              content: {
                "application/json": {
                  schema: { type: "object", "x-confidence": "test" },
                  examples: { [exampleKey(e.itTitle, 0)]: { summary: e.itTitle, value: e.response.body } },
                },
              },
            }
          : {}),
      };
    }

    const security = analysis?.auth.required
      ? [{ bearerAuth: [] }, { apiKeyBearer: [] }, { cookieAuth: [] }]
      : [];

    pathItem[route.method.toLowerCase()] = {
      operationId: operationId(route),
      summary: jsdoc?.summary ?? defaultSummary(route.method, route.path),
      ...(jsdoc?.description ? { description: jsdoc.description } : {}),
      tags: jsdoc?.tags ?? [deriveTag(route.file)],
      ...(parameters.length > 0 ? { parameters } : {}),
      ...(requestBody ? { requestBody } : {}),
      responses,
      security,
      servers: service ? [{ url: `http://localhost:${service.port ?? "?"}`, description: service.key }] : undefined,
      "x-source": { file: route.file, line: route.line },
      ...(analysis?.auth.requiresAdmin ? { "x-requires-admin": true } : {}),
      ...(analysis?.auth.requiresDataAccess ? { "x-requires-data-access": true } : {}),
      ...(route.sharedHandlerWith.length > 0 ? { "x-shared-handler-with": route.sharedHandlerWith } : {}),
      ...(analysis?.opaque ? { "x-confidence": "unknown", "x-note": "handler could not be statically resolved" } : {}),
      ...(routeFrontendCalls.length > 0
        ? {
            "x-frontend-calls": routeFrontendCalls.map((fc) => ({
              function: fc.call.functionName,
              file: fc.call.file,
              line: fc.call.line,
              ...(fc.warnings.length > 0 ? { warnings: fc.warnings } : {}),
            })),
          }
        : {}),
    };
  }

  const servers = routesIr.services
    .filter((s) => s.port !== null)
    .map((s) => ({ url: `http://localhost:${s.port}`, description: s.key }));

  return {
    openapi: "3.1.0",
    info: {
      title: "Termix API (unofficial, generated)",
      version: routesIr.meta.tag || "unknown",
      description:
        "Generated by termix-sdk's spec-gen tool by statically analyzing the Termix backend source " +
        "(routes, Drizzle schema, response construction) rather than trusting the project's own " +
        "hand-written openapi.json. See tools/spec-gen/docs/spec-generation-strategy.md.",
    },
    "x-termix-source": {
      tag: routesIr.meta.tag,
      commit: routesIr.meta.commit,
      generatedAt: routesIr.meta.generatedAt,
    },
    servers,
    paths,
    components: {
      schemas,
      securitySchemes: {
        bearerAuth: { type: "http", scheme: "bearer", bearerFormat: "JWT" },
        apiKeyBearer: {
          type: "http",
          scheme: "bearer",
          description: "API key prefixed with tmx_, sent via the same Authorization header as a JWT.",
        },
        cookieAuth: { type: "apiKey", in: "cookie", name: "jwt" },
      },
    },
    security: [{ bearerAuth: [] }, { apiKeyBearer: [] }, { cookieAuth: [] }],
    ...(anyMethodRoutes.length > 0 ? { "x-any-method-routes": anyMethodRoutes } : {}),
  };
}
