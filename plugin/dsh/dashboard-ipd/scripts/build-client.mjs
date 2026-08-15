/**
 * Build the browser bundle for dashboard-ipd: esbuild CJS bundle wrapped in
 * the dsh client-module contract (`window.__ModuleLoader__.load({ id, factory })`).
 * Externals resolve through the browser's module loader, not Node.
 */
import { build } from 'esbuild'
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const pkg = JSON.parse(readFileSync(resolve(root, 'package.json'), 'utf8'))

const result = await build({
  entryPoints: [resolve(root, 'src/client/index.ts')],
  bundle: true,
  format: 'cjs',
  platform: 'browser',
  target: ['es2020'],
  jsx: 'automatic',
  external: ['react', 'react/jsx-runtime', '@deepseek-ai/*'],
  write: false,
  logLevel: 'info',
})

const code = result.outputFiles[0].text.trim()
const indented = code.split('\n').map(line => `\t${line}`).join('\n')
// 浏览器 loader 契约 (dsh-client-modules): 调 factory(require) 并取其返回值作为
// 模块导出 —— 与 in-repo tsdown clientBundle 一致:
//   intro: var module/exports;  footer: return module.exports;
// 缺 prologue → esbuild 尾部 module.exports=... 抛 module is not defined;
// 缺 return → factory 返回 undefined → "invalid plugin, received undefined"。
const prologue = '\tvar module = { exports: {} };\n\tvar exports = module.exports;\n'
  + '\tObject.defineProperty(exports, Symbol.toStringTag, { value: "Module" });\n'
const wrapped = `window.__ModuleLoader__.load({\n\tid: ${JSON.stringify(pkg.name)},\n\tfactory: (require) => {\n${prologue}${indented}\n\treturn module.exports;\n\t}\n})\n`
mkdirSync(resolve(root, 'lib'), { recursive: true })
writeFileSync(resolve(root, 'lib/client.js'), wrapped)
console.log(`client bundle: lib/client.js (${wrapped.length} bytes)`)
