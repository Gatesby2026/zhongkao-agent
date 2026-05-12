import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // 允许读取 knowledge-base 目录
  serverExternalPackages: ["js-yaml"],
};

export default nextConfig;
