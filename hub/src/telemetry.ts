import { env } from "./config/env";

/**
 * Front-end telemetry with one sink.
 *
 * The platform's telemetry service (spec §4.13) expects OpenTelemetry with an
 * allowlisted attribute set and no content capture (PLT-TEL-12). This module is
 * the seam where the OpenTelemetry web SDK plugs in; until then events go to
 * the console in development and nowhere in production. Callers never put
 * prompt text, tool arguments or personal data in attributes.
 */
export type Attributes = Record<string, string | number | boolean | undefined>;

type Sink = (name: string, attrs: Attributes) => void;

let sink: Sink = env.VITE_TELEMETRY === "console" ? (name, attrs) => console.debug(`[telemetry] ${name}`, attrs) : () => {};

export function setTelemetrySink(next: Sink) {
  sink = next;
}

export function track(name: string, attrs: Attributes = {}) {
  sink(name, { ...attrs, build: env.VITE_BUILD_SHA });
}
