/**
 * Phase 6: mines real request/response examples out of the route test suite
 * (`tests/database/routes/*.test.ts`, `tests/hosts/**​/*.test.ts`).
 *
 * These tests build their own fake router/response mocks in wildly different
 * shapes from file to file (see the design doc's Phase 6 section), so rather
 * than trying to trace any one test harness's construction, this reads off a
 * convention that turned out to hold across a good chunk of the suite: the
 * `describe("METHOD /express/path", () => {...})` block title *is* the route,
 * Express-syntax path and all. Matched against that, an `it()` block's own
 * `expect(x.statusCode).toBe(N)` / `expect(x.jsonBody | x.body).toEqual(...)`
 * assertions are read directly off their arguments — self-contained, so it
 * doesn't matter how `x` itself was built.
 *
 * These test files never resolve through registerXRoutes() the way
 * production code does — but that's fine, because Phase 1 already recorded
 * each route's `file` as wherever its literal `X.method(...)` call sits, and
 * that's the same file a route test imports from (directly or through a
 * `registerXRoutes(fakeRouter(), ...)` call), so file-based correlation still
 * lines up.
 *
 * See tools/spec-gen/docs/spec-generation-strategy.md, Phase 6.
 */

import { Node, Project, SourceFile, SyntaxKind } from "ts-morph";
import { posix as posixPath } from "node:path";
import type { RouteRecord, RoutesIR, TestExample } from "./types.js";
import { relFile } from "./project.js";

const METHOD_PATH_RE = /^(GET|POST|PUT|PATCH|DELETE)\s+(\/\S*)/;

function literalToJson(node: Node, depth = 0): unknown {
  if (depth > 6) return "<...>";
  if (node.getKind() === SyntaxKind.TrueKeyword) return true;
  if (node.getKind() === SyntaxKind.FalseKeyword) return false;
  if (node.getKind() === SyntaxKind.NullKeyword) return null;
  if (Node.isNumericLiteral(node)) return Number(node.getText());
  if (Node.isStringLiteral(node) || Node.isNoSubstitutionTemplateLiteral(node)) return node.getLiteralText();
  if (Node.isArrayLiteralExpression(node)) return node.getElements().map((e) => literalToJson(e, depth + 1));
  if (Node.isObjectLiteralExpression(node)) {
    const out: Record<string, unknown> = {};
    for (const p of node.getProperties()) {
      if (Node.isPropertyAssignment(p)) {
        const init = p.getInitializer();
        out[p.getName()] = init ? literalToJson(init, depth + 1) : "<expr>";
      } else if (Node.isShorthandPropertyAssignment(p)) {
        out[p.getName()] = "<expr>";
      }
    }
    return out;
  }
  return "<expr>"; // identifier, call, member access, etc. — not a static literal, not worth chasing
}

/** Nearest enclosing `describe("METHOD /path", ...)` ancestor's method+path, if any. */
function findEnclosingRouteTitle(nodeIn: Node): { method: string; path: string } | null {
  let cur: Node | undefined = nodeIn.getParent();
  while (cur) {
    if (Node.isCallExpression(cur)) {
      const callee = cur.getExpression();
      if (Node.isIdentifier(callee) && callee.getText() === "describe") {
        const arg0 = cur.getArguments()[0];
        if (arg0 && (Node.isStringLiteral(arg0) || Node.isNoSubstitutionTemplateLiteral(arg0))) {
          const m = METHOD_PATH_RE.exec(arg0.getLiteralText());
          if (m) return { method: m[1], path: m[2] };
        }
      }
    }
    cur = cur.getParent();
  }
  return null;
}

/** First object literal in the block with a body/params/query/headers key — the request overrides. */
function findRequestExample(fnBody: Node): TestExample["request"] | undefined {
  const REQUEST_KEYS = ["body", "params", "query", "headers"];
  for (const obj of fnBody.getDescendantsOfKind(SyntaxKind.ObjectLiteralExpression)) {
    const result: Record<string, unknown> = {};
    for (const p of obj.getProperties()) {
      if (Node.isPropertyAssignment(p) && REQUEST_KEYS.includes(p.getName())) {
        const init = p.getInitializer();
        if (init) result[p.getName()] = literalToJson(init);
      }
    }
    if (Object.keys(result).length > 0) return result;
  }
  return undefined;
}

/** `expect(<x>.statusCode | <x>.status).toBe(N)` / `.toEqual(N)` anywhere in the block. */
function findStatus(fnBody: Node): number | undefined {
  for (const call of fnBody.getDescendantsOfKind(SyntaxKind.CallExpression)) {
    const callee = call.getExpression();
    if (!Node.isPropertyAccessExpression(callee)) continue;
    if (callee.getName() !== "toBe" && callee.getName() !== "toEqual") continue;
    const expectCall = callee.getExpression();
    if (!Node.isCallExpression(expectCall)) continue;
    const expectCallee = expectCall.getExpression();
    if (!Node.isIdentifier(expectCallee) || expectCallee.getText() !== "expect") continue;
    const target = expectCall.getArguments()[0];
    if (!target || !Node.isPropertyAccessExpression(target)) continue;
    if (target.getName() !== "statusCode" && target.getName() !== "status") continue;
    const statusArg = call.getArguments()[0];
    if (statusArg && Node.isNumericLiteral(statusArg)) return Number(statusArg.getText());
  }
  return undefined;
}

