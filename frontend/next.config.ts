import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Build plain HTML/CSS/JS files into out/, so the site can be hosted for free on
  // GitHub Pages. There is no Next.js server: the page calls the Python API directly.
  output: "export",
  // GitHub Pages serves the site at /bureaucracy-copilot/, not at the root. The deploy
  // workflow sets NEXT_PUBLIC_BASE_PATH; locally it is empty.
  basePath: process.env.NEXT_PUBLIC_BASE_PATH ?? "",
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
