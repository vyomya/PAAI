/** @type {import('next').NextConfig} */
module.exports = {
  reactStrictMode: true,
};
/** @type {import('next').NextConfig} */

// Everything under /api is proxied to the backend server-side, so the browser
// only ever sees one origin. That is what keeps the session cookie first-party:
// a cookie set directly by the Azure domain would be third-party, which Safari
// blocks outright. It also means zero CORS config.
const API_ORIGIN = process.env.API_ORIGIN ?? "http://localhost:8000";

module.exports = {
  reactStrictMode: true,
  async rewrites() {
    return [
      { source: "/api/:path*", destination: `${API_ORIGIN}/:path*` },
    ];
  },
};