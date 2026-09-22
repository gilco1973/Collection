import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useRef } from "react";
import { api } from "../../api";
import { newId } from "../../api/client";
import { ApiError, ForbiddenError } from "../../api/errors";
import type { AccessRequest } from "../../api/types";
import { track } from "../../telemetry";
import { useToast } from "../../ui/Toast";

export type CreateRequestBody = { kind: AccessRequest["kind"]; consumerId?: string; ladder?: string; reason?: string };

/**
 * Ask for access, a role, or a higher ladder on a consumer. The platform's
 * policy engine decides; the front end only routes the ask (spec §8.6). The
 * workspace's request list and the catalog refresh on success so the new
 * state shows everywhere at once.
 */
export function useCreateRequest() {
  const qc = useQueryClient();
  const toast = useToast();
  // One ask in flight per (kind, consumer, ladder): a second click while it runs joins the first, with the same key.
  const inflight = useRef(new Map<string, Promise<AccessRequest>>());
  return useMutation({
    mutationFn: (body: CreateRequestBody) => {
      const k = JSON.stringify([body.kind, body.consumerId ?? "", body.ladder ?? ""]);
      const running = inflight.current.get(k);
      if (running) return running;
      const p = api.requests.create(body, newId()).finally(() => inflight.current.delete(k));
      inflight.current.set(k, p);
      return p;
    },
    onSuccess: (r, body) => {
      track("request.created", { kind: body.kind, consumerId: body.consumerId ?? "" });
      qc.invalidateQueries({ queryKey: ["workspace"] });
      qc.invalidateQueries({ queryKey: ["requests"] });
      qc.invalidateQueries({ queryKey: ["catalog"] });
      qc.invalidateQueries({ queryKey: ["consumer"] });
      toast.notify("ok", "Request sent.", `${r.title} · ${r.note}`);
    },
    onError: (e: unknown) => {
      if (e instanceof ForbiddenError) toast.notify("crit", e.problem?.title ?? "Not allowed.", e.problem?.detail);
      else if (e instanceof ApiError && e.status === 409) {
        // Already asked, or already granted: this tab is stale. Refresh what it shows so it stops offering the button.
        toast.notify("warn", e.problem?.title ?? "Already asked.", e.problem?.detail);
        qc.invalidateQueries({ queryKey: ["workspace"] });
        qc.invalidateQueries({ queryKey: ["requests"] });
        qc.invalidateQueries({ queryKey: ["catalog"] });
        qc.invalidateQueries({ queryKey: ["consumer"] });
      } else toast.notify("crit", "The request could not be sent.", e instanceof ApiError ? (e.problem?.detail ?? e.supportLine) : (e as Error).message);
    },
  });
}
