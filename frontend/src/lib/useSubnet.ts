"use client";

import { useCallback, useMemo } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { DEFAULT_SUBNET, type DashboardView } from "@/lib/subnets";

export function useSubnet() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const view: DashboardView = useMemo(
    () => (searchParams.get("view") === "clusters" ? "clusters" : "dashboard"),
    [searchParams]
  );

  const setView = useCallback(
    (next: DashboardView) => {
      const params = new URLSearchParams(searchParams.toString());
      if (next === "clusters") {
        params.set("view", "clusters");
      } else {
        params.delete("view");
      }
      params.delete("subnet");
      const qs = params.toString();
      router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
    },
    [pathname, router, searchParams]
  );

  return {
    subnet: DEFAULT_SUBNET,
    view,
    setView,
  };
}
