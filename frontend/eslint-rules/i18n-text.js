/**
 * Видимый текст — только через перевод. Ловит кириллицу в тексте JSX,
 * в строках и в шаблонных строках вне позиции ключа `t()`, `tk()`, `tn()`,
 * `plural()`, `counted()`. Так в интерфейс не попадёт русская строка мимо
 * словарей — именно так раньше оставались карточки без перевода.
 *
 * Строка в таблице подписей на уровне модуля помечается `tk('…')` и
 * переводится `t()` при показе. Не показываемая строка (сравнение с данными,
 * разбор файла) — `// eslint-disable-next-line i18n-text -- почему`.
 *
 * Базовая линия (`i18n-baseline.json`, файл → число мест) не даёт числу
 * непереведённых мест в файле расти, пока их переносят в словари; когда
 * её нет, правило ловит каждое место.
 */
'use strict'

const fs = require('fs')
const path = require('path')
const { CYRILLIC, translateCall } = require('./_i18n.cjs')

const ROOT = path.join(__dirname, '..')
const BASELINE_FILE = path.join(__dirname, 'i18n-baseline.json')
const baseline = fs.existsSync(BASELINE_FILE) ? JSON.parse(fs.readFileSync(BASELINE_FILE, 'utf8')) : {}

/** Строка стоит на месте ключа перевода — сама или веткой `?:` / `||`. */
function inKeyPosition(node) {
  let child = node
  let parent = node.parent
  while (parent && (parent.type === 'ConditionalExpression' || parent.type === 'LogicalExpression')) {
    if (parent.type === 'ConditionalExpression' && parent.test === child) return false
    child = parent
    parent = parent.parent
  }
  const call = translateCall(parent)
  return Boolean(call && parent.arguments[call.index] === child)
}

/** Места, где строка не показывается: импорт, тип, ключ объекта, консоль. */
function notShown(node) {
  const parent = node.parent
  if (!parent) return false
  if (parent.type === 'ImportDeclaration' || parent.type === 'ExportAllDeclaration' || parent.type === 'ExportNamedDeclaration') return true
  if (parent.type === 'TSLiteralType') return true
  if (parent.type === 'Property' && parent.key === node) return true
  if (
    parent.type === 'CallExpression' &&
    parent.callee.type === 'MemberExpression' &&
    parent.callee.object.type === 'Identifier' &&
    parent.callee.object.name === 'console'
  )
    return true
  return false
}

function preview(text) {
  const flat = text.replace(/\s+/g, ' ').trim()
  return flat.length > 60 ? `${flat.slice(0, 57)}…` : flat
}

module.exports = {
  meta: {
    type: 'problem',
    docs: { description: 'видимый текст — только через t()' },
    schema: [],
  },
  create(context) {
    const file = path.relative(ROOT, context.filename ?? context.getFilename())
    const found = []
    return {
      JSXText(node) {
        if (CYRILLIC.test(node.value)) found.push({ node, text: node.value })
      },
      Literal(node) {
        if (typeof node.value !== 'string' || !CYRILLIC.test(node.value)) return
        if (inKeyPosition(node) || notShown(node)) return
        found.push({ node, text: node.value })
      },
      TemplateLiteral(node) {
        const text = node.quasis.map((q) => q.value.cooked ?? '').join('…')
        if (!CYRILLIC.test(text) || node.parent.type === 'TSLiteralType') return
        found.push({ node, text })
      },
      'Program:exit'() {
        const allowed = baseline[file] ?? 0
        if (found.length <= allowed) return
        for (const { node, text } of found) {
          context.report({
            node,
            message: `Текст мимо перевода: «${preview(text)}» — t('…') или tk('…'). В файле ${found.length}, допускается ${allowed}.`,
          })
        }
      },
    }
  },
}
