import { useEffect } from "react";

/** Sets the document title for a live page; the app-level fallback covers the rest. */
export function useTitle(title: string | undefined) {
  useEffect(() => {
    if (title) document.title = `${title} · CrossRiver AI Hub`;
  }, [title]);
}
