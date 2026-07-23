"use client";

import { useSyncExternalStore } from "react";

function subscribe(onStoreChange: () => void): () => void {
  document.addEventListener("visibilitychange", onStoreChange);
  return () => document.removeEventListener("visibilitychange", onStoreChange);
}

function getSnapshot(): boolean {
  return document.visibilityState !== "hidden";
}

function getServerSnapshot(): boolean {
  return true;
}

/** True when the tab is visible; polling hooks should pause when false. */
export function usePageVisibility(): boolean {
  return useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
}
