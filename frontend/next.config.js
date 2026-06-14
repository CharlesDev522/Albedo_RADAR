/** @type {import('next').NextConfig} */
const apiOrigin =
  process.env.API_URL?.replace(/\/api\/v1\/?$/, "") ||
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/api\/v1\/?$/, "") ||
  "http://localhost:8000";

const nextConfig = {
  output: "standalone",
  // Browser calls /api/v1/* on port 3000; Next.js proxies to the FastAPI backend.
  // This fixes the regression when LiveDashboard moved fetches to the client:
  // the browser cannot resolve Docker-internal hostnames like api:8000.
  async rewrites() {
    return [
      {
        source: "/api/v1/:path*",
        destination: `${apiOrigin}/api/v1/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;
