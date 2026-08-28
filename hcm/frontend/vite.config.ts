import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const backendPort = process.env.HCM_E2E_BACKEND_PORT ?? '8000'
const backendTarget = `http://127.0.0.1:${backendPort}`

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
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
