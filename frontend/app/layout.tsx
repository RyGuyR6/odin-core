import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Odin Control Center",
  description: "Remote command and control for the Odin engineering platform.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className="dark">
      <body>{children}</body>
    </html>
  );
}
