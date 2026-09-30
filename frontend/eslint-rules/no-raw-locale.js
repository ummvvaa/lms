/**
 * Даты и числа — только через `lib/format.ts`: там язык берётся из интерфейса.
 * `toLocaleDateString('ru')` в экране зашивал язык, и казахский интерфейс
 * показывал «30 сентября».
 */
'use strict'

const ALLOWED = [/src\/lib\/format\.ts$/, /src\/lib\/dates\.ts$/, /src\/i18n\/index\.ts$/]
const METHODS = new Set(['toLocaleDateString', 'toLocaleTimeString', 'toLocaleString'])

module.exports = {
  meta: {
    type: 'problem',
    docs: { description: 'даты и числа форматируются только в lib/format.ts' },
    schema: [],
  },
  create(context) {
    const file = context.filename ?? context.getFilename()
    if (ALLOWED.some((re) => re.test(file))) return {}
    return {
      CallExpression(node) {
        const callee = node.callee
        if (callee.type === 'MemberExpression' && !callee.computed && METHODS.has(callee.property.name)) {
          context.report({ node, message: `${callee.property.name} зашивает язык — возьмите функцию из lib/format.ts.` })
        }
      },
      NewExpression(node) {
        const callee = node.callee
        if (callee.type === 'MemberExpression' && callee.object.type === 'Identifier' && callee.object.name === 'Intl') {
          context.report({ node, message: 'Intl в экране зашивает язык — возьмите функцию из lib/format.ts.' })
        }
      },
    }
  },
}
