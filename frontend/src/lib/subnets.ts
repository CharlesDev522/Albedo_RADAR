/** SN97 Albedo dashboard profile. */

export const DEFAULT_SUBNET = 97;

export type DashboardView = "dashboard" | "clusters" | "activity";

export interface SubnetFeatures {
  incentiveColumn: boolean;
  commitLabel: string;
  modelHost: "hippius";
}

export interface SubnetProfile {
  netuid: number;
  name: string;
  shortName: string;
  tagline: string;
  accent: "amber";
  features: SubnetFeatures;
}

const ALBEDO_PROFILE: SubnetProfile = {
  netuid: 97,
  name: "Albedo",
  shortName: "Albedo",
  tagline: "Model distillation · Qwen3.6-35B vs Qwen3-4B · Hippius pipe commits",
  accent: "amber",
  features: {
    incentiveColumn: true,
    commitLabel: "published",
    modelHost: "hippius",
  },
};

export function getSubnetProfile(_netuid: number = DEFAULT_SUBNET): SubnetProfile {
  return ALBEDO_PROFILE;
}

export const DASHBOARD_TABS: { view: DashboardView; label: string; hint: string }[] = [
  { view: "dashboard", label: "Overview", hint: "Slots, commits, and live feed" },
  { view: "activity", label: "Repo activity", hint: "Hippius hub changes and miner model updates" },
  { view: "clusters", label: "Clusters", hint: "Coldkey and model-owner groups" },
];
