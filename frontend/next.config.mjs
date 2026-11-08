/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  eslint: {
    ignoreDuringBuilds: true,
  },
  generateBuildId: async () => {
    return `build-${Date.now()}`;
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
