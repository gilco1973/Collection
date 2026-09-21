import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "../../api";
import { newId } from "../../api/client";
import { ApiError } from "../../api/errors";
import type { Conversation, Turn, View } from "../../api/types";
import { track } from "../../telemetry";

/**
 * One conversation with an assistant, as the person sees it: the server's
 * turns plus the turn in flight. Sending opens a `text/event-stream`; each
 * view event is appended as it arrives, so the answer reads while it is
 * written. Stop aborts the request; the harness records that as
 * `human.interrupt` (PLT-HAR-29, PLT-UI-10).
 */
export type StreamState = "idle" | "sending" | "streaming" | "error";

export function useConversation(id: string | undefined, assistantId: string) {
  const qc = useQueryClient();
  const query = useQuery({ queryKey: ["conversation", id], queryFn: ({ signal }) => api.conversations.get(id!, signal), enabled: !!id });
  const [live, setLive] = useState<{ user: Turn; assistant: Turn } | null>(null);
  const [state, setState] = useState<StreamState>("idle");
  const [error, setError] = useState<string | undefined>();
  const [errorDetail, setErrorDetail] = useState<string | undefined>();
  const abort = useRef<AbortController | null>(null);
  const [answeredHere, setAnswered] = useState<Record<string, boolean>>({});
  // What the record says was answered (survives a reload), plus what was answered in this session.
  const answered = useMemo<Record<string, boolean>>(
    () => ({ ...Object.fromEntries((query.data?.feedback ?? []).map((f) => [String(f.seq), f.answered])), ...answeredHere }),
    [query.data?.feedback, answeredHere],
  );
  const streaming = useRef<string | undefined>(undefined);  // the conversation the live turn belongs to
  const selected = useRef(id);
  useEffect(() => {
    selected.current = id;
    if (streaming.current !== id) setLive(null);  // a turn streaming for another conversation never shows under this one
  }, [id]);

  // A new conversation is created on the first send, never on open (no empty records).
  const create = useMutation({ mutationFn: (aid: string) => api.conversations.create(aid, newId()) });

  const hhmm = () => new Date().toTimeString().slice(0, 5);

  const send = useCallback(
    async (text: string, onCreated?: (c: Conversation) => void) => {
      const t = text.trim();
      if (!t || state === "streaming" || state === "sending") return;
      setError(undefined); setErrorDetail(undefined);
      setState("sending");
      let cid = id;
      try {
        if (!cid) {
          const c = await create.mutateAsync(assistantId);
          cid = c.id;
          qc.setQueryData(["conversation", c.id], c);
          onCreated?.(c);
        }
        const user: Turn = { id: `local_${newId()}`, role: "user", at: hhmm(), views: [{ kind: "text", text: t, provenance: "system" }] };
        const assistant: Turn = { id: `local_${newId()}`, role: "assistant", at: hhmm(), views: [] };
        streaming.current = cid;
        if (selected.current === cid) setLive({ user, assistant });
        const ctrl = new AbortController();
        abort.current = ctrl;
        track("assistant.turn_sent", { assistantId, chars: t.length });
        setState("streaming");
        for await (const ev of api.conversations.send(cid, t, newId(), ctrl.signal)) {
          assistant.views = [...assistant.views, ev.view];
          if (selected.current === cid) setLive({ user, assistant: { ...assistant } });
        }
        setState("idle");
      } catch (e) {
        if (abort.current?.signal.aborted) {
          // Stopped by the person: the server records the interrupt; show it at once.
          setLive((l) =>
            l
              ? { ...l, assistant: { ...l.assistant, views: [...l.assistant.views, { kind: "stop", reason: "human.interrupt", message: "Stopped." } as View] } }
              : l,
          );
          track("assistant.stopped", { assistantId });
          setState("idle");
        } else {
          // The platform's sentence first (the ceiling, a lost entitlement, a body too large); the support line beside it.
          setError(e instanceof ApiError ? (e.problem?.detail ?? e.message) : "The connection dropped before the answer finished. Send again.");
          setErrorDetail(e instanceof ApiError ? e.supportLine : undefined);
          setState("error");
        }
      } finally {
        abort.current = null;
        // Refresh the server's copy so the list title and the recorded turns are the truth.
        await qc.invalidateQueries({ queryKey: ["conversation", cid] });
        qc.invalidateQueries({ queryKey: ["conversations"] });
      }
    },
    [id, assistantId, state, create, qc],
  );

  // Once the server copy includes the live turns, drop the local ones.
  useEffect(() => {
    if (!live || state === "streaming" || state === "sending") return;
    const serverText = query.data?.turns
      .filter((t) => t.role === "user")
      .map((t) => (t.views[0]?.kind === "text" ? t.views[0].text : ""))
      .pop();
    const liveText = live.user.views[0]?.kind === "text" ? live.user.views[0].text : "";
    if (serverText === liveText && query.data?.turns[query.data.turns.length - 1]?.role === "assistant") setLive(null);
  }, [query.data, live, state]);

  const stop = useCallback(() => {
    abort.current?.abort();
  }, []);

  const feedback = useMutation({
    mutationFn: ({ seq, yes }: { seq: number; yes: boolean }) => api.conversations.feedback(id!, seq, yes),
    onSuccess: (_r, v) => {
      setAnswered((a) => ({ ...a, [v.seq]: v.yes }));
      track("assistant.feedback", { assistantId, answered: v.yes });
    },
  });

  const handoff = useMutation({
    mutationFn: () => api.conversations.handoff(id!, newId()),
    onSuccess: (r) => {
      track("assistant.handoff", { assistantId, route: r.route });
      qc.setQueryData<Conversation>(["conversation", id], (c) =>
        c
          ? {
              ...c,
              turns: [
                ...c.turns,
                {
                  id: `h_${newId()}`,
                  role: "assistant",
                  at: hhmm(),
                  views: [{ kind: "handoff", route: r.route as "human", expected_wait_s: r.expected_wait_s }],
                },
              ],
            }
          : c,
      );
    },
  });

  const turns: Turn[] = [...(query.data?.turns ?? []), ...(live ? [live.user, live.assistant] : [])];
  return {
    conversation: query.data,
    loading: !!id && query.isPending,
    loadError: query.error,
    turns,
    state,
    error,
    errorDetail,
    send,
    stop,
    feedback,
    handoff,
    answered,
    streamingTurnId: state === "streaming" ? live?.assistant.id : undefined,
  };
}
