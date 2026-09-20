import { act, render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import TypewriterText from "../components/TypewriterText";

const stubMatchMedia = (reduced: boolean) =>
  vi.stubGlobal("matchMedia", (query: string) => ({
    matches: reduced,
    media: query,
    addEventListener: () => {},
    removeEventListener: () => {},
  }));

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("TypewriterText", () => {
  it("reveals the text one character at a time, then calls onDone", () => {
    vi.useFakeTimers();
    stubMatchMedia(false);
    const onDone = vi.fn();
    const { container } = render(<TypewriterText text="Hi" onDone={onDone} />);
    expect(container.textContent).toBe("");
    act(() => vi.advanceTimersByTime(16));
    expect(container.textContent).toBe("H");
    expect(onDone).not.toHaveBeenCalled();
    act(() => vi.advanceTimersByTime(16));
    expect(container.textContent).toBe("Hi");
    expect(onDone).toHaveBeenCalledTimes(1);
  });

  it("shows the full text immediately under prefers-reduced-motion, with no caret", () => {
    stubMatchMedia(true);
    const onDone = vi.fn();
    const { container } = render(<TypewriterText text="Hi" onDone={onDone} />);
    expect(container.textContent).toBe("Hi");
    expect(onDone).toHaveBeenCalledTimes(1);
    expect(container.querySelector('[aria-hidden="true"]')).toBeNull();
  });
});
