import type { NextConfig } from "next";
const config: NextConfig = {
  distDir: process.env.GIGBID_E2E_TEST_SERVER === "1" ? ".next/e2e" : ".next",
  output: process.platform === "win32" ? undefined : "standalone",
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${process.env.API_INTERNAL_URL || "http://127.0.0.1:8000"}/:path*` }];
  },
  async headers() {
    return [{ source: "/:path*", headers: [
      { key: "X-Frame-Options", value: "DENY" },
      { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
      { key: "X-Content-Type-Options", value: "nosniff" }
    ] }];
  }
};
export default config;
