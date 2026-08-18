// Starts the Django backend for the Playwright suite on a throwaway SQLite
// database: fresh migrate + seed_demo_data every run, then `runserver` on
// 127.0.0.1:8000 (the Vite dev server proxies /api there). Used as a
// Playwright `webServer` (playwright.config.ts); also fine to run by hand.
//
// Python resolution: $PYTHON, else ../backend/venv/Scripts/python.exe (Windows
// dev venv), else ../backend/venv/bin/python, else `python` on PATH (CI).
import { spawn, spawnSync } from 'node:child_process'
import { existsSync, rmSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const here = path.dirname(fileURLToPath(import.meta.url))
const backendDir = path.resolve(here, '..', '..', 'backend')
const dbPath = path.join(backendDir, 'e2e.sqlite3')

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

const python = pickPython()
const env = {
  ...process.env,
  SQLITE_PATH: dbPath,
  DJANGO_DEBUG: '1',
  // Never talk to a real broker from the e2e backend; tasks run inline.
  REDIS_URL: '',
  CELERY_TASK_ALWAYS_EAGER: '1',
  PYTHONUNBUFFERED: '1',
}

function run(args) {
  const r = spawnSync(python, ['manage.py', ...args], { cwd: backendDir, env, stdio: 'inherit' })
  if (r.status !== 0) {
    console.error(`[e2e backend] manage.py ${args.join(' ')} failed (${r.status})`)
    process.exit(r.status ?? 1)
  }
}

if (existsSync(dbPath)) rmSync(dbPath)
console.log(`[e2e backend] python=${python} db=${dbPath}`)
run(['migrate', '--noinput', '-v', '0'])
run(['seed_demo_data'])

const server = spawn(python, ['manage.py', 'runserver', '127.0.0.1:8000', '--noreload'], {
  cwd: backendDir,
  env,
  stdio: 'inherit',
})
const stop = () => {
  server.kill()
  process.exit(0)
}
process.on('SIGINT', stop)
process.on('SIGTERM', stop)
server.on('exit', (code) => process.exit(code ?? 0))
