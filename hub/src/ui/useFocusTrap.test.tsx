import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useEffect, useRef, useState } from "react";
import { beforeAll, describe, expect, it } from "vitest";
import { useFocusTrap } from "./useFocusTrap";

/** A dialog that moves focus to its own field on open, the way the guide panel and the composer do. */
function Dialog({ onClose }: { onClose: () => void }) {
  const ref = useRef<HTMLDivElement>(null);
  useFocusTrap(ref, onClose);
  useEffect(() => {
    ref.current?.querySelector<HTMLElement>("input")?.focus();
  }, []);
  return (
    <div ref={ref} role="dialog" aria-label="Pick">
      <input aria-label="Search" />
      <button type="button">Add</button>
    </div>
  );
}

function Page() {
  const [open, setOpen] = useState(false);
  const [n, setN] = useState(0);
  return (
    <div>
      <button type="button" onClick={() => setOpen(true)}>
        Browse the catalog
      </button>
      <button type="button" onClick={() => setN((x) => x + 1)}>
        rerender {n}
      </button>
      {/* A new onClose identity on every render, as an inline arrow gives. */}
      {open && <Dialog onClose={() => setOpen(false)} />}
    </div>
  );
}

describe("useFocusTrap", () => {
  // jsdom lays nothing out, so every element's offsetParent is null; the trap reads it to skip hidden controls.
  beforeAll(() => {
    Object.defineProperty(HTMLElement.prototype, "offsetParent", {
      configurable: true,
      get: function (this: HTMLElement) {
        return this.parentElement;
      },
    });
  });

  it("captures the opener before the dialog's own autofocus, and gives focus back on Escape", async () => {
    const user = userEvent.setup();
    render(<Page />);
    const opener = screen.getByRole("button", { name: "Browse the catalog" });
    opener.focus();
    await user.keyboard("{Enter}");
    expect(screen.getByRole("textbox", { name: "Search" })).toHaveFocus();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(opener).toHaveFocus();
  });

  it("keeps the opener across re-renders that hand it a new onClose", async () => {
    const user = userEvent.setup();
    render(<Page />);
    const opener = screen.getByRole("button", { name: "Browse the catalog" });
    opener.focus();
    await user.keyboard("{Enter}");
    // The parent re-renders while the dialog is open (a new onClose identity); focus is inside the dialog meanwhile.
    screen.getByRole("button", { name: /rerender/ }).click();
    await screen.findByRole("button", { name: "rerender 1" });
    screen.getByRole("button", { name: "Add" }).focus();
    await user.keyboard("{Escape}");
    expect(opener).toHaveFocus();
  });

  it("cycles Tab inside the dialog", async () => {
    const user = userEvent.setup();
    render(<Page />);
    screen.getByRole("button", { name: "Browse the catalog" }).focus();
    await user.keyboard("{Enter}");
    await user.tab();
    expect(screen.getByRole("button", { name: "Add" })).toHaveFocus();
    await user.tab();
    expect(screen.getByRole("textbox", { name: "Search" })).toHaveFocus();
    await user.tab({ shift: true });
    expect(screen.getByRole("button", { name: "Add" })).toHaveFocus();
  });
});
