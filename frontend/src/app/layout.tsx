import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "MinerWatch | Bittensor Miner Intelligence",
  description: "Real-time miner tracking and analytics for Bittensor subnets",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <nav className="border-b border-bittensor-border bg-bittensor-card/50 backdrop-blur sticky top-0 z-50">
          <div className="max-w-7xl mx-auto px-4 py-3 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 rounded bg-bittensor-accent/20 flex items-center justify-center">
                <span className="text-bittensor-accent font-bold text-sm">MW</span>
              </div>
              <div>
                <h1 className="text-lg font-semibold text-white">MinerWatch</h1>
                <p className="text-xs text-gray-500">Subnet 97 · v5 Commitment Tracker</p>
              </div>
            </div>
            <div className="flex items-center gap-4 text-sm text-gray-400">
              <span className="flex items-center gap-1.5">
                <span className="w-2 h-2 rounded-full bg-bittensor-accent animate-pulse" />
                Live
              </span>
            </div>
          </div>
        </nav>
        <main className="max-w-7xl mx-auto px-4 py-6">{children}</main>
      </body>
    </html>
  );
}
