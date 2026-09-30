/**
 * У каждого ключа перевода есть казахский и английский, и они совпадают
 * с исходной строкой по подстановкам `{имя}` и по числу форм.
 *
 * Ключ — строковый литерал в `t()`, `tk()`, `tn()`, `plural()`, `counted()`.
 * Ключ из переменной (`t(row.title)`) проверить здесь нельзя: его литерал
 * помечен `tk()` там, где он написан, и проверяется там.
 */
'use strict'

const { PLURAL_CALLS, translateCall, keyLiterals, dictionary, placeholders } = require('./_i18n.cjs')

/** Сколько форм числа бывает у языка: у русского три, у казахского и английского две. */
const MAX_FORMS = { kk: 2, en: 2 }

module.exports = {
  meta: {
    type: 'problem',
    docs: { description: 'ключ перевода есть в kk.ts и en.ts, подстановки и формы совпадают' },
    schema: [],
  },
  create(context) {
    return {
      CallExpression(node) {
        const call = translateCall(node)
        if (!call) return
        const arg = node.arguments[call.index]
        if (!arg) return
        if (arg.type === 'TemplateLiteral' || arg.type === 'BinaryExpression') {
          context.report({ node: arg, message: 'Ключ перевода собран из кусков — строка целиком с подстановками {имя}.' })
          return
        }
        for (const literal of keyLiterals(arg)) check(literal, call)
      },
    }

    function check(arg, call) {
        const source = arg.value
        if (!source) return
        const plural = PLURAL_CALLS.has(call.name)
        const sourceForms = source.split('|')
        if (plural && sourceForms.length !== 3 && sourceForms.length !== 1) {
          context.report({ node: arg, message: `Русских форм числа три («один|два|пять»), а здесь ${sourceForms.length}.` })
        }
        const expected = placeholders(source).join(',')
        for (const lang of ['kk', 'en']) {
          const translated = dictionary(lang).get(source)
          if (translated === undefined) {
            context.report({ node: arg, message: `Нет перевода ${lang}: «${source}».` })
            continue
          }
          if (placeholders(translated).join(',') !== expected) {
            context.report({ node: arg, message: `Подстановки ${lang} не совпадают с исходной строкой: «${translated}».` })
          }
          const forms = translated.split('|').length
          if (plural ? forms > MAX_FORMS[lang] : forms !== sourceForms.length) {
            context.report({ node: arg, message: `Число форм ${lang} не подходит: «${translated}».` })
          }
        }
    }
  },
}
