/** Dashboard subnet profiles — SN97 (Albedo) + SN24 (Quasar) are first-class. */

export const DASHBOARD_SUBNETS = [97, 24] as const;
export type DashboardSubnet = (typeof DASHBOARD_SUBNETS)[number];

export const OTHER_SUBNETS = [21, 1] as const;

export interface SubnetFeatures {
  /** When true, miner clusters panel is the first block on the dashboard (SN24). */
  minerClustersTop: boolean;
  incentiveColumn: boolean;
  commitLabel: string;
  modelHost: "hippius" | "huggingface";
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
    tagline: "Model distillation · Qwen3.6-35B vs Qwen3-4B · Hippius pipe commits",
    accent: "amber",
    features: {
      minerClustersTop: false,
      incentiveColumn: true,
      commitLabel: "published",
      modelHost: "hippius",
    },
  },
  24: {
    netuid: 24,
    name: "Quasar",
    shortName: "Quasar",
    tagline: "Quasar 3B MoE · king-of-the-hill · JSON commits",
    accent: "violet",
    features: {
      minerClustersTop: true,
      incentiveColumn: true,
      commitLabel: "quasar",
      modelHost: "huggingface",
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
        minerClustersTop: false,
        incentiveColumn: true,
        commitLabel: "model",
        modelHost: "huggingface",
      },
    }
  );
}

export function isDashboardSubnet(netuid: number): netuid is DashboardSubnet {
  return (DASHBOARD_SUBNETS as readonly number[]).includes(netuid);
}
