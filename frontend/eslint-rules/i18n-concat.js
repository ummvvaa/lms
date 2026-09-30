/**
 * Фраза не склеивается из кусков: `${t('до')} ${date}`, `{t('Отметить')} {n} {t('урок')}`.
 * В казахском и английском другой порядок слов, и из кусков фраза не
 * переводится. Нужна одна строка с подстановками: `t('до {date}', { date })`,
 * `tn(n, 'Отметить {n} урок|…')`.
 *
 * Склейка — перевод и соседний кусок (значение или другой перевод), между
 * которыми только пробел. Разделители « · », «, », « — » склейкой не считаются:
 * это список фактов, каждый факт — своя фраза. Подпись с двоеточием
 * («Причина:» перед значением) и законченное предложение («….») — тоже.
 */
'use strict'

const { translateCall, keyLiterals } = require('./_i18n.cjs')

/** Перевод, законченный сам по себе: подпись «…:» или предложение «….» */
function standalone(node) {
  const call = translateCall(node)
  if (!call) return false
  const keys = keyLiterals(node.arguments[call.index])
  return keys.length > 0 && keys.every((k) => /[:.!?…»)]\s*$/.test(k.value.split('|')[0]))
}

function isTranslated(node) {
  return Boolean(translateCall(node))
}

/** Элемент, а не слово: значок, кнопка, `cond && <Icon/>`, `cond ? <A/> : null`. */
function isElement(node) {
  if (!node) return true
  if (node.type === 'JSXElement' || node.type === 'JSXFragment') return true
  if (node.type === 'Literal' && node.value === null) return true
  if (node.type === 'LogicalExpression') return isElement(node.right)
  if (node.type === 'ConditionalExpression') return isElement(node.consequent) && isElement(node.alternate)
  return false
}

module.exports = {
  meta: {
    type: 'problem',
    docs: { description: 'фраза — одна строка с подстановками, не склейка кусков' },
    schema: [],
  },
  create(context) {
    const report = (node) =>
      context.report({ node, message: 'Фраза склеена из кусков — одна строка с подстановками: t(\'… {имя} …\', { имя }) или tn().' })

    /** Соседи: [узел, текст-разделитель, узел]. */
    function check(items) {
      for (let i = 0; i + 2 < items.length; i += 1) {
        const [left, gap, right] = [items[i], items[i + 1], items[i + 2]]
        if (gap.kind !== 'text' || left.kind !== 'node' || right.kind !== 'node') continue
        if (!/^\s+$/.test(gap.text) && gap.text !== '') continue
        const l = isTranslated(left.node)
        const r = isTranslated(right.node)
        if (!l && !r) continue
        if (isElement(left.node) || isElement(right.node)) continue
        if (l && standalone(left.node) && !r) continue
        if (l && r && standalone(left.node)) continue
        report(l ? left.node : right.node)
      }
    }

    return {
      TemplateLiteral(node) {
        const items = []
        node.quasis.forEach((quasi, index) => {
          items.push({ kind: 'text', text: quasi.value.cooked ?? '' })
          if (index < node.expressions.length) items.push({ kind: 'node', node: node.expressions[index] })
        })
        check(items)
      },
      'JSXElement, JSXFragment'(node) {
        const items = []
        for (const child of node.children) {
          if (child.type === 'JSXText') items.push({ kind: 'text', text: child.value.includes('\n') && !child.value.trim() ? '\n' : child.value })
          else if (child.type === 'JSXExpressionContainer' && child.expression.type !== 'JSXEmptyExpression') {
            const last = items[items.length - 1]
            if (last && last.kind === 'node') items.push({ kind: 'text', text: '' })
            items.push({ kind: 'node', node: child.expression })
          } else items.push({ kind: 'text', text: '|' })
        }
        check(items)
      },
    }
  },
}
