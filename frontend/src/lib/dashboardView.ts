import type { DashboardView } from "@/lib/subnets";

export function parseDashboardView(raw: string | null | undefined): DashboardView {
  if (raw === "clusters") return "clusters";
  if (raw === "activity") return "activity";
  if (raw === "duels") return "duels";
  return "dashboard";
}

export function readViewFromUrl(): DashboardView {
  if (typeof window === "undefined") return "dashboard";
  return parseDashboardView(new URLSearchParams(window.location.search).get("view"));
}

let viewState: DashboardView = "dashboard";
const listeners = new Set<() => void>();

function emit() {
  for (const listener of listeners) listener();
}

export function getDashboardViewSnapshot(): DashboardView {
  return viewState;
}

export function subscribeDashboardView(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function setDashboardView(next: DashboardView): void {
  if (viewState === next) return;
  viewState = next;
  emit();
}

export function syncDashboardViewFromUrl(): void {
  const next = readViewFromUrl();
  if (next !== viewState) {
    viewState = next;
    emit();
  }
}

if (typeof window !== "undefined") {
  viewState = readViewFromUrl();
  window.addEventListener("popstate", syncDashboardViewFromUrl);
}
