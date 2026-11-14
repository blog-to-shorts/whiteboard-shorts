import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// /api/* 요청을 FastAPI(8000)로 넘긴다 → 브라우저에서는 같은 주소처럼 보여 CORS 걱정이 없다
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": { target: "http://localhost:8000", rewrite: (p) => p.replace(/^\/api/, "") },
    },
  },
});