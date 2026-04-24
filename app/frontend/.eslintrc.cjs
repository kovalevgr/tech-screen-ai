// TechScreen frontend ESLint config (legacy .eslintrc format).
// Flat config migration is deferred to a later task — see
// specs/001-t01-monorepo-baseline/research.md §2.
module.exports = {
  root: true,
  parser: '@typescript-eslint/parser',
  parserOptions: {
    ecmaVersion: 'latest',
    sourceType: 'module',
    project: false,
  },
  plugins: ['@typescript-eslint'],
  extends: [
    'eslint:recommended',
    'plugin:@typescript-eslint/recommended',
    'prettier',
  ],
  env: {
    browser: true,
    node: true,
    es2022: true,
  },
  ignorePatterns: ['node_modules', '.next', 'dist', 'out', 'coverage', '*.config.js', '*.config.cjs'],
};
