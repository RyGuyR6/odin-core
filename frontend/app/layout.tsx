import { AuthProvider } from "@/components/auth/auth-provider";
import type { Metadata } from "next";
import { AppShell } from "@/components/navigation/app-shell";
import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "Odin Control Center",
    template: "%s | Odin",
  },
  description: "Remote command and control for the Odin engineering platform.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className="dark">
      <body><AuthProvider>
        <AppShell>{children}</AppShell>
      </AuthProvider></body>
    </html>
  );
}
