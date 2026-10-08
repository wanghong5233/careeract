import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  devIndicators: false,
  async rewrites() {
    return [
      {
        source: "/api/browser/sessions/:sessionId/cast",
        destination: `${process.env.BROWSER_BASE_URL ?? "http://localhost:8001"}/internal/v1/sessions/:sessionId/cast`,
      },
    ];
  },
};

export default nextConfig;
