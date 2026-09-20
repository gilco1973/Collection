import { useSyncExternalStore } from "react";
import type { ChatContext, ChatMode } from "./api/chatTypes";

/**
 * A request to the floating chat widget from elsewhere in the console: the selection toolbar on a
 * page ("Explain" / "Elaborate" / "Quiz me" on the selected text) or a link that opens a page with
 * `?quiz=1`. The widget subscribes with `useChatRequest()`; each `openChat` gets a fresh `seq`, so an
 * identical request made twice is still handled twice.
 */
export interface ChatRequest {
  mode: ChatMode;
  context?: ChatContext;
  seq: number;
}

let current: ChatRequest | null = null;
let seq = 0;
const listeners = new Set<() => void>();

export function openChat(request: Omit<ChatRequest, "seq">): void {
  current = { ...request, seq: ++seq };
  listeners.forEach((notify) => notify());
}

/** Forget the last request (tests: a freshly mounted widget must not replay an earlier test's request). */
export function resetChatBus(): void {
  current = null;
}

function subscribe(onChange: () => void): () => void {
  listeners.add(onChange);
  return () => listeners.delete(onChange);
}

/** The latest request, or null; re-renders the caller on every `openChat`. */
export function useChatRequest(): ChatRequest | null {
  return useSyncExternalStore(subscribe, () => current);
}
