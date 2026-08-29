/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  env: {
    SHOPIFY_API_VERSION: process.env.SHOPIFY_API_VERSION || "2026-01",
  },
};

export default nextConfig;
