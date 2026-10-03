import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  {
    files: ["src/components/markdown-text.tsx"],
    rules: {
      "react-hooks/refs": "off",
    },
  },
  {
    files: ["src/components/file.tsx"],
    rules: {
      "react-hooks/static-components": "off",
    },
  },
  {
    files: ["src/components/thread.aui.tsx"],
    rules: {
      "jsx-a11y/alt-text": "off",
    },
  },
  {
    files: ["src/components/image.tsx", "src/components/attachment.aui.tsx"],
    rules: {
      "@next/next/no-img-element": "off",
      "jsx-a11y/alt-text": "off",
    },
  },
  // Override default ignores of eslint-config-next.
  globalIgnores([
    // Default ignores of eslint-config-next:
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
  ]),
]);

export default eslintConfig;
