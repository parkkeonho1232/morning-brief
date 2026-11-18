import type { NextConfig } from "next";

// 모든 화면이 로그인 뒤 요청마다 DB를 읽으므로 Cache Components(사전 렌더링)는 쓰지 않는다.
const nextConfig: NextConfig = {
  poweredByHeader: false,
};

export default nextConfig;
