import type { Metadata } from "next";
import "./globals.css";
export const metadata: Metadata = { title: "GigBid · Your work, well represented", description: "Evidence-grounded freelancer copilot with human approvals" };
export default function Layout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
