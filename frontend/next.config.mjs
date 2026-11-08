/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  eslint: {
    ignoreDuringBuilds: true,
  },
  async redirects() {
    return [
      {
        source: "/cfp",
        destination: "/planner",
        permanent: false,
      },
    ];
  },
};

export default nextConfig;