/** `expect(<x>.jsonBody | <x>.body).toEqual({...})` / `.toMatchObject({...})` anywhere in the block. */
function findResponseBody(fnBody: Node): { body: unknown; partial: boolean } | undefined {
  for (const call of fnBody.getDescendantsOfKind(SyntaxKind.CallExpression)) {
    const callee = call.getExpression();
    if (!Node.isPropertyAccessExpression(callee)) continue;
    const matcher = callee.getName();
    if (matcher !== "toEqual" && matcher !== "toMatchObject") continue;
    const expectCall = callee.getExpression();
    if (!Node.isCallExpression(expectCall)) continue;
    const expectCallee = expectCall.getExpression();
    if (!Node.isIdentifier(expectCallee) || expectCallee.getText() !== "expect") continue;
    const target = expectCall.getArguments()[0];
    if (!target || !Node.isPropertyAccessExpression(target)) continue;
    if (target.getName() !== "jsonBody" && target.getName() !== "body") continue;
    const bodyArg = call.getArguments()[0];
    if (bodyArg && Node.isObjectLiteralExpression(bodyArg)) {
      return { body: literalToJson(bodyArg), partial: matcher === "toMatchObject" };
    }
  }
  return undefined;
}

/** Every relative import (static or dynamic `import()`) in the file, resolved to a repo-relative .ts path. */
function resolveImportedBackendFiles(sf: SourceFile, testFileRel: string): string[] {
  const dir = posixPath.dirname(testFileRel);
  const specifiers = new Set<string>();

  for (const imp of sf.getImportDeclarations()) {
    const spec = imp.getModuleSpecifierValue();
    if (spec) specifiers.add(spec);
  }
  for (const call of sf.getDescendantsOfKind(SyntaxKind.CallExpression)) {
    if (!Node.isImportExpression(call.getExpression())) continue;
    const arg = call.getArguments()[0];
    if (arg && (Node.isStringLiteral(arg) || Node.isNoSubstitutionTemplateLiteral(arg))) {
      specifiers.add(arg.getLiteralText());
    }
  }

  const out = new Set<string>();
  for (const spec of specifiers) {
    if (!spec.startsWith(".")) continue; // skip package imports (express, vitest, jose, ...)
    out.add(posixPath.normalize(posixPath.join(dir, spec)).replace(/\.js$/, ".ts"));
  }
  return [...out];
}

export function extractTestExamples(project: Project, repoPath: string, routesIr: RoutesIR): TestExample[] {
  const testFiles = project.addSourceFilesAtPaths([
    posixPath.join(repoPath.replace(/\\/g, "/"), "src/backend/tests/database/routes/**/*.test.ts"),
    posixPath.join(repoPath.replace(/\\/g, "/"), "src/backend/tests/hosts/**/*.test.ts"),
  ]);

  const routesByFile = new Map<string, RouteRecord[]>();
  for (const r of routesIr.routes) {
    const list = routesByFile.get(r.file) ?? [];
    list.push(r);
    routesByFile.set(r.file, list);
  }

  const examples: TestExample[] = [];

  for (const sf of testFiles) {
    const testFileRel = relFile(repoPath, sf.getFilePath());
    const backendFiles = resolveImportedBackendFiles(sf, testFileRel);
    const candidateRoutes = backendFiles.flatMap((f) => routesByFile.get(f) ?? []);
    if (candidateRoutes.length === 0) continue;

    for (const call of sf.getDescendantsOfKind(SyntaxKind.CallExpression)) {
      const callee = call.getExpression();
      if (!Node.isIdentifier(callee) || (callee.getText() !== "it" && callee.getText() !== "test")) continue;

      const titleArg = call.getArguments()[0];
      const itTitle =
        titleArg && (Node.isStringLiteral(titleArg) || Node.isNoSubstitutionTemplateLiteral(titleArg))
          ? titleArg.getLiteralText()
          : "";
      const fn = call.getArguments()[1];
      if (!fn || !(Node.isArrowFunction(fn) || Node.isFunctionExpression(fn))) continue;

      let routeTitle = findEnclosingRouteTitle(call);
      if (!routeTitle) {
        const m = METHOD_PATH_RE.exec(itTitle);
        if (m) routeTitle = { method: m[1], path: m[2] };
      }
      if (!routeTitle) continue;

      // describe() titles are inconsistent about which path they name: some tests register
      // straight onto a fake router and title with the router-local path (e.g. "/list", as
      // registered), others title with the fully mounted path (e.g. "/session-sharing/create",
      // as a client would call it) even though the route itself is only ever registered with
      // its local "/create". Accept either.
      const route = candidateRoutes.find(
        (r) => r.method === routeTitle!.method && (r.expressPath === routeTitle!.path || r.path === routeTitle!.path),
      );
      if (!route) continue;

      const request = findRequestExample(fn);
      const status = findStatus(fn);
      const responseBody = findResponseBody(fn);
      if (!request && status === undefined && !responseBody) continue;

      examples.push({
        routeId: route.id,
        testFile: testFileRel,
        describeTitle: `${routeTitle.method} ${routeTitle.path}`,
        itTitle,
        ...(request ? { request } : {}),
        ...(status !== undefined || responseBody
          ? {
              response: {
                ...(status !== undefined ? { status } : {}),
                ...(responseBody ? { body: responseBody.body, partial: responseBody.partial } : {}),
              },
            }
          : {}),
      });
    }
  }

  return examples;
}
