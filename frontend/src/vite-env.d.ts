/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL: string
  readonly VITE_MAPBOX_ACCESS_TOKEN: string
  /** Set to "false" to skip initializing the live Mapbox map during dev (saves free-tier map loads). */
  readonly VITE_MAPBOX_ENABLED?: string
  /** Set to "true" to serve listings from a local fixture instead of the backend API. */
  readonly VITE_USE_MOCK_LISTINGS?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
