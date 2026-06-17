"use client";

import { useCallback, useMemo } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { DEFAULT_SUBNET } from "@/lib/api";
import { DASHBOARD_SUBNETS, OTHER_SUBNETS } from "@/lib/subnets";

function parseSubnet(raw: string | null): number {
  if (!raw) return DEFAULT_SUBNET;
  const n = Number.parseInt(raw, 10);
  if (!Number.isFinite(n) || n < 0 || n > 65535) return DEFAULT_SUBNET;
  return n;
}

export function useSubnet() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const subnet = useMemo(() => parseSubnet(searchParams.get("subnet")), [searchParams]);

  const setSubnet = useCallback(
    (next: number) => {
      const safe = Math.max(0, Math.min(65535, Math.trunc(next)));
      const params = new URLSearchParams(searchParams.toString());
      if (safe === DEFAULT_SUBNET) {
        params.delete("subnet");
      } else {
        params.set("subnet", String(safe));
      }
      const qs = params.toString();
      router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
    },
    [pathname, router, searchParams]
  );

  return {
    subnet,
    setSubnet,
    dashboardSubnets: DASHBOARD_SUBNETS,
    otherPresets: OTHER_SUBNETS,
    /** @deprecated use dashboardSubnets */
    presets: [...DASHBOARD_SUBNETS, ...OTHER_SUBNETS] as const,
  };
}
