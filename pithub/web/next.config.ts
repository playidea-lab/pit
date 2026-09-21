import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // 컨테이너에 node_modules 전체 대신 필요한 파일만 담는다
  output: "standalone",
};

export default nextConfig;
