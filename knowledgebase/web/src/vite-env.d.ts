/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** API prefix the console calls (defaults to `/api`; set when the platform mounts the API elsewhere). */
  readonly VITE_API_BASE?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
