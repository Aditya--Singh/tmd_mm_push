import js from "@eslint/js";
import globals from "globals";
import react from "eslint-plugin-react";

export default [
    { ignores: ["dist/**", "node_modules/**"] },
    {
        files: ["**/*.{js,jsx}"],
        languageOptions: {
            ecmaVersion: 2022,
            sourceType: "module",
            globals: { ...globals.browser, ...globals.node },
            parserOptions: { ecmaFeatures: { jsx: true } },
        },
        plugins: { react },
        settings: { react: { version: "detect" } },
        rules: {
            ...js.configs.recommended.rules,
            ...react.configs.recommended.rules,
            // The rule is off, because the variables of a component are read through JSX.
            "react/react-in-jsx-scope": "off",
            "react/prop-types": "off",
            "no-unused-vars": ["error", { argsIgnorePattern: "^_" }],
        },
    },
];
