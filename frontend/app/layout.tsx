import type { Metadata, Viewport } from "next";
import "./globals.css";

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
  themeColor: "#f7f9fc"
};

export default function RootLayout({
  children
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}