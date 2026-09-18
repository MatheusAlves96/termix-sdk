/**
 * Known response transformers from database/routes/host-normalizers.ts.
 *
 * `transformHostResponse` and `stripSensitiveFields` are both host-specific (confirmed
 * by reading their source in the release-2.7.1-tag clone) and are modeled here by
 * walking the live `hosts` Drizzle table rather than a hand-typed field list, so the
 * shape tracks schema changes across Termix versions instead of silently going stale.
 * Everything else is listed in config/transformers.json as "opaque": named in the
 * output with a note, but not expanded.
 *
 * See tools/spec-gen/docs/spec-generation-strategy.md, Phase 4, item 3.
 */

import type { ColumnSchema, SchemaNode, TableSchema } from "./types.js";

// Confirmed at database/routes/host-normalizers.ts:261 (SENSITIVE_FIELDS)
const SENSITIVE_HOST_FIELDS = new Set([
  "key",
  "keyPassword",
  "autostartKey",
  "autostartKeyPassword",
  "password",
  "sudoPassword",
  "socks5Password",
  "rdpPassword",
  "vncPassword",
  "telnetPassword",
  "autostartPassword",
]);

const HAS_FLAGS = [
  "hasKey",
  "hasKeyPassword",
  "hasPassword",
  "hasSudoPassword",
  "hasRdpPassword",
  "hasVncPassword",
  "hasTelnetPassword",
];

const JSON_ARRAY_COLUMNS = new Set([
  "tunnelConnections",
  "jumpHosts",
  "quickActions",
  "socks5ProxyChain",
  "portKnockSequence",
]);

const JSON_OBJECT_COLUMNS = new Set([
  "statsConfig",
  "terminalConfig",
  "dockerConfig",
  "proxmoxConfig",
  "proxmoxStatsConfig",
  "guacamoleConfig",
]);

const EXTRA_BOOLEAN_COLUMNS = new Set([
  "pin",
  "shareSshAuth",
  "useWarpgate",
  "ignoreCert",
  "rdpIgnoreCert",
  "forceKeyboardInteractive",
]);

function columnToSchema(col: ColumnSchema): SchemaNode {
  if (col.tsName === "tags") {
    return { type: "array", items: { type: "string", confidence: "inferred" }, confidence: "inferred" };
  }
  if (JSON_ARRAY_COLUMNS.has(col.tsName)) {
    return { type: "array", items: { type: "object", confidence: "inferred" }, confidence: "inferred" };
  }
  if (JSON_OBJECT_COLUMNS.has(col.tsName)) {
    return { type: "object", nullable: true, confidence: "inferred" };
  }
  if (col.tsName.startsWith("enable") || col.tsName.startsWith("show") || EXTRA_BOOLEAN_COLUMNS.has(col.tsName)) {
    return { type: "boolean", confidence: "inferred" };
  }
  return {
    type: col.jsonType,
    confidence: "inferred",
    ...(col.nullable ? { nullable: true } : {}),
  };
}

/** Builds the response shape of `transformHostResponse(row)`, optionally also passed through `stripSensitiveFields`. */
export function buildHostResponseSchema(hostsTable: TableSchema, stripped: boolean): SchemaNode {
  const properties: Record<string, SchemaNode> = {};
  const required: string[] = [];

  for (const col of hostsTable.columns) {
    if (stripped && SENSITIVE_HOST_FIELDS.has(col.tsName)) continue;
    properties[col.tsName] = columnToSchema(col);
    required.push(col.tsName);
  }

  if (stripped) {
    for (const flag of HAS_FLAGS) {
      properties[flag] = { type: "boolean", confidence: "inferred" };
      required.push(flag);
    }
  }

  return {
    type: "object",
    properties,
    required,
    confidence: "inferred",
    note: stripped
      ? "derived from stripSensitiveFields(transformHostResponse(row)) in host-normalizers.ts"
      : "derived from transformHostResponse(row) in host-normalizers.ts",
  };
}

export interface TransformerRegistry {
  expanded: Set<string>;
  opaque: Set<string>;
}

export function applyKnownTransformer(
  name: string,
  hostsTable: TableSchema | undefined,
  innerCallName: string | undefined,
): SchemaNode | null {
  if (name === "stripSensitiveFields") {
    if (!hostsTable) return { type: "object", confidence: "unknown", note: "stripSensitiveFields(); hosts table unavailable" };
    return buildHostResponseSchema(hostsTable, true);
  }
  if (name === "transformHostResponse") {
    if (!hostsTable) return { type: "object", confidence: "unknown", note: "transformHostResponse(); hosts table unavailable" };
    return buildHostResponseSchema(hostsTable, false);
  }
  void innerCallName;
  return null;
}
