"use client";

import { useCallback, useMemo } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { DEFAULT_SUBNET, type DashboardView } from "@/lib/subnets";

function parseView(raw: string | null): DashboardView {
  if (raw === "clusters") return "clusters";
  if (raw === "activity") return "activity";
  if (raw === "duels") return "duels";
  return "dashboard";
}

export function useSubnet() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const view: DashboardView = useMemo(
    () => parseView(searchParams.get("view")),
    [searchParams]
  );

  const setView = useCallback(
    (next: DashboardView) => {
      const params = new URLSearchParams(searchParams.toString());
      if (next === "dashboard") {
        params.delete("view");
      } else {
        params.set("view", next);
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
