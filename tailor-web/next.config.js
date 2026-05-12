/** @type {import('next').NextConfig} */
// Proxy every /api/* call to the Python server so the editor can share
// the same backend that powers /paste, /library, and the dashboard
// modal. In production the Python server can serve the Next.js build
// statically, or the front-end can be deployed independently and point
// at the Python server's public URL.
const NEXT_CONFIG = {
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: "http://localhost:8765/api/:path*",
      },
    ];
  },
};
module.exports = NEXT_CONFIG;
