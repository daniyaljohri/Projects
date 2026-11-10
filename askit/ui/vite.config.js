import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// port 3000 matches the CORS origin allowed by the API
export default defineConfig({
  plugins: [react()],
  server: { port: 3000, strictPort: true },
});
