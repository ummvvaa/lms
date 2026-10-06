module.exports = {
  root: true,
  env: { browser: true, es2022: true },
  extends: [
    'eslint:recommended',
    'plugin:@typescript-eslint/recommended',
  ],
  parser: '@typescript-eslint/parser',
  parserOptions: { ecmaVersion: 'latest', sourceType: 'module' },
  plugins: ['react-hooks', '@typescript-eslint'],
  rules: {
    'react-hooks/rules-of-hooks': 'error',
    'react-hooks/exhaustive-deps': 'warn',
    // перевод (eslint-rules/, подключаются --rulesdir): видимый текст — через
    // t(), у ключа есть kk и en, даты и числа — через lib/format.ts
    'i18n-text': 'error',
    'i18n-keys': 'error',
    'no-raw-locale': 'error',
    'i18n-module-scope': 'error',
    'i18n-concat': 'error',
  },
  overrides: [
    // словари — это и есть переводы; правила эти файлы проверяют, а не наоборот
    { files: ['src/i18n/kk.ts', 'src/i18n/en.ts'], rules: { 'i18n-text': 'off' } },
    // проверки vitest пишут названия и данные для разработчика, не для интерфейса
    { files: ['src/**/*.test.ts'], rules: { 'i18n-text': 'off' } },
    // сами правила пишут сообщения разработчику, а не интерфейсу
    { files: ['eslint-rules/**', '.eslintrc.cjs'], env: { node: true }, rules: { '@typescript-eslint/no-require-imports': 'off', 'i18n-text': 'off' } },
  ],
  ignorePatterns: ['dist', 'node_modules', 'src/api/schema.ts'],
}
