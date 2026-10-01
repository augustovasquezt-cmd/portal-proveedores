import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Keep browser API calls same-origin; Next.js forwards them to FastAPI so
  // local development does not depend on browser CORS or localhost DNS behavior.
  async rewrites() {
    const apiServer = (process.env.API_SERVER_URL || process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000').replace(/\/$/, '')
    return [{ source: '/api-backend/:path*', destination: `${apiServer}/:path*` }]
  },
};

export default nextConfig;
