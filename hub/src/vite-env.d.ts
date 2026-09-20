/// <reference types="vite/client" />
interface ImportMetaEnv {
  readonly VITE_ROUTER?: "hash" | "browser";
}
interface ImportMeta {
  readonly env: ImportMetaEnv;
}
