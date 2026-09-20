import { QueryClient } from "@tanstack/react-query";
import { authClient } from "../auth/client";
import { env } from "../config/env";
import { ApiClient, fetchTransport } from "./client";
import { endpoints } from "./endpoints";
import { isTransient } from "./errors";

/**
 * One API client, one query client, built from configuration.
 *
 * `VITE_API_MODE=mock` swaps the transport for the in-process server and
 * nothing else changes: the same client, the same endpoints, the same errors.
 */
async function transport() {
  if (env.VITE_API_MODE === "mock") {
    const { mockTransport } = await import("./mock/server");
    return mockTransport;
  }
  return fetchTransport;
}

let unauthorizedHandler: (() => void) | undefined;
export function onUnauthorized(handler: () => void) {
  unauthorizedHandler = handler;
}

const clientPromise = transport().then(
  (t) => new ApiClient(env.VITE_API_BASE, t, () => authClient.getAccessToken(), { onUnauthorized: () => unauthorizedHandler?.() }),
);

/** Resolved once at boot by `main.tsx`; features import the ready instance. */
export let api!: ReturnType<typeof endpoints>;
export let apiClient!: ApiClient;

export async function initApi() {
  apiClient = await clientPromise;
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
