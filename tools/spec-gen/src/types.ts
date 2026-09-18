/**
 * Intermediate representation (IR) types shared across every extraction phase.
 * See tools/spec-gen/docs/spec-generation-strategy.md for the full design.
 */

export type Confidence =
  | "test"
  | "repository-type"
  | "handler-literal"
  | "frontend-type"
  | "matched-type"
  | "inferred"
  | "unknown";

export interface SourceLocation {
  file: string;
  line: number;
}

export type HttpMethod = "GET" | "POST" | "PUT" | "PATCH" | "DELETE" | "*";

/** A single route registration, as discovered by Phase 1. */
export interface RouteRecord {
  /** Stable id: "<relFile>#L<line>:<METHOD>:<path>" */
  id: string;
  method: HttpMethod;
  /** Final resolved path, e.g. "/host/db/host" */
  path: string;
  /** The path literal as written at the registration site, e.g. "/db/host" */
  expressPath: string;
  /** Service key, e.g. "database", "tunnel", "file-manager" */
  service: string;
  /** Port number of the express() app that ultimately serves this route, if resolved */
  port: number | null;
  file: string;
  line: number;
  /** Syntactic shape of the final handler argument */
  handlerKind:
    | "inline-arrow"
    | "inline-function"
    | "named-function"
    | "property-handler";
  /** Middleware identifiers between the path and the final handler, in order */
  middlewares: string[];
  /** Other route ids that share the exact same handler function (array-literal paths) */
  sharedHandlerWith: string[];
  /** True when this route came from X.use(path, fn) as a method catch-all */
  anyMethod: boolean;
}

export interface UnresolvedRoute {
  file: string;
  line: number;
  reason: string;
  snippet: string;
}

export interface ServiceInfo {
  key: string;
  file: string;
  port: number | null;
  globalAuth: boolean;
  /** Line at which app.use(createAuthMiddleware()) is registered, if globalAuth is true */
  globalAuthLine: number | null;
  bodyLimits: Record<string, string>;
}

export interface RoutesIR {
  meta: RunMeta;
  services: ServiceInfo[];
  routes: RouteRecord[];
  unresolved: UnresolvedRoute[];
}

export interface RunMeta {
  tag: string;
  commit: string;
  generatedAt: string;
  sourceRepo: string;
  expressVersion: string | null;
}

/** A single JSON-Schema-ish column type, as derived from a Drizzle column builder call. */
export interface ColumnSchema {
  /** TypeScript object-key name, e.g. "isAdmin" */
  tsName: string;
  /** Actual database column name, e.g. "is_admin" */
  dbName: string;
  jsonType: "string" | "integer" | "boolean" | "number";
  format?: "date-time";
  maxLength?: number;
  nullable: boolean;
  default?: { kind: "literal"; value: string | number | boolean } | { kind: "expression"; text: string };
  primaryKey: boolean;
  autoIncrement: boolean;
  unique: boolean;
  /** "otherTsVarName.column" when this column has a Drizzle .references() call */
  references?: string;
}

export interface TableSchema {
  /** TS export name, e.g. "hosts" */
  tsVarName: string;
  /** Actual database table name, e.g. "ssh_data" */
  dbTableName: string;
  /** Preferred components.schemas name: the repository's own `*Record` type when found, else derived */
  schemaName: string;
  file: string;
  line: number;
  columns: ColumnSchema[];
}

export interface DrizzleIR {
  tables: TableSchema[];
}

// ---- Phases 2-4: per-route auth, parameters, request body, responses ----

export type JsonPrimitive = "string" | "integer" | "number" | "boolean" | "null";

/** A JSON-Schema-ish field/value shape produced by Phases 3-4. Deliberately small: this
 *  generator only ever infers what the source code makes reasonably explicit. */
export interface SchemaNode {
  type?: JsonPrimitive | "array" | "object" | "unknown";
  /** $ref target: a components.schemas name (e.g. a Drizzle *Record) */
  ref?: string;
  items?: SchemaNode;
  properties?: Record<string, SchemaNode>;
  required?: string[];
  enumValues?: (string | number)[];
  const?: string | number | boolean;
  default?: string | number | boolean;
  format?: "binary" | "date-time";
  nullable?: boolean;
  confidence: Confidence;
  /** Free-text note, e.g. which transformer produced this shape */
  note?: string;
  /** Distinct shapes seen at the same status+contentType (e.g. /users/login's two 200 forms) */
  oneOf?: SchemaNode[];
}

export interface AuthInfo {
  required: boolean;
  requiresAdmin: boolean;
  requiresDataAccess: boolean;
  /** Header name used for admin impersonation, when the middleware chain allows it */
  adminImpersonation: boolean;
}

export interface PathParamInfo {
  name: string;
  type: "integer" | "string";
}

export interface QueryParamInfo {
  name: string;
  type: JsonPrimitive;
  required: boolean;
  default?: string | number | boolean;
  enumValues?: string[];
}

export interface HeaderParamInfo {
  name: string;
  note?: string;
}

export interface RequestBodyVariant {
  contentType: string;
  schema: SchemaNode;
}

export interface ResponseInfo {
  status: number | "default";
  contentType: string | null;
  description?: string;
  schema?: SchemaNode;
  headers?: string[];
}

export interface RouteAnalysis {
  routeId: string;
  auth: AuthInfo;
  pathParams: PathParamInfo[];
  queryParams: QueryParamInfo[];
  headers: HeaderParamInfo[];
  requestBody: RequestBodyVariant[];
  responses: ResponseInfo[];
  /** True when the handler could not be located/analyzed at all (opaque property-handler, etc.) */
  opaque: boolean;
}

