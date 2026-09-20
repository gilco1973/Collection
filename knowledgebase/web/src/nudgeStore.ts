import { useSyncExternalStore } from "react";
import { activeDismissals } from "./nudges";

/**
 * What this browser remembers about a reader's suggestions: whether they want them, and which ones they
 * dismissed. Lives in `localStorage` only, under a key derived from the reader's subject, so two readers
 * sharing a browser do not see each other's dismissals. Nothing here is ever sent anywhere.
 */
export interface NudgeState {
  enabled: boolean;
  /** Dismissed nudge id → ISO time of the dismissal (`nudges.ts` decides when one has expired). */
  dismissed: Record<string, string>;
}

const PREFIX = "kb.nudges.";
const DEFAULT: NudgeState = Object.freeze({ enabled: true, dismissed: Object.freeze({}) as Record<string, string> });
const listeners = new Set<() => void>();
/** One parsed snapshot per key, keyed by the raw string it came from, so `useSyncExternalStore` sees a stable value. */
const cache = new Map<string, { raw: string | null; state: NudgeState }>();

/** FNV-1a (32-bit) over the subject: names the reader without spelling the identity provider's id into the key. */
export function storageKey(sub: string): string {
  let hash = 0x811c9dc5;
  for (let i = 0; i < sub.length; i += 1) hash = Math.imul(hash ^ sub.charCodeAt(i), 0x01000193) >>> 0;
  return `${PREFIX}${hash.toString(16).padStart(8, "0")}`;
}

function safeGet(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function parse(raw: string | null): NudgeState {
  if (!raw) return DEFAULT;
  try {
    const data = JSON.parse(raw) as Partial<NudgeState> | null;
    const dismissed = data?.dismissed && typeof data.dismissed === "object" ? data.dismissed : {};
    return { enabled: data?.enabled !== false, dismissed: Object.fromEntries(Object.entries(dismissed).filter(([, at]) => typeof at === "string")) };
  } catch {
    return DEFAULT;
  }
}

function read(sub: string): NudgeState {
  const key = storageKey(sub);
  const raw = safeGet(key);
  const hit = cache.get(key);
  if (hit && hit.raw === raw) return hit.state;
  const state = parse(raw);
  cache.set(key, { raw, state });
  return state;
}

function write(sub: string, state: NudgeState): void {
  const key = storageKey(sub);
  let raw: string | null = JSON.stringify(state);
  try {
    localStorage.setItem(key, raw);
  } catch {
    raw = safeGet(key); // storage refused it: keep the change for this session, matched against whatever is stored
  }
  cache.set(key, { raw, state });
  listeners.forEach((notify) => notify());
}

export function readNudgeState(sub: string): NudgeState {
  return read(sub);
}

/** Remember a dismissal; expired ones are dropped at the same time so the entry never grows. */
export function dismissNudge(sub: string, id: string, now = Date.now()): void {
  const current = read(sub);
  const kept = Object.fromEntries(activeDismissals(current.dismissed, now).map((k) => [k, current.dismissed[k]]));
  write(sub, { enabled: current.enabled, dismissed: { ...kept, [id]: new Date(now).toISOString() } });
}

export function setNudgesEnabled(sub: string, enabled: boolean): void {
  const current = read(sub);
  if (current.enabled !== enabled) write(sub, { ...current, enabled });
}

/** Forget everything kept for this reader — the "Delete my data" flow calls it so no page path lingers here. */
export function clearNudgeState(sub: string | undefined): void {
  if (!sub) return;
  const key = storageKey(sub);
  try {
    localStorage.removeItem(key);
  } catch {
    /* nothing stored, or storage unavailable: the in-memory snapshot is reset either way */
  }
  cache.set(key, { raw: safeGet(key), state: DEFAULT });
  listeners.forEach((notify) => notify());
}

function subscribe(onChange: () => void): () => void {
  listeners.add(onChange);
  return () => listeners.delete(onChange);
}

/** The reader's suggestion state; re-renders the caller on every dismissal or toggle. Anonymous readers get the defaults. */
export function useNudgeState(sub: string | undefined): NudgeState {
  return useSyncExternalStore(subscribe, () => (sub ? read(sub) : DEFAULT));
}
