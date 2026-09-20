import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../../api";
import { newId } from "../../api/client";
import { ApiError, ConflictError, ForbiddenError, ValidationError } from "../../api/errors";
import type { ShelfAttestation, ShelfRole } from "../../api/types";
import { track } from "../../telemetry";
import { useToast } from "../../ui/Toast";

export function useShelf() {
  return useQuery({ queryKey: ["shelf"], queryFn: ({ signal }) => api.shelf.list(signal) });
}

export function useShelfEntry(name: string | undefined) {
  return useQuery({ queryKey: ["shelf", name], queryFn: ({ signal }) => api.shelf.get(name!, signal), enabled: !!name });
}

export type SignBody = { component: string; role: ShelfRole; attest: ShelfAttestation; usedIn?: string; note?: string };

/**
 * Record a sign-off. The server decides who may sign (the owner by name, AI
 * security by role) and refuses a form with an attestation missing; the front
 * end only shows the form to people it expects to succeed. The manifest in the
 * repository stays the record of truth: the queue exports what was recorded
 * here and the shelf tool writes it in, so the commit is the signature.
 */
export function useSign() {
  const qc = useQueryClient();
  const toast = useToast();
  return useMutation({
    mutationFn: ({ component, ...body }: SignBody) => api.shelf.sign(component, body, newId()),
    onSuccess: (r) => {
      track("shelf.signed", { component: r.component, role: r.role, version: r.version });
      qc.invalidateQueries({ queryKey: ["shelf"] });
      qc.invalidateQueries({ queryKey: ["consumer", r.component] });
      toast.notify(
        "ok",
        `Recorded: ${r.role === "owner" ? "owner" : "AI security"} sign-off on ${r.component} ${r.version}.`,
        "Export the queue and apply it with the shelf tool; the commit is the signature.",
      );
    },
    onError: (e: unknown) => {
      if (e instanceof ForbiddenError || e instanceof ConflictError || e instanceof ValidationError)
        toast.notify("crit", e.problem?.title ?? "Not recorded.", e.problem?.detail);
      else toast.notify("crit", "The sign-off could not be recorded.", e instanceof ApiError ? e.supportLine : (e as Error).message);
    },
  });
}

/** Hand the person the file the shelf tool applies. */
export function downloadJson(name: string, body: unknown) {
  const blob = new Blob([JSON.stringify(body, null, 2) + "\n"], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
