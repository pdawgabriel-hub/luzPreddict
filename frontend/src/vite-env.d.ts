/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** "1" para usar datos de ejemplo en lugar de la API (make web-mocks) */
  readonly VITE_USE_MOCKS?: string
  /** Con datos de ejemplo, "stale", "error" o "slow" para ver cada estado de la web */
  readonly VITE_MOCK_SCENARIO?: string
  /** Tema público de ntfy del resumen diario (por defecto, "luzpreddict") */
  readonly VITE_NTFY_TOPIC?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
