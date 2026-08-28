import { defineConfig, type Plugin } from 'vite'
import react from '@vitejs/plugin-react'

const backendPort = process.env.HCM_E2E_BACKEND_PORT ?? '8000'
const backendTarget = `http://127.0.0.1:${backendPort}`

// Recorded chunk-size budget (regulatory review P0.3: "record a chunk-size
// budget and fail... when it regresses", not just suppress Vite's generic
// 500 kB warning). Keyed by the chunk's stable `name` (Vite/rolldown's
// pre-hash identifier -- the hashed `fileName` like
// "assets/index-Ab12Cd34.js" is not stable across builds). Both entries
// here are KNOWN, accepted-for-now exceptions -- the budget is a ceiling
// against further growth, not an endorsement that these sizes are fine
// long-term. Shrinking `index` further is tracked in latest_todo.md P3.
//
// `face-api.esm` (2026-08-28, HR_Code_report.md M4): face-api.js/
// TensorFlow.js used to inflate MyIdentityVerificationPage's own chunk to
// 1.31 MB purely from a static top-level import, downloaded and parsed the
// moment someone opened that route. It's now a dynamic import() inside
// faceApi.ts's loadModels(), only awaited once CameraCapture's own "Start
// camera" button is clicked -- so it lands in its own vendor chunk here,
// and MyIdentityVerificationPage's chunk dropped to ~6 kB.
const CHUNK_SIZE_BUDGET_KB: Record<string, number> = {
  index: 650,
  'face-api.esm': 1400,
}

function chunkSizeBudget(): Plugin {
  return {
    name: 'chunk-size-budget',
    generateBundle(_options, bundle) {
      const overBudget: string[] = []
      for (const file of Object.values(bundle)) {
        if (file.type !== 'chunk') continue
        const budgetKb = CHUNK_SIZE_BUDGET_KB[file.name]
        if (budgetKb === undefined) continue
        const sizeKb = Buffer.byteLength(file.code, 'utf8') / 1024
        if (sizeKb > budgetKb) {
          overBudget.push(`${file.fileName} (chunk "${file.name}"): ${sizeKb.toFixed(0)} kB > ${budgetKb} kB budget`)
        }
      }
      if (overBudget.length > 0) {
        this.error(
          `Chunk-size budget exceeded (config/vite.config.ts CHUNK_SIZE_BUDGET_KB):\n${overBudget.join('\n')}`,
        )
      }
    },
  }
}

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), chunkSizeBudget()],
  server: {
    // Proxies API + admin calls to the Django dev server so the browser
    // only ever talks to one origin (localhost:5173) — avoids CORS and
    // keeps the session cookie same-site, matching the single-host
    // reverse-proxy shape production uses (ADR-005).
    proxy: {
      '/api': backendTarget,
      '/admin': backendTarget,
    },
  },
})
