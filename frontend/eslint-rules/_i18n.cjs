/**
 * Общее для правил `i18n-text` и `i18n-keys`: какие вызовы переводят,
 * где у них ключ и как читаются словари kk.ts и en.ts.
 *
 * Файл не `.js`: `--rulesdir` грузит правилом каждый `.js` в папке.
 */
'use strict'

const fs = require('fs')
const path = require('path')

/** Вызов перевода → номер аргумента с ключом. `tk` — метка ключа без перевода. */
const KEY_ARG = { t: 0, tk: 0, tn: 1, plural: 1, counted: 1 }
/** Вызовы, у которых ключ — формы числа через черту. */
const PLURAL_CALLS = new Set(['tn', 'plural', 'counted'])

const CYRILLIC = /[А-Яа-яЁёӘәҒғҚқҢңӨөҰұҮүҺһІі]/

/** Вызов перевода и место ключа в нём: `{ name, index }` или null. */
function translateCall(node) {
  if (!node || node.type !== 'CallExpression' || node.callee.type !== 'Identifier') return null
  const index = KEY_ARG[node.callee.name]
  return index === undefined ? null : { name: node.callee.name, index }
}

const DICT_DIR = path.join(__dirname, '..', 'src', 'i18n')
const cache = new Map()

/** Словарь `kk` или `en` как Map ключ → перевод; перечитывается, если файл изменился. */
function dictionary(name) {
  const file = path.join(DICT_DIR, `${name}.ts`)
  const mtime = fs.statSync(file).mtimeMs
  const hit = cache.get(name)
  if (hit && hit.mtime === mtime) return hit.map
  const { parse } = require('@typescript-eslint/parser')
  const ast = parse(fs.readFileSync(file, 'utf8'), { loc: false, range: false })
  const map = new Map()
  for (const statement of ast.body) {
    const declaration = statement.type === 'ExportNamedDeclaration' ? statement.declaration : statement
    if (!declaration || declaration.type !== 'VariableDeclaration') continue
    for (const item of declaration.declarations) {
      if (!item.init || item.init.type !== 'ObjectExpression') continue
      for (const prop of item.init.properties) {
        if (prop.type !== 'Property') continue
        const key = prop.key.type === 'Identifier' ? prop.key.name : prop.key.value
        const value = prop.value.type === 'Literal' ? prop.value.value : prop.value.type === 'TemplateLiteral' && prop.value.expressions.length === 0 ? prop.value.quasis[0].value.cooked : null
        if (typeof key === 'string' && typeof value === 'string') map.set(key, value)
      }
    }
  }
  cache.set(name, { mtime, map })
  return map
}

/**
 * Литералы, которые служат ключом в позиции ключа: сам литерал или ветви
 * `a ? 'x' : 'y'` и `a || 'x'`. Остальное (переменная, вызов) — не литерал.
 */
function keyLiterals(node) {
  if (!node) return []
  if (node.type === 'Literal' && typeof node.value === 'string') return [node]
  if (node.type === 'ConditionalExpression') return [...keyLiterals(node.consequent), ...keyLiterals(node.alternate)]
  if (node.type === 'LogicalExpression') return [...keyLiterals(node.left), ...keyLiterals(node.right)]
  return []
}

/** Имена подстановок `{имя}` строки. */
function placeholders(text) {
  return [...new Set([...text.matchAll(/\{(\w+)\}/g)].map((m) => m[1]))].sort()
}

module.exports = { CYRILLIC, PLURAL_CALLS, translateCall, keyLiterals, dictionary, placeholders }
