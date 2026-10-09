import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// En local, la API (make api) corre aparte: Vite le reenvía estas rutas y el
// navegador ve un solo origen, como en Vercel, donde web y API comparten dominio.
// Con barra final: una página de la web que empiece igual (p. ej. /api-algo) no va a la API.
const API_URL = process.env.API_URL ?? 'http://localhost:8000'
const API_PATHS = ['/api/', '/v1/', '/health']

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
    proxy: Object.fromEntries(API_PATHS.map((path) => [path, { target: API_URL, changeOrigin: true }])),
  },
})
