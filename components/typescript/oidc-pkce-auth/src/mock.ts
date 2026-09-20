import type { AuthClient } from "./provider";
import type { AuthSnapshot, MockPersona } from "./types";

/**
 * Sign-in for development, demos and tests: pick a persona, get a bearer token
 * of the form `mock.<persona>` that the mock API resolves to a principal.
 *
 * The chosen persona is kept in sessionStorage so a reload stays signed in
 * within the tab. That is a development convenience; the real provider keeps
 * nothing persisted (see `oidc.ts`).
 */
export const MOCK_PERSONAS: MockPersona[] = [
  { id: "gk", label: "Gil Klainert", description: "ops.lead · team-payments-ops · ladder L2" },
  { id: "investigator", label: "Ana Petrov", description: "ops.investigator · team-payments-ops · ladder L1" },
  { id: "employee", label: "Sam Okafor", description: "employee · no team lead role · ladder L0" },
  { id: "platform", label: "Dana Ruiz", description: "platform.lead · reviews briefs and roads" },
];

const KEY = "crai.hub.mockPersona";

export function createMockClient(): AuthClient {
  const listeners = new Set<(s: AuthSnapshot) => void>();
  const emit = (s: AuthSnapshot) => listeners.forEach((l) => l(s));
  const snapshotFor = (id: string): AuthSnapshot => {
    const p = MOCK_PERSONAS.find((x) => x.id === id);
    return p ? { status: "signed-in", accessToken: `mock.${p.id}`, subject: { id: p.id, name: p.label } } : { status: "signed-out" };
  };
  const stored = () => {
    try {
      return window.sessionStorage.getItem(KEY) ?? undefined;
    } catch {
      return undefined;
    }
  };

  return {
    async initialize() {
      const id = stored();
      return id ? snapshotFor(id) : { status: "signed-out" };
    },
    async signIn(opts) {
      const id = opts?.persona ?? MOCK_PERSONAS[0].id;
      try {
        window.sessionStorage.setItem(KEY, id);
      } catch {
        /* private mode: stay signed in for this load only */
      }
      const s = snapshotFor(id);
      emit(s);
      return s;
    },
    async completeSignIn() {
      return { snapshot: await this.initialize() };
    },
    async signOut() {
      try {
        window.sessionStorage.removeItem(KEY);
      } catch {
        /* ignore */
      }
      emit({ status: "signed-out" });
    },
    async getAccessToken() {
      const id = stored();
      return id ? `mock.${id}` : undefined;
    },
    subscribe(listener) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    personas() {
      return MOCK_PERSONAS;
    },
    isCallbackUrl() {
      return false;
    },
  };
}
