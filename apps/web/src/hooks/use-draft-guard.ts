"use client";

import { useEffect } from "react";
import { useWorkspaceActions } from "@/components/workspace-actions";

export function useDraftGuard(dirty: boolean) {
  const { openContent } = useWorkspaceActions();
  useEffect(() => {
    if (!dirty) return;
    const beforeUnload = (event: BeforeUnloadEvent) => event.preventDefault();
    const beforeShellNavigate = (event: Event) => event.preventDefault();
    const beforeNavigate = (event: MouseEvent) => {
      const anchor = event.target instanceof Element ? event.target.closest("a[href]") : null;
      if (!(anchor instanceof HTMLAnchorElement) || event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey || anchor.target === "_blank" || anchor.hasAttribute("download")) return;
      const destination = new URL(anchor.href);
      if (anchor.closest('nav[aria-label="全部能力"]')) return;
      if (destination.origin !== window.location.origin) return;
      if (destination.pathname === window.location.pathname && destination.search === window.location.search) return;
      event.preventDefault();
      event.stopPropagation();
      openContent(destination.pathname + destination.search + destination.hash);
    };
    window.addEventListener("beforeunload", beforeUnload);
    window.addEventListener("careeract:before-navigate", beforeShellNavigate);
    document.addEventListener("click", beforeNavigate, true);
    return () => {
      window.removeEventListener("beforeunload", beforeUnload);
      window.removeEventListener("careeract:before-navigate", beforeShellNavigate);
      document.removeEventListener("click", beforeNavigate, true);
    };
  }, [dirty, openContent]);
}
