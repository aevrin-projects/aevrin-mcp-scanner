import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

/**
 * Feature-Sliced Design layers, highest first. A layer may import from any
 * layer below it and never from one above or beside it, which is what keeps
 * the dependency graph acyclic and makes a slice safe to delete.
 *
 * Encoded as lint rules rather than documentation because a convention that
 * nothing checks is a convention that lasts about a month.
 */
const LAYERS = ["app", "views", "widgets", "features", "entities", "shared"];

/** Every layer at or above `layer`, as import patterns to forbid. */
function forbiddenFor(layer) {
  const index = LAYERS.indexOf(layer);
  return LAYERS.slice(0, index).map((upper) => ({
    group: [`@/${upper}/*`, `@/${upper}`],
    message:
      `${layer} must not import from ${upper}. Dependencies run one way ` +
      `(${LAYERS.join(" -> ")}); move the shared part down a layer instead.`,
  }));
}

const layerRules = LAYERS.slice(1).map((layer) => ({
  files: [`src/${layer}/**/*.{ts,tsx}`],
  rules: {
    "no-restricted-imports": ["error", { patterns: forbiddenFor(layer) }],
  },
}));

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  // Override default ignores of eslint-config-next.
  globalIgnores([
    // Default ignores of eslint-config-next:
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
  ]),
  ...layerRules,
]);

export default eslintConfig;
