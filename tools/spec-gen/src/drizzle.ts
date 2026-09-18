/**
 * Phase 5: Drizzle schema (src/backend/database/db/schema.ts) -> table/column IR.
 * This becomes components.schemas in the emitted OpenAPI (Phase 9) and is the
 * base every repository-typed response (Phase 4) resolves against.
 *
 * See tools/spec-gen/docs/spec-generation-strategy.md, Phase 5.
 */

import { Node, Project, SyntaxKind } from "ts-morph";
import type { ColumnSchema, DrizzleIR, TableSchema } from "./types.js";
import { relFile } from "./project.js";

const SCHEMA_FILE = "src/backend/database/db/schema.ts";
const TABLE_FNS = new Set(["sqliteTable", "pgTable", "mysqlTable"]);

interface ChainCall {
  method: string;
  args: Node[];
}

interface ChainResult {
  baseName: string;
  baseArgs: Node[];
  calls: ChainCall[];
}

function collectChain(exprIn: Node): ChainResult | null {
  const calls: ChainCall[] = [];
  let cur: Node = exprIn;
  while (Node.isCallExpression(cur)) {
    const callee = cur.getExpression();
    if (Node.isPropertyAccessExpression(callee)) {
      calls.unshift({ method: callee.getName(), args: cur.getArguments() });
      cur = callee.getExpression();
      continue;
    }
    if (Node.isIdentifier(callee)) {
      return { baseName: callee.getText(), baseArgs: cur.getArguments(), calls };
    }
    return null;
  }
  return null;
}

function literalText(node: Node): string | null {
  if (Node.isStringLiteral(node) || Node.isNoSubstitutionTemplateLiteral(node)) return node.getLiteralText();
  return null;
}

function objectLiteralOptions(node: Node | undefined): Map<string, Node> {
  const out = new Map<string, Node>();
  if (!node || !Node.isObjectLiteralExpression(node)) return out;
  for (const prop of node.getProperties()) {
    if (Node.isPropertyAssignment(prop)) {
      const init = prop.getInitializer();
      if (init) out.set(prop.getName(), init);
    }
  }
  return out;
}

function resolveDefaultValue(arg: Node): ColumnSchema["default"] {
  if (arg.getKind() === SyntaxKind.TrueKeyword) return { kind: "literal", value: true };
  if (arg.getKind() === SyntaxKind.FalseKeyword) return { kind: "literal", value: false };
  if (Node.isNumericLiteral(arg)) return { kind: "literal", value: Number(arg.getText()) };
  const s = literalText(arg);
  if (s !== null) return { kind: "literal", value: s };
  return { kind: "expression", text: arg.getText() };
}

function baseTypeToJsonType(
  baseName: string,
  mode: string | undefined,
): { jsonType: ColumnSchema["jsonType"]; format?: "date-time" } {
  if (mode === "boolean") return { jsonType: "boolean" };
  if (mode === "timestamp") return { jsonType: "string", format: "date-time" };
  switch (baseName) {
    case "text":
    case "varchar":
      return { jsonType: "string" };
    case "integer":
    case "serial":
      return { jsonType: "integer" };
    case "real":
    case "numeric":
    case "doublePrecision":
      return { jsonType: "number" };
    case "boolean":
      return { jsonType: "boolean" };
    case "timestamp":
    case "date":
      return { jsonType: "string", format: "date-time" };
    default:
      return { jsonType: "string" };
  }
}

function extractColumn(tsName: string, initializer: Node): ColumnSchema | null {
  const chain = collectChain(initializer);
  if (!chain) return null;

  const options = objectLiteralOptions(chain.baseArgs[1]);
  const modeNode = options.get("mode");
  const mode = modeNode ? literalText(modeNode) ?? undefined : undefined;
  const { jsonType, format } = baseTypeToJsonType(chain.baseName, mode ?? undefined);

  const dbNameArg = chain.baseArgs[0];
  const dbName = (dbNameArg && literalText(dbNameArg)) ?? tsName;

  const lengthNode = options.get("length");
  const maxLength =
    lengthNode && Node.isNumericLiteral(lengthNode) ? Number(lengthNode.getText()) : undefined;

  let nullable = true;
  let primaryKey = false;
  let autoIncrement = false;
  let unique = false;
  let defaultVal: ColumnSchema["default"] | undefined;
  let references: string | undefined;

  for (const call of chain.calls) {
    switch (call.method) {
      case "notNull":
        nullable = false;
        break;
      case "primaryKey": {
        primaryKey = true;
        nullable = false;
        const arg0 = call.args[0];
        if (arg0 && Node.isObjectLiteralExpression(arg0)) {
          for (const prop of arg0.getProperties()) {
            if (Node.isPropertyAssignment(prop) && prop.getName() === "autoIncrement") {
              const init = prop.getInitializer();
              if (init && init.getKind() === SyntaxKind.TrueKeyword) autoIncrement = true;
            }
          }
        }
        break;
      }
      case "unique":
        unique = true;
        break;
      case "default":
      case "$defaultFn":
        if (call.args[0]) defaultVal = resolveDefaultValue(call.args[0]);
        break;
      case "references": {
        const arrowFn = call.args[0];
        if (arrowFn && Node.isArrowFunction(arrowFn)) {
          let body: Node = arrowFn.getBody();
          while (Node.isParenthesizedExpression(body)) body = body.getExpression();
          references = body.getText();
        }
        break;
      }
      default:
        break; // $type<>(), etc. — not needed for the JSON Schema shape
    }
  }

  return {
    tsName,
    dbName,
    jsonType,
    ...(format ? { format } : {}),
    ...(maxLength !== undefined ? { maxLength } : {}),
    nullable,
    ...(defaultVal ? { default: defaultVal } : {}),
    primaryKey,
    autoIncrement,
    unique,
    ...(references ? { references } : {}),
  };
}

