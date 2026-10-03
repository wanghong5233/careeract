import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import ts from "typescript";

const require = createRequire(import.meta.url);

export function loadSource(relative, dependencies = {}, globals = {}) {
  const filename = new URL(`../src/${relative}`, import.meta.url);
  const source = readFileSync(filename, "utf8");
  const { outputText } = ts.transpileModule(source, {
    fileName: filename.pathname,
    compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS },
  });
  const loaded = { exports: {} };
  const importDependency = name => {
    if (Object.hasOwn(dependencies, name)) return dependencies[name];
    if (name.startsWith("@/")) throw new Error(`Test requires explicit dependency: ${name}`);
    return require(name);
  };
  new Function("require", "module", "exports", ...Object.keys(globals), outputText)(
    importDependency, loaded, loaded.exports, ...Object.values(globals),
  );
  return loaded.exports;
}
