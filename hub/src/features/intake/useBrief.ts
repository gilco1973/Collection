import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "../../api";
import { newId } from "../../api/client";
import { ApiError, ConflictError, ForbiddenError, ValidationError } from "../../api/errors";
import { BRIEF_STEPS, briefContentSchema, issuesToFieldErrors, validateStep, type BriefContent, type BriefStepKey, type FieldErrors } from "../../api/schemas";
import type { Brief } from "../../api/types";
import { track } from "../../telemetry";
import { withBaseline } from "../../api/baseline";

/**
 * State for one intake brief: the server's copy (react-query), the person's
 * working copy (local), and the autosave that keeps the two in step.
 *
 * - Every edit marks the draft dirty and schedules a PATCH after a short pause.
 * - Every PATCH carries `If-Match` with the etag last seen; a 409 means the
 *   draft changed in another tab, and the form stops saving until reloaded.
 * - Continue validates the step locally with the same zod schema the server
 *   applies on file, so the person never reaches a 422 they could not see.
 */
export type SaveState = "saved" | "dirty" | "saving" | "conflict" | "error";

const AUTOSAVE_MS = 1200;

export function useBrief(id: string | undefined) {
  const qc = useQueryClient();
  const query = useQuery({
    queryKey: ["brief", id],
    queryFn: ({ signal }) => api.briefs.get(id!, signal),
    enabled: !!id,
    staleTime: Infinity,
  });

  const [content, setContent] = useState<BriefContent | null>(null);
  const [step, setStepState] = useState<BriefStepKey>("useCase");
  const [completed, setCompleted] = useState<BriefStepKey[]>([]);
  const [saveState, setSaveState] = useState<SaveState>("saved");
  const [saveDetail, setSaveDetail] = useState<string | undefined>();   // why the last save failed, when the reason changes what to do
  const filed = useRef(false);                                           // once filing starts, the autosave stays out of the way
  const [errors, setErrors] = useState<FieldErrors>({});
  const [fileError, setFileError] = useState<string | undefined>();
  const etag = useRef<string>("");
  const timer = useRef<number | undefined>();
  const inFlight = useRef<Promise<void> | null>(null);
  const loadedFor = useRef<string | undefined>();

  // Adopt the server copy once per brief id, and again after a reload.
  useEffect(() => {
    const b = query.data;
    if (!b || loadedFor.current === b.id) return;
    loadedFor.current = b.id;
    etag.current = b.etag;
    setContent(b.content);
    setStepState(b.currentStep);
    setCompleted(b.completed);
    setSaveState("saved");
    setErrors({});
  }, [query.data]);

  const patch = useMutation({
    mutationFn: (body: { content?: BriefContent; currentStep?: BriefStepKey; completed?: BriefStepKey[] }) => api.briefs.save(id!, etag.current, body),
    onSuccess: (b) => {
      etag.current = b.etag;
      qc.setQueryData(["brief", id], b);
    },
  });

  const save = useCallback(
    async (next?: { step?: BriefStepKey; completed?: BriefStepKey[] }) => {
      if (!id || !content || saveState === "conflict") return;
      window.clearTimeout(timer.current);
      if (inFlight.current) await inFlight.current.catch(() => undefined);
      setSaveState("saving");
      const run = patch
        .mutateAsync({ content, currentStep: next?.step ?? step, completed: next?.completed ?? completed })
        .then(() => setSaveState("saved"))
        .catch((e: unknown) => {
          setSaveState(e instanceof ConflictError ? "conflict" : "error");
          setSaveDetail(e instanceof ApiError && e.status === 413 ? "This section is too long; shorten it (a draft saves at most 64 KB at a time)." : undefined);
          throw e;
        })
        .finally(() => {
          inFlight.current = null;
        });
      inFlight.current = run.catch(() => undefined);
      return run;
    },
    [id, content, saveState, step, completed, patch],
  );

  // Debounced autosave: reschedule on every edit while dirty.
  useEffect(() => {
    if (saveState !== "dirty" || filed.current) return;
    timer.current = window.setTimeout(() => {
      void save().catch(() => undefined);
    }, AUTOSAVE_MS);
    return () => window.clearTimeout(timer.current);
  }, [saveState, content, save]);

  const update = useCallback(<K extends BriefStepKey>(section: K, fields: Partial<BriefContent[K]>) => {
    setContent((c) => (c ? { ...c, [section]: { ...c[section], ...fields } } : c));
    setSaveState((s) => (s === "conflict" ? s : "dirty"));
    // Clear the errors for the fields just edited so the message goes away as the person types.
    setErrors((e) => {
      const next = { ...e };
      for (const k of Object.keys(fields)) delete next[`${section}.${k}`];
      return next;
    });
  }, []);

  const goTo = useCallback(
    (target: BriefStepKey) => {
      setStepState(target);
      setErrors({});
      track("brief.step", { step: target });
      void save({ step: target }).catch(() => undefined);
    },
    [save],
  );

  /** Validate the current step; on success mark it complete and move on. */
  const next = useCallback(async () => {
    if (!content) return false;
    const errs = validateStep(step, content[step]);
    if (Object.keys(errs).length) {
      setErrors(errs);
      return false;
    }
    const i = BRIEF_STEPS.indexOf(step);
    const target = BRIEF_STEPS[Math.min(i + 1, BRIEF_STEPS.length - 1)];
    const done = completed.includes(step) ? completed : [...completed, step];
    setCompleted(done);
    setStepState(target);
    setErrors({});
    track("brief.step", { step: target, completed: done.length });
    await save({ step: target, completed: done }).catch(() => undefined);
    return true;
  }, [content, step, completed, save]);

  const back = useCallback(() => {
    const i = BRIEF_STEPS.indexOf(step);
    if (i > 0) goTo(BRIEF_STEPS[i - 1]);
  }, [step, goTo]);

  const fileKey = useRef(newId());
  const file = useMutation({
    mutationFn: async () => {
      if (!id || !content) throw new Error("no brief");
      window.clearTimeout(timer.current); filed.current = true;  // a pending autosave would PATCH the filed brief and read as a conflict
      const parsed = briefContentSchema.safeParse(content);
      if (!parsed.success) {
        const errs = issuesToFieldErrors(parsed.error.issues);
        setErrors(errs);
        const first = BRIEF_STEPS.find((s) => Object.keys(errs).some((k) => k.startsWith(`${s}.`)));
        if (first) setStepState(first);
        throw new ValidationError({
          type: "about:blank",
          title: "The brief is not complete",
          status: 422,
          detail: "Some sections need attention before it can be filed.",
          errors: errs,
        });
      }
      // The harness baseline comes with any tool: written into the brief here, and again by the server, so the record names it.
      const merged = withBaseline(content);
      if (merged !== content) {
        setContent(merged);
        await patch.mutateAsync({ content: merged, currentStep: step, completed });
      } else await save().catch(() => undefined);
      return api.briefs.file(id, etag.current, fileKey.current);
    },
    onSuccess: (b) => {
      etag.current = b.etag;
      qc.setQueryData(["brief", id], b);
      // Update the list in place so no stale window shows the filed brief as a draft.
      qc.setQueryData<Brief[]>(["briefs"], (old) => old?.map((x) => (x.id === b.id ? b : x)));
      qc.invalidateQueries({ queryKey: ["workspace"] });
      qc.invalidateQueries({ queryKey: ["briefs"] });
      track("brief.filed", { road: b.road ?? "" });
    },
    onError: (e: unknown) => {
      fileKey.current = newId(); filed.current = false;
      if (e instanceof ValidationError) {
        setErrors((cur) => ({ ...cur, ...e.fieldErrors }));
        setFileError(e.problem?.detail ?? e.message);
      } else if (e instanceof ForbiddenError) setFileError(e.problem?.detail ?? "You cannot file this brief.");
      else if (e instanceof ConflictError) setSaveState("conflict");
      else setFileError(e instanceof ApiError ? e.supportLine : (e as Error).message);
    },
  });

  const reload = useCallback(async () => {
    loadedFor.current = undefined;
    setFileError(undefined);
    await qc.invalidateQueries({ queryKey: ["brief", id] });
  }, [qc, id]);

  const stepIndex = BRIEF_STEPS.indexOf(step);
  const canVisit = useCallback(
    (s: BriefStepKey) => {
      const i = BRIEF_STEPS.indexOf(s);
      // Completed steps, the current one, and the first not-yet-completed step.
      return completed.includes(s) || i <= stepIndex || i === completed.length;
    },
    [completed, stepIndex],
  );

  return useMemo(
    () => ({
      brief: query.data as Brief | undefined,
      loading: query.isPending && !!id,
      error: query.error,
      content,
      step,
      stepIndex,
      completed,
      saveState,
      saveDetail,
      errors,
      fileError,
      update,
      goTo,
      next,
      back,
      save,
      reload,
      canVisit,
      file: () => file.mutateAsync().catch(() => undefined),
      filing: file.isPending,
      setErrors,
    }),
    [
      query.data,
      query.isPending,
      query.error,
      id,
      content,
      step,
      stepIndex,
      completed,
      saveState,
      saveDetail,
      errors,
      fileError,
      update,
      goTo,
      next,
      back,
      save,
      reload,
      canVisit,
      file,
    ],
  );
}

export type BriefState = ReturnType<typeof useBrief>;