function toPascalCase(name: string): string {
  return name.charAt(0).toUpperCase() + name.slice(1);
}

/**
 * Finds `export type XRecord = typeof tableVar.$inferSelect;` across the repositories
 * directory. Several repositories often alias the same table for their own local use
 * (e.g. `HostRecord` in host-repository.ts, but also `FleetMemberHostRecord` in
 * fleet-repository.ts and 3 more, all for the `hosts` table) — when that happens we
 * prefer the shortest name, since the "owning" repository's alias is consistently the
 * least qualified one in this codebase, while call-site-specific repos prefix/suffix it.
 */
function findRecordTypeNames(project: Project, repoPath: string): Map<string, string> {
  const candidates = new Map<string, string[]>();
  const repoDir = "src/backend/database/repositories/";
  for (const sf of project.getSourceFiles()) {
    if (!relFile(repoPath, sf.getFilePath()).startsWith(repoDir)) continue;
    for (const alias of sf.getDescendantsOfKind(SyntaxKind.TypeAliasDeclaration)) {
      const typeNode = alias.getTypeNode();
      if (!typeNode || typeNode.getKind() !== SyntaxKind.TypeQuery) continue;
      const text = typeNode.getText(); // e.g. "typeof snippetFolders.$inferSelect"
      const m = /^typeof\s+([A-Za-z_$][\w$]*)\.\$inferSelect$/.exec(text);
      if (!m) continue;
      const tableVar = m[1];
      const list = candidates.get(tableVar) ?? [];
      list.push(alias.getName());
      candidates.set(tableVar, list);
    }
  }
  const out = new Map<string, string>();
  for (const [tableVar, names] of candidates) {
    const sorted = [...names].sort((a, b) => a.length - b.length || a.localeCompare(b));
    out.set(tableVar, sorted[0]);
  }
  return out;
}

export function extractDrizzleSchema(project: Project, repoPath: string): DrizzleIR {
  const sf = project.getSourceFiles().find((f) => relFile(repoPath, f.getFilePath()) === SCHEMA_FILE);
  if (!sf) throw new Error(`Drizzle schema not found at ${SCHEMA_FILE}`);

  const recordNames = findRecordTypeNames(project, repoPath);
  const tables: TableSchema[] = [];

  for (const varDecl of sf.getDescendantsOfKind(SyntaxKind.VariableDeclaration)) {
    const stmt = varDecl.getVariableStatement();
    if (!stmt || !stmt.isExported()) continue;
    const init = varDecl.getInitializer();
    if (!init || !Node.isCallExpression(init)) continue;
    const callee = init.getExpression();
    if (!Node.isIdentifier(callee) || !TABLE_FNS.has(callee.getText())) continue;

    const args = init.getArguments();
    const dbTableName = (args[0] && literalText(args[0])) ?? varDecl.getName();
    const columnsArg = args[1];
    if (!columnsArg || !Node.isObjectLiteralExpression(columnsArg)) continue;

    const columns: ColumnSchema[] = [];
    for (const prop of columnsArg.getProperties()) {
      if (!Node.isPropertyAssignment(prop)) continue;
      const tsName = prop.getName();
      const propInit = prop.getInitializer();
      if (!propInit) continue;
      const col = extractColumn(tsName, propInit);
      if (col) columns.push(col);
      else console.error(`[drizzle] could not parse column "${tsName}" on table "${varDecl.getName()}"`);
    }

    const tsVarName = varDecl.getName();
    tables.push({
      tsVarName,
      dbTableName,
      schemaName: recordNames.get(tsVarName) ?? `${toPascalCase(tsVarName)}Record`,
      file: relFile(repoPath, sf.getFilePath()),
      line: varDecl.getStartLineNumber(),
      columns,
    });
  }

  return { tables };
}
