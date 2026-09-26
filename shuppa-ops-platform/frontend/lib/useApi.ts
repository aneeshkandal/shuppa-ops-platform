"use client";

import { useEffect, useRef, useState } from "react";

type State<T> = { data: T | null; loading: boolean; error: string | null; lastUpdated: number | null };

/**
 * Fetches `fn()` whenever any value in `deps` changes. `fn` is expected to be
 * a stable-ish closure (e.g. an inline arrow calling one of the lib/api.ts
 * functions) - it's re-invoked on every deps change, not memoized itself.
 *
 * `refreshInterval` (ms) optionally re-runs `fn()` on a timer, on top of the
 * normal deps-driven refetch - for pages that want to feel "live" (the
 * Alerts Center, the sidebar's alert badge, the Executive Overview) without
 * a real backend push channel. A background refresh keeps `loading` false
 * (it doesn't flash a spinner over content the user is already looking at)
 * and silently keeps the last-good data on error rather than clearing the
 * screen. `lastUpdated` (a Date.now() timestamp) is bumped on every
 * successful fetch, whether deps-driven or timer-driven, so the UI can show
 * "Last updated Xs ago".
 */
export function useApi<T>(
  fn: () => Promise<T>,
  deps: any[] = [],
  options?: { refreshInterval?: number }
): State<T> & { reload: () => void } {
  const [state, setState] = useState<State<T>>({ data: null, loading: true, error: null, lastUpdated: null });
  const [tick, setTick] = useState(0);
  const fnRef = useRef(fn);
  fnRef.current = fn;

  useEffect(() => {
    let cancelled = false;
    setState((s) => ({ ...s, loading: true, error: null }));
    fnRef.current()
      .then((data) => {
        if (!cancelled) setState({ data, loading: false, error: null, lastUpdated: Date.now() });
      })
      .catch((err) => {
        if (!cancelled) setState((s) => ({ ...s, data: null, loading: false, error: err?.message || "Request failed" }));
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick]);

  const refreshInterval = options?.refreshInterval;
  useEffect(() => {
    if (!refreshInterval) return;
    const id = setInterval(() => {
      fnRef.current()
        .then((data) => setState((s) => ({ ...s, data, error: null, lastUpdated: Date.now() })))
        .catch(() => {
          /* a background poll failing shouldn't clear what's already on screen */
        });
    }, refreshInterval);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refreshInterval, ...deps]);

  return { ...state, reload: () => setTick((t) => t + 1) };
}
