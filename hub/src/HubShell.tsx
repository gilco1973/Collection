import { useEffect, useRef, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { NAV_BY_LABEL } from "./routes";

/** Elements that read as "clickable" in the artboard vocabulary. */
const CLICKABLE = ["[data-nav]", ".btn", ".hnav .links span", ".lc", ".hsec .hh a", "a"].join(",");

/**
 * Wraps a generated screen and makes it navigable without editing its markup.
 *
 * The screens under `src/screens/` are byte-identical reproductions of the
 * published artboards, so they carry no hrefs and no handlers. Adding them
 * inline would change the markup and break the pixel match; instead this shell
 * delegates click and keyboard events on the subtree and resolves a destination
 * from the clicked element's own text, via `NAV_BY_LABEL`.
 */
export default function HubShell({ children }: { children: ReactNode }) {
  const hostRef = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;

    const destinationFor = (start: Element | null): string | undefined => {
      // Live screens (marked `data-live`) wire their own links and buttons;
      // label-based delegation is only for the generated artboard screens.
      if (start?.closest("[data-live]")) return undefined;
      let el: Element | null = start;
      while (el && el !== host) {
        if (el.matches(CLICKABLE)) {
          const explicit = el.getAttribute("data-nav");
          if (explicit) return explicit;
          const label = (el.textContent ?? "").trim().toLowerCase();
          const hit = NAV_BY_LABEL[label];
          if (hit) return hit;
        }
        el = el.parentElement;
      }
      return undefined;
    };

    const onClick = (event: MouseEvent) => {
      if (event.defaultPrevented || event.button !== 0) return;
      if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      const to = destinationFor(event.target as Element);
      if (!to) return;
      event.preventDefault();
      navigate(to);
    };

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Enter" && event.key !== " ") return;
      const to = destinationFor(document.activeElement);
      if (!to) return;
      event.preventDefault();
      navigate(to);
    };

    host.addEventListener("click", onClick);
    host.addEventListener("keydown", onKeyDown);
    return () => {
      host.removeEventListener("click", onClick);
      host.removeEventListener("keydown", onKeyDown);
    };
  }, [navigate]);

  // `display:contents` keeps this wrapper out of the layout entirely, so the
  // `.hub` element below is the outermost box exactly as it is in the artboard.
  return (
    <div ref={hostRef} style={{ display: "contents" }}>
      {children}
    </div>
  );
}
