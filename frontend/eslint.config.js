import js from "@eslint/js";
import { defineConfig } from "eslint/config";
import prettier from "eslint-config-prettier/flat";
import importPlugin from "eslint-plugin-import-x";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";
import globals from "globals";
import tseslint from "typescript-eslint";

export default defineConfig([
  {
    ignores: [
      "**/dist/**",
      "**/build/**",
      "**/node_modules/**",
      "**/.tmp/**",
      "src/api/schema.d.ts",
    ],
  },
  { linterOptions: { reportUnusedDisableDirectives: "error" } },
  {
    files: ["**/*.{js,mjs,cjs,jsx}"],
    extends: [js.configs.recommended],
    languageOptions: { parserOptions: { ecmaFeatures: { jsx: true } } },
  },
  {
    files: ["**/*.{ts,mts,cts,tsx}"],
    extends: [js.configs.recommended, tseslint.configs.recommended],
  },
  {
    files: ["src/**/*.{ts,tsx}"],
    languageOptions: { globals: globals.browser },
    plugins: { "react-hooks": reactHooks, "react-refresh": reactRefresh, "import-x": importPlugin },
    settings: { "import-x/resolver": { typescript: { project: "./tsconfig.app.json" } } },
    rules: {
      ...reactHooks.configs.recommended.rules,
      // React Compiler is not enabled; retain TanStack Table and React Hook Form APIs.
      "react-hooks/incompatible-library": "off",
      "import-x/no-cycle": "error",
      "react-refresh/only-export-components": ["warn", { allowConstantExport: true }],
    },
  },
  {
    files: ["*.{js,ts,mjs}", "scripts/**/*.mjs", "tests/**/*.mjs"],
    languageOptions: { globals: globals.node },
  },
  {
    // Radix component aliases and the shared component/helper module are intentional.
    files: ["src/components/ui/dialog.tsx", "src/pages/record/entry-shared.tsx"],
    rules: { "react-refresh/only-export-components": "off" },
  },
  prettier,
]);
