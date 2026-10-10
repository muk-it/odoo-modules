const js = require('@eslint/js');
const globals = require('globals');
const jsdoc = require('eslint-plugin-jsdoc');

module.exports = [
    js.configs.recommended,
    {
        files: ['**/*.js'],
        ignores: [
            '**/node_modules/**',
            '**/dist/**',
            '**/build/**',
            '**/.venv/**',
            '**/static/lib/**',
        ],
        plugins: { jsdoc },
        languageOptions: {
            ecmaVersion: 2024,
            sourceType: 'module',
            globals: {
                ...globals.browser,
                ...globals.es2024,
                odoo: 'readonly',
                owl: 'readonly',
                luxon: 'readonly',
                openerp: 'readonly',
            },
        },
        rules: {
            'no-debugger': 'error',
            'no-undef': 'error',
            'no-unused-vars': [
                'warn',
                { argsIgnorePattern: '^_', varsIgnorePattern: '^_' },
            ],
            eqeqeq: ['error', 'always', { null: 'ignore' }],
            'no-fallthrough': 'error',
            'no-duplicate-imports': 'error',
            'prefer-const': 'warn',
            'jsdoc/check-tag-names': 'warn',
            'jsdoc/check-types': 'warn',
        },
    },
];
