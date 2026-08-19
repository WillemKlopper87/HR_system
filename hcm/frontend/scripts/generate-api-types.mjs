// Regenerates src/api/generated-types.ts from the live Django OpenAPI schema
// (H3). Two steps, two separate toolchains:
//
//   1. `manage.py spectacular` dumps the schema as JSON (drf-spectacular,
//      already a backend dependency).
//   2. `openapi-typescript` turns that JSON into TS types -- run from
//      tools/api-codegen/, a *separate* node_modules pinned to TypeScript 5.
//      openapi-typescript 7.x calls the `typescript` compiler API directly
//      (ts.factory.createKeywordTypeNode); as of this writing it breaks
//      under this project's TypeScript 7 with "Cannot read properties of
//      undefined" because Node module resolution would otherwise pick up
//      the nearest `typescript` package (this project's 7.x) over
//      openapi-typescript's own declared `^5.x` peer. Isolating it in its
//      own directory's node_modules is what lets both TS versions coexist.
//
// Usage: npm run generate:api-types  (from hcm/frontend)
import { spawnSync } from 'node:child_process'
import { existsSync, mkdtempSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const here = path.dirname(fileURLToPath(import.meta.url))
const frontendDir = path.resolve(here, '..')
const backendDir = path.resolve(frontendDir, '..', 'backend')
const codegenDir = path.join(frontendDir, 'tools', 'api-codegen')
const outFile = path.join(frontendDir, 'src', 'api', 'generated-types.ts')

function pickPython() {
  if (process.env.PYTHON) return process.env.PYTHON
  const candidates = [
    path.join(backendDir, 'venv', 'Scripts', 'python.exe'),
    path.join(backendDir, 'venv', 'bin', 'python'),
    path.join(backendDir, '.venv', 'Scripts', 'python.exe'),
    path.join(backendDir, '.venv', 'bin', 'python'),
  ]
  return candidates.find((c) => existsSync(c)) ?? 'python'
}

function run(cmd, args, opts) {
  const r = spawnSync(cmd, args, { stdio: 'inherit', ...opts })
  if (r.status !== 0) {
    console.error(`[generate-api-types] ${cmd} ${args.join(' ')} failed (${r.status})`)
    process.exit(r.status ?? 1)
  }
}

if (!existsSync(codegenDir)) {
  console.error(`[generate-api-types] ${codegenDir} is missing -- run "npm install" inside tools/api-codegen/ first.`)
  process.exit(1)
}

const tmpDir = mkdtempSync(path.join(tmpdir(), 'hcm-openapi-'))
const schemaPath = path.join(tmpDir, 'schema.json')

try {
  console.log('[generate-api-types] dumping schema from Django...')
  run(pickPython(), ['manage.py', 'spectacular', '--file', schemaPath, '--format', 'openapi-json'], { cwd: backendDir })

  console.log('[generate-api-types] running openapi-typescript (TS 5 scope)...')
  // Invoke the CLI's actual JS entry point with this process's own `node`,
  // not the .bin/ shell shim (a .cmd batch file on Windows, which
  // spawnSync can't execute directly without `shell: true` -- easier and
  // more portable to just skip the shim).
  const cli = path.join(codegenDir, 'node_modules', 'openapi-typescript', 'bin', 'cli.js')
  run(process.execPath, [cli, schemaPath, '-o', outFile], { cwd: codegenDir })

  console.log(`[generate-api-types] wrote ${path.relative(frontendDir, outFile)}`)
} finally {
  rmSync(tmpDir, { recursive: true, force: true })
}
