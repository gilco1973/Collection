import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../api/errors";
import type { Conversation, TurnEvent } from "../../api/types";

const calls = { send: [] as string[], get: 0 };
let refuse: ApiError | undefined;
const record: Conversation = {
  id: "cnv_1",
  title: "New conversation",
  assistantId: "employee-assistant",
  assistant: { name: "A", sub: "", chips: [] },
  turns: [],
};

vi.mock("../../api", () => ({
  api: {
    conversations: {
      get: async () => {
        calls.get++;
        return structuredClone(record);
      },
      create: async () => structuredClone(record),
      send: async function* (_id: string, text: string): AsyncGenerator<TurnEvent> {
        calls.send.push(text);
        if (refuse) throw refuse;
        yield { seq: 1, view: { kind: "text", provenance: "model", text: "hello" } };
        record.turns.push(
          { id: "t1", role: "user", at: "10:00", views: [{ kind: "text", text, provenance: "system" }] },
          { id: "t2", role: "assistant", at: "10:00", views: [{ kind: "text", provenance: "model", text: "hello" }] },
        );
      },
      feedback: async () => undefined,
      handoff: async () => ({ route: "human", expected_wait_s: 1 }),
    },
  },
}));
vi.mock("../../telemetry", () => ({ track: () => undefined }));

import { useConversation } from "./useConversation";

const wrap = () => {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: { children: ReactNode }) => <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
};

describe("a refused turn", () => {
  beforeEach(() => {
    calls.send = [];
    calls.get = 0;
    record.turns = [];
    refuse = undefined;
  });

  it("leaves no phantom turn, reports false so the draft comes back, and the next send refetches the record", async () => {
    const { result } = renderHook(() => useConversation("cnv_1", "employee-assistant"), { wrapper: wrap() });
    await waitFor(() => expect(result.current.loading).toBe(false));
    const loads = calls.get;
    refuse = new ApiError("busy", 409, {
      status: 409,
      title: "Answer in progress",
      detail: "The assistant is still answering the previous message in this conversation; wait for it to finish.",
      code: "conversation.busy",
    });
    let sent: boolean | undefined;
    await act(async () => {
      sent = await result.current.send("refused while busy");
    });
    expect(sent).toBe(false);
    expect(result.current.state).toBe("error");
    expect(result.current.error).toMatch(/still answering/);
    expect(result.current.turns).toEqual([]);
    expect(result.current.streamingTurnId).toBeUndefined();

    // The retry: the record is read again before the turn streams, then once more after it.
    refuse = undefined;
    await act(async () => {
      sent = await result.current.send("again");
    });
    expect(sent).toBe(true);
    expect(result.current.state).toBe("idle");
    expect(result.current.error).toBeUndefined();
    expect(calls.send).toEqual(["refused while busy", "again"]);
    expect(calls.get).toBeGreaterThanOrEqual(loads + 2);
    await waitFor(() => expect(result.current.turns.map((t) => t.role)).toEqual(["user", "assistant"]));
  });

  it("returns false for an empty message without calling the server", async () => {
    const { result } = renderHook(() => useConversation("cnv_1", "employee-assistant"), { wrapper: wrap() });
    await waitFor(() => expect(result.current.loading).toBe(false));
    let sent: boolean | undefined;
    await act(async () => {
      sent = await result.current.send("   ");
    });
    expect(sent).toBe(false);
    expect(calls.send).toEqual([]);
  });
});
