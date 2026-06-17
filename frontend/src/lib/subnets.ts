/** Dashboard subnet profiles — SN97 (Albedo) + SN24 (OMEGA) are first-class. */

export const DASHBOARD_SUBNETS = [97, 24] as const;
export type DashboardSubnet = (typeof DASHBOARD_SUBNETS)[number];

export const OTHER_SUBNETS = [21, 1] as const;

export interface SubnetFeatures {
  albedoKing: boolean;
  hfAnalytics: boolean;
  incentiveColumn: boolean;
}

export interface SubnetProfile {
  netuid: number;
  name: string;
  shortName: string;
  tagline: string;
  accent: "amber" | "violet" | "emerald";
  features: SubnetFeatures;
}

const PROFILES: Record<number, SubnetProfile> = {
  97: {
    netuid: 97,
    name: "Albedo",
    shortName: "Albedo",
    tagline: "King-of-the-hill model distillation · Qwen3-4B",
    accent: "amber",
    features: {
      albedoKing: true,
      hfAnalytics: true,
      incentiveColumn: true,
    },
  },
  24: {
    netuid: 24,
    name: "OMEGA Labs",
    shortName: "OMEGA",
    tagline: "Multimodal dataset subnet · model commits",
    accent: "violet",
    features: {
      albedoKing: false,
      hfAnalytics: false,
      incentiveColumn: true,
    },
  },
};

export function getSubnetProfile(netuid: number): SubnetProfile {
  return (
    PROFILES[netuid] ?? {
      netuid,
      name: `Subnet ${netuid}`,
      shortName: `SN${netuid}`,
      tagline: "Bittensor subnet",
      accent: "emerald",
      features: {
        albedoKing: false,
        hfAnalytics: false,
        incentiveColumn: true,
      },
    }
  );
}

export function isDashboardSubnet(netuid: number): netuid is DashboardSubnet {
  return (DASHBOARD_SUBNETS as readonly number[]).includes(netuid);
}
