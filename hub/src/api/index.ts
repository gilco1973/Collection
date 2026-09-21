import { QueryClient } from "@tanstack/react-query";
import { authClient } from "../auth/client";
import { loadEnv } from "../config/env";
import { ApiClient, fetchTransport, type Transport } from "./client";
import { endpoints } from "./endpoints";
import { isTransient } from "./errors";

/**
 * One API client, one query client, built from configuration.
 *
 * `VITE_API_MODE=mock` swaps the transport for the in-process server and
 * nothing else changes: the same client, the same endpoints, the same errors.
 * The mock server is a lazy chunk in every build; one prebuilt dist serves the
 * sandbox (hub-api with mock identity says `HUB_ALLOW_MOCK` in /config.js) and
 * production alike. `loadEnv()` is the gate: a production build never resolves
 * to mock unless the configuration that names it also allows it.
 */
async function transport(mode: "http" | "mock"): Promise<Transport> {
  if (mode !== "mock") return fetchTransport;
  const { mockTransport } = await import("./mock/server");
  return mockTransport;
}

let unauthorizedHandler: (() => void) | undefined;
export function onUnauthorized(handler: () => void) {
  unauthorizedHandler = handler;
}

/** Resolved once at boot by `main.tsx`; features import the ready instance. */
export let api!: ReturnType<typeof endpoints>;
export let apiClient!: ApiClient;

/** Load the configuration (a bad one throws a readable error here, before any route renders) and build the client. */
export async function initApi() {
  const env = loadEnv();
  const t = await transport(env.VITE_API_MODE);
  apiClient = new ApiClient(env.VITE_API_BASE, t, () => authClient.getAccessToken(), { onUnauthorized: () => unauthorizedHandler?.() });
  api = endpoints(apiClient);
  return api;
}

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      refetchOnWindowFocus: false,
      // Retry only what is safe and likely to succeed: transient failures on reads.
      retry: (count, error) => count < 2 && isTransient(error),
    },
    mutations: { retry: false },
  },
});
