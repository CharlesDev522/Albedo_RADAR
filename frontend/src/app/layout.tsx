import type { Metadata } from "next";
import { IBM_Plex_Mono, Inter } from "next/font/google";
import "./globals.css";

const inter = Inter({ subsets: ["latin"], variable: "--font-sans" });
const mono = IBM_Plex_Mono({
  subsets: ["latin"],
  weight: ["400", "500"],
  variable: "--font-mono",
});

export const metadata: Metadata = {
  title: "MinerWatch · SN97",
  description: "v5 commitment tracker for Bittensor subnet 97",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${inter.variable} ${mono.variable}`}>
      <body className="font-sans text-[12px] leading-relaxed">
        <header className="border-b border-zinc-800/80 bg-zinc-950/90 backdrop-blur sticky top-0 z-50">
          <div className="max-w-[1400px] mx-auto px-3 py-2 flex items-center justify-between gap-4">
            <div className="flex items-center gap-2.5 min-w-0">
              <div className="w-6 h-6 rounded-md bg-emerald-500/15 border border-emerald-500/30 flex items-center justify-center shrink-0">
                <span className="text-emerald-400 font-mono text-[10px] font-medium">MW</span>
              </div>
              <div className="min-w-0">
                <h1 className="text-[13px] font-semibold text-zinc-100 tracking-tight">MinerWatch</h1>
                <p className="text-[10px] text-zinc-500 truncate">subnet 97 · v5 commitments</p>
              </div>
            </div>
            <div className="flex items-center gap-3 text-[10px] text-zinc-500 shrink-0">
              <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full border border-emerald-500/20 bg-emerald-500/5 text-emerald-400">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                live
              </span>
            </div>
          </div>
        </header>
        <main className="max-w-[1400px] mx-auto px-3 py-3">{children}</main>
      </body>
    </html>
  );
}
