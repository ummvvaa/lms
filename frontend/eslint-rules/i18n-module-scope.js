/**
 * Перевод — только при показе, не на уровне модуля. `t()` вне функции
 * выполняется один раз при загрузке модуля, и строка остаётся на языке,
 * который был тогда: сменил язык — подпись не сменилась. На уровне модуля
 * строку помечают `tk('…')`, а переводят `t(значение)` при показе.
 */
'use strict'

const TRANSLATE = new Set(['t', 'tn', 'plural', 'counted'])
const FUNCTIONS = new Set(['FunctionDeclaration', 'FunctionExpression', 'ArrowFunctionExpression'])

module.exports = {
  meta: {
    type: 'problem',
    docs: { description: 't() не вызывается на уровне модуля' },
    schema: [],
  },
  create(context) {
    return {
      CallExpression(node) {
        if (node.callee.type !== 'Identifier' || !TRANSLATE.has(node.callee.name)) return
        for (let parent = node.parent; parent; parent = parent.parent) {
          if (FUNCTIONS.has(parent.type)) return
          // поле класса считается при создании экземпляра, а не модуля
          if (parent.type === 'PropertyDefinition' && !parent.static) return
        }
        context.report({ node, message: `${node.callee.name}() на уровне модуля застынет на языке загрузки — tk('…') здесь и t() при показе.` })
      },
    }
  },
}
