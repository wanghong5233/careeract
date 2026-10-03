"use client";

import { useCallback, useEffect, useState, type SetStateAction } from "react";
import { createLatestRequest } from "@/lib/latest-request";
import { readProjects, type CareerProject } from "@/lib/projects";

export function useProjectList() {
  const [projects, setProjects] = useState<CareerProject[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [cursor, setCursor] = useState<string | null>(null);
  const [requests] = useState(createLatestRequest);

  const load = useCallback(async (nextCursor?: string) => {
    const controller = requests.start();
    setLoading(true); setError("");
    try {
      const page = await readProjects(
        { limit: 50, ...(nextCursor ? { cursor: nextCursor } : {}) },
        AbortSignal.any([controller.signal, AbortSignal.timeout(20_000)]),
      );
      if (!requests.isCurrent(controller)) return;
      setProjects(previous => nextCursor
        ? [...previous, ...page.items.filter(item => !previous.some(existing => existing.id === item.id))]
        : page.items);
      setCursor(page.next_cursor);
    } catch (failure) {
      if (requests.isCurrent(controller)) setError(failure instanceof Error ? failure.message : "项目读取失败，请重试。");
    } finally {
      if (requests.isCurrent(controller)) setLoading(false);
    }
  }, [requests]);

  useEffect(() => {
    const refresh = () => { void load(); };
    refresh();
    window.addEventListener("careeract:projects-changed", refresh);
    return () => {
      requests.cancel();
      window.removeEventListener("careeract:projects-changed", refresh);
    };
  }, [load, requests]);

  function updateProjects(change: SetStateAction<CareerProject[]>) {
    requests.cancel();
    setLoading(false);
    setProjects(change);
  }

  return { projects, loading, error, cursor, updateProjects, refresh: () => load(), loadMore: () => cursor ? load(cursor) : Promise.resolve() };
}
