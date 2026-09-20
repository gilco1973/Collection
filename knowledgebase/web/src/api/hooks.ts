import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, api } from "./client";
import type { StartAuditBody } from "./types";

const RUNNING_POLL_MS = 3000;
const LIST_POLL_MS = 5000;

export const useMe = () => useQuery({ queryKey: ["me"], queryFn: api.me });
export const useContract = () => useQuery({ queryKey: ["contract"], queryFn: api.contract });
export const useSections = (lang?: string) => useQuery({ queryKey: ["sections", lang], queryFn: () => api.sections(lang) });
export const useSectionPages = (id: string | undefined, lang?: string) =>
  useQuery({ queryKey: ["section-pages", id, lang], queryFn: () => api.sectionPages(id!, lang), enabled: !!id });
export const usePage = (path: string, lang?: string) =>
  useQuery({ queryKey: ["page", path, lang], queryFn: () => api.page(path, lang), enabled: !!path });
export const usePageFindings = (path: string) =>
  useQuery({ queryKey: ["page-findings", path], queryFn: () => api.pageFindings(path), enabled: !!path });
export const useStalePages = (lang?: string) =>
  useQuery({ queryKey: ["pages", "stale", lang], queryFn: () => api.pages({ stale: "true", lang }) });
export const useSearch = (params: Record<string, string | undefined>) =>
  useQuery({ queryKey: ["search", params], queryFn: () => api.search(params), placeholderData: keepPreviousData });

/** The list polls while any listed audit is still running. */
export const useAudits = (params: Record<string, string | undefined> = {}) =>
  useQuery({
    queryKey: ["audits", params],
    queryFn: () => api.audits(params),
    placeholderData: keepPreviousData,
    refetchInterval: (q) => (q.state.data?.items.some((a) => a.status === "in_progress") ? LIST_POLL_MS : false),
  });

/** Polling is derived from the data itself, so it stops the moment the audit reaches a terminal state. */
export const useAudit = (id: string | undefined) =>
  useQuery({
    queryKey: ["audit", id],
    queryFn: () => api.audit(id!),
    enabled: !!id,
    refetchInterval: (q) => (q.state.data?.status === "in_progress" ? RUNNING_POLL_MS : false),
  });

export function useStartAudit() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: StartAuditBody) => api.startAudit(body),
    onSuccess: () => client.invalidateQueries({ queryKey: ["audits"] }),
  });
}

export function useCancelAudit(id: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => api.cancelAudit(id),
    onSettled: () => Promise.all([client.invalidateQueries({ queryKey: ["audit", id] }), client.invalidateQueries({ queryKey: ["audits"] })]),
  });
}

export function useRollback(id: string, actionId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: { reason: string; force: boolean }) => api.rollback(id, actionId, body),
    onSuccess: (result) =>
      Promise.all([
        client.invalidateQueries({ queryKey: ["audit", id] }),
        client.invalidateQueries({ queryKey: ["audits"] }),
        client.invalidateQueries({ queryKey: ["page", result.action.path] }),
        client.invalidateQueries({ queryKey: ["page-findings", result.action.path] }),
        client.invalidateQueries({ queryKey: ["pages"] }),
      ]),
  });
}

export function useReportProblem(path: string) {
  return useMutation({ mutationFn: (body: { category: string; message: string }) => api.reportProblem(path, body) });
}

/** Whether a reader is signed in (false while `/api/me` is still loading, so per-user calls never fire early). */
export function useSignedIn(): boolean {
  const me = useMe();
  return !!me.data?.user;
}

export const useProfile = (enabled: boolean) => useQuery({ queryKey: ["profile"], queryFn: api.profile, enabled });

export function useRecordView() {
  const client = useQueryClient();
  return useMutation({ mutationFn: api.recordView, onSuccess: () => client.invalidateQueries({ queryKey: ["profile"] }) });
}

export function useSetPersona() {
  const client = useQueryClient();
  return useMutation({ mutationFn: api.setPersona, onSuccess: (profile) => client.setQueryData(["profile"], profile) });
}

export function useForgetMe() {
  const client = useQueryClient();
  return useMutation({ mutationFn: api.forgetMe, onSettled: () => client.invalidateQueries({ queryKey: ["profile"] }) });
}

/** Signing out clears the session cookie server-side; everything the console cached about "me" is stale after. */
export function useSignOut() {
  const client = useQueryClient();
  return useMutation({ mutationFn: api.signOut, onSettled: () => client.invalidateQueries() });
}

/** Revokes every session of the reader server-side (their session epoch moves); the cache is as stale as after a sign-out. */
export function useSignOutEverywhere() {
  const client = useQueryClient();
  return useMutation({ mutationFn: api.signOutEverywhere, onSettled: () => client.invalidateQueries() });
}

export function useChat() {
  return useMutation({ mutationFn: api.chat });
}

/** The pages written for an audience (a reader's persona); idle until a persona is chosen. */
export const usePagesFor = (audience: string | null | undefined, lang?: string) =>
  useQuery({ queryKey: ["pages", "audience", audience, lang], queryFn: () => api.pages({ audience: audience!, lang }), enabled: !!audience });

/** A graded quiz's tally for the signed-in reader; the profile (and its quiz list) is refetched after. */
export function useRecordQuiz() {
  const client = useQueryClient();
  return useMutation({ mutationFn: api.recordQuiz, onSuccess: () => client.invalidateQueries({ queryKey: ["profile"] }) });
}

/** The stored insights for operators; `null` until a run generated them (the API's 404), so the panel can offer a refresh. */
export const useInsights = (enabled: boolean) =>
  useQuery({
    queryKey: ["insights"],
    queryFn: async () => {
      try {
        return await api.insights();
      } catch (error) {
        if (error instanceof ApiError && error.status === 404) return null;
        throw error;
      }
    },
    enabled,
    retry: false,
  });

/** Regenerates the insights server-side (`POST /insights/refresh`) and replaces the cached copy with the result. */
export function useRefreshInsights() {
  const client = useQueryClient();
  return useMutation({ mutationFn: api.refreshInsights, onSuccess: (data) => client.setQueryData(["insights"], data) });
}
