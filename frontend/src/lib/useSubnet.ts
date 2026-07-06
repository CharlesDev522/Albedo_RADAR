"use client";

import { useCallback, useSyncExternalStore } from "react";
import { usePathname } from "next/navigation";
import { DEFAULT_SUBNET, type DashboardView } from "@/lib/subnets";
import {
  getDashboardViewSnapshot,
  setDashboardView,
  subscribeDashboardView,
} from "@/lib/dashboardView";

export function useSubnet() {
  const pathname = usePathname();
  const view = useSyncExternalStore(
    subscribeDashboardView,
    getDashboardViewSnapshot,
    () => "dashboard" as DashboardView
  );

  const setView = useCallback(
    (next: DashboardView) => {
      setDashboardView(next);
      const params = new URLSearchParams(window.location.search);
      if (next === "dashboard") {
        params.delete("view");
      } else {
        params.set("view", next);
      }
      params.delete("subnet");
      const qs = params.toString();
      const url = qs ? `${pathname}?${qs}` : pathname;
      window.history.replaceState(window.history.state, "", url);
    },
    [pathname]
  );

  return {
    subnet: DEFAULT_SUBNET,
    view,
    setView,
  };
}
