/**
 * Короткое имя теста для вкладки — по методике: «Карта интересов (А. Е. Голомшток…)» —
 * «Карта интересов», «Опросник … (Л. Йовайши)» — «Йовайши», «… (ДДО, Е. А. Климов)» —
 * «Климов (ДДО)». Полное название стоит подписью под вкладками.
 */
export function shortTitle(title: string): string {
  const match = /^(.*?)\s*\((.*)\)\s*$/.exec(title)
  if (!match) return title
  const [, head, inside] = match
  if (head.length <= 24) return head
  const parts = inside.split(',').map((part) => part.trim())
  const author = parts.find((part) => /\p{Lu}\.\s*\p{Lu}/u.test(part) || /^\p{Lu}\.\s/u.test(part))
  if (!author) return title
  const surname = author.split(/\s+/).pop() ?? author
  const code = parts.find((part) => part !== author && /^\p{Lu}{2,}$/u.test(part))
  return code ? `${surname} (${code})` : surname
}
