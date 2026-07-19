import { fileURLToPath, URL } from "url";
import { reactRouter } from "@react-router/dev/vite";
import { defineConfig } from "vite";
import safariCacheBustPlugin from "./vite-plugin-safari-cachebust";

// Ensure that bun always uses the react-dom/server.node functions.
function alwaysUseReactDomServerNode() {
  return {
    name: "vite-plugin-always-use-react-dom-server-node",
    enforce: "pre",

    resolveId(source, importer) {
      if (
        typeof importer === "string" &&
        importer.endsWith("/entry.server.node.tsx") &&
        source.includes("react-dom/server")
      ) {
        return this.resolve("react-dom/server.node", importer, {
          skipSelf: true,
        });
      }
      return null;
    },
  };
}

function fullReload() {
  return {
    name: "full-reload",
    enforce: "pre",
    handleHotUpdate({ server }) {
      server.ws.send({
        type: "full-reload",
      });
      return [];
    }
  };
}

export default defineConfig((config) => ({
  base: "/",
  plugins: [
    alwaysUseReactDomServerNode(),
    reactRouter(),
    safariCacheBustPlugin(),
  ].concat([]),
  build: {
    sourcemap: false,
    rollupOptions: {
      onwarn(warning, warn) {
        if (warning.code === "EVAL" && warning.id && warning.id.endsWith("state.js")) return;
        warn(warning);
      },
      jsx: {},
      output: {
        advancedChunks: {
          groups: [
            {
              test: /env.json/,
              name: "reflex-env",
            },
          ],
        },
      },
    },
  },
  experimental: {
    enableNativePlugin: false,
    hmr: false,
  },
  server: {
    port: process.env.PORT,
    hmr: true,
    watch: {
      ignored: [
        "**/.web/backend/**",
        "**/.web/reflex.install_frontend_packages.cached",
      ],
    },
  },
  resolve: {
    mainFields: ["browser", "module", "jsnext"],
    alias: [
      {
        find: "$",
        replacement: fileURLToPath(new URL("./", import.meta.url)),
      },
      {
        find: "@",
        replacement: fileURLToPath(new URL("./public", import.meta.url)),
      },
    ],
  },
}));