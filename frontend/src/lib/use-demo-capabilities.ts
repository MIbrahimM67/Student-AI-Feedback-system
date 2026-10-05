"use client";
import { useEffect, useState } from "react";

export function useDemoCodeExecution(): boolean {
  const demo = process.env.NEXT_PUBLIC_DOCUMENT_DEMO === "true";
  const [enabled, setEnabled] = useState(!demo);
  useEffect(() => {
    if (!demo) return;
    const controller = new AbortController();
    fetch("/api/demo-capabilities", { signal: controller.signal, cache: "no-store" })
      .then(response => response.ok ? response.json() : null)
      .then(value => setEnabled(value?.code_execution === true))
      .catch(() => {});
    return () => controller.abort();
  }, [demo]);
  return enabled;
}
