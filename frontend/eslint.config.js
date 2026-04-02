/**
 * ESLint configuration for Crate frontend.
 *
 * What is ESLint?
 * ESLint is a JavaScript linter — it reads your code and reports problems:
 * undefined variables, missing keys in lists, unsafe patterns, etc.
 * It can also enforce code style rules. Think of it as Ruff, but for JS.
 *
 * Rule sets used here:
 *   js.recommended          — catches common JS errors (undefined vars, etc.)
 *   react/recommended       — React-specific rules (missing keys, prop types, etc.)
 *   react-hooks/recommended — enforces Rules of Hooks (no hooks in conditions, etc.)
 *   prettier                — reports Prettier formatting violations via ESLint
 */
import js from '@eslint/js';
import reactPlugin from 'eslint-plugin-react';
import reactHooks from 'eslint-plugin-react-hooks';
import reactRefresh from 'eslint-plugin-react-refresh';
import prettierConfig from 'eslint-config-prettier';
import prettierPlugin from 'eslint-plugin-prettier';

export default [
  { ignores: ['dist', 'node_modules'] },
  {
    files: ['**/*.{js,jsx}'],
    languageOptions: {
      ecmaVersion: 2020,
      globals: {
        window: 'readonly',
        document: 'readonly',
        console: 'readonly',
        fetch: 'readonly',
        setTimeout: 'readonly',
        clearTimeout: 'readonly',
        setInterval: 'readonly',
        clearInterval: 'readonly',
      },
      parserOptions: {
        ecmaVersion: 'latest',
        ecmaFeatures: { jsx: true },
        sourceType: 'module',
      },
    },
    settings: {
      react: { version: '18.3' },
    },
    plugins: {
      react: reactPlugin,
      'react-hooks': reactHooks,
      'react-refresh': reactRefresh,
      prettier: prettierPlugin,
    },
    rules: {
      // React rules
      ...reactPlugin.configs.recommended.rules,
      ...reactHooks.configs.recommended.rules,
      'react/react-in-jsx-scope': 'off', // Not needed in React 17+
      'react/prop-types': 'off',         // Not using TypeScript, prop-types is verbose

      // React Refresh — ensures components are structured for hot reload
      'react-refresh/only-export-components': ['warn', { allowConstantExport: true }],

      // No console.log in production code.
      // Why? console.log left in production code clutters the browser console
      // and can leak sensitive information. Use a proper logger instead.
      // To debug locally, use console.log freely — just remove before committing.
      'no-console': ['warn', { allow: ['warn', 'error'] }],

      // Prettier formatting violations are reported as ESLint errors.
      // Run 'npm run format' to auto-fix them.
      'prettier/prettier': 'error',

      // Disable ESLint formatting rules that conflict with Prettier.
      ...prettierConfig.rules,
    },
  },
];
