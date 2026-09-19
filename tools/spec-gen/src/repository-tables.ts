/**
 * E2 (docs/spec-generation-strategy-v2.md): resolves which Drizzle table(s) each
 * `createCurrentXRepository()` factory export (from `database/repositories/factory.ts`)
 * operates on. A request-body field whose name matches a column of a table the calling
 * handler's own repository calls resolve to can inherit that column's type — this module is
 * the "fábrica -> tabela(s)" half of that (E2 step 1); handler-analysis.ts does step 2
 * (which factories a given handler calls) and step 3 (matching a field against the result).
 */

import { Node, Project } from "ts-morph";
import type { TableSchema } from "./types.js";
import { relFile } from "./project.js";

const FACTORY_FILE = "src/backend/database/repositories/factory.ts";
const SCHEMA_IMPORT_SUFFIX = "db/schema.js";

export interface RepositoryTables {
  /** The table this repository "owns" — checked first for a field-name match. */
  primary: TableSchema | null;
  /** Every other table the repository's own file imports from schema.js. Checked only when
   *  no primary table (across every factory the handler calls) has a matching column. */
  secondary: TableSchema[];
}

/**
 * `createCurrentHostRepository(): HostRepository` -> resolve `HostRepository`'s own source
 * file -> every table identifier it imports from `../db/schema.js`. Multiple tables per
 * repository is normal (`host-repository.ts` imports both `hosts` and `hostAccess`), so the
 * "primary" table is picked by name proximity to the repository's own filename — the
 * heuristic the plan calls out as a starting point, not a claim of full correctness.
 */
export function resolveRepositoryTables(
  project: Project,
  repoPath: string,
  tables: TableSchema[],
): Map<string, RepositoryTables> {
  const tablesByVarName = new Map(tables.map((t) => [t.tsVarName, t]));
  const out = new Map<string, RepositoryTables>();

  const factorySf = project.getSourceFiles().find((f) => relFile(repoPath, f.getFilePath()) === FACTORY_FILE);
  if (!factorySf) return out;

  for (const fn of factorySf.getFunctions()) {
    if (!fn.isExported()) continue;
    const name = fn.getName();
    if (!name || !name.startsWith("createCurrent") || !name.endsWith("Repository")) continue;

    const returnTypeNode = fn.getReturnTypeNode();
    if (!returnTypeNode) continue;
    const classSymbol = returnTypeNode.getType().getSymbol();
    const classDecl = classSymbol?.getDeclarations().find((d) => Node.isClassDeclaration(d));
    if (!classDecl) continue;

    const repoSf = classDecl.getSourceFile();
    const repoFileRel = relFile(repoPath, repoSf.getFilePath());
    const repoFileBase = repoFileRel
      .split("/")
      .pop()!
      .replace(/-repository\.ts$/, "")
      .replace(/-/g, "")
      .toLowerCase();

    const importedTableNames: string[] = [];
    for (const imp of repoSf.getImportDeclarations()) {
      if (!imp.getModuleSpecifierValue().endsWith(SCHEMA_IMPORT_SUFFIX)) continue;
      for (const named of imp.getNamedImports()) importedTableNames.push(named.getName());
    }
    const importedTables = importedTableNames.map((n) => tablesByVarName.get(n)).filter((t): t is TableSchema => !!t);
    if (importedTables.length === 0) continue;

    // Score 2: `host-repository.ts` -> `hosts` (file base + plain "s" == table var name).
    // Score 1: file base is a prefix of the table name (`hostFolders` from `host-folder-
    // repository.ts` -> base "hostfolder", which isn't a plain pluralization but does prefix-
    // match). Ties (and the no-match case) fall back to the shortest imported table name,
    // since a repository's own table is consistently the least-qualified one in this codebase
    // (`hosts`, not `hostAccess`; `snippets`, not some join table it also happens to touch).
    let best: TableSchema | null = null;
    let bestScore = -1;
    for (const t of importedTables) {
      const varLower = t.tsVarName.toLowerCase();
      const score = varLower === repoFileBase + "s" ? 2 : varLower.startsWith(repoFileBase) || repoFileBase.startsWith(varLower) ? 1 : 0;
      if (score > bestScore || (score === bestScore && best && t.tsVarName.length < best.tsVarName.length)) {
        best = t;
        bestScore = score;
      }
    }
    const primary = best;
    const secondary = importedTables.filter((t) => t !== primary);
    out.set(name, { primary, secondary });
  }

  return out;
}
