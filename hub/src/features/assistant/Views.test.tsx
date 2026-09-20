import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { View } from "../../api/types";
import { CONVERSATION_1 } from "../../api/mock/fixtures";
import { Message, paragraphs, sourcesFor } from "./Views";

describe("view-descriptor renderer", () => {
  it("groups text leaves into paragraphs and attaches citations", () => {
    const views = CONVERSATION_1.turns[1].views;
    const paras = paragraphs(views);
    expect(paras).toHaveLength(2);
    expect(paras[0].map((l) => l.kind)).toEqual(["text", "citation", "text", "citation"]);
    expect(paras[1].map((l) => l.kind)).toEqual(["text", "citation"]);
  });

  it("marks claims by their support and never interprets model text as markup", () => {
    const views: View[] = [{ kind: "text", provenance: "model", text: "Say <b>hi</b> now", claims: [{ span: [4, 13], support: "unsupported" }] }];
    render(<Message views={views} />);
    expect(screen.getByText("<b>hi</b>")).toHaveClass("claim", "un");
    expect(document.querySelector("b")).toBeNull();
  });

  it("derives source chips from citations when the server sends none", () => {
    const chips = sourcesFor({
      id: "t",
      role: "assistant",
      at: "",
      views: [
        { kind: "citation", source: "Runbook · x", chunk_ref: "c", classification: "internal" },
        { kind: "citation", source: "Policy manual · y", chunk_ref: "d", classification: "confidential" },
      ],
    });
    expect(chips).toEqual([
      { text: "runbook · internal", kind: "line" },
      { text: "policy manual · confidential", kind: "model" },
    ]);
  });
});
