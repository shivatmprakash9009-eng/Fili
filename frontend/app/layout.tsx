import type { Metadata, Viewport } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap"
});

export const metadata: Metadata = {
  title: {
    default: "Fili — Prospecting workspace",
    template: "%s · Fili"
  },
  description: "A focused workspace for discovering, enriching and managing your next customers.",
  applicationName: "Fili",
  appleWebApp: {
    capable: true,
    statusBarStyle: "default",
    title: "Fili"
  }
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#F8FAFC"
};

export default function RootLayout({
  children
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className={inter.variable}>{children}</body>
    </html>
  );
}
