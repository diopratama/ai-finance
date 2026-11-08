/** @type {import('next').NextConfig} */
const buildSalt = `build-${Date.now()}`;

const nextConfig = {
  reactStrictMode: true,
  eslint: {
    ignoreDuringBuilds: true,
  },
  generateBuildId: async () => {
    return buildSalt;
  },
  webpack: (config) => {
    if (config.output) {
      config.output.hashSalt = buildSalt;
    }
    return config;
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
