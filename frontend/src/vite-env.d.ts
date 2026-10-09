/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** "1" para usar datos de ejemplo en lugar de la API (make web-mocks) */
  readonly VITE_USE_MOCKS?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
