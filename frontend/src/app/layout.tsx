import type { Metadata } from "next";
import { Suspense } from "react";
import { IBM_Plex_Mono, Inter } from "next/font/google";
import HeaderBar from "@/components/HeaderBar";
import "./globals.css";

const inter = Inter({ subsets: ["latin"], variable: "--font-sans" });
const mono = IBM_Plex_Mono({
  subsets: ["latin"],
  weight: ["400", "500"],
  variable: "--font-mono",
});

export const metadata: Metadata = {
  title: "MinerWatch",
  description: "v6 model commitment tracker for Bittensor",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${inter.variable} ${mono.variable}`}>
      <body className="font-sans text-[12px] leading-relaxed">
        <Suspense fallback={null}>
          <HeaderBar />
        </Suspense>
        <main className="max-w-[1400px] mx-auto px-3 py-3">{children}</main>
      </body>
    </html>
  );
}
