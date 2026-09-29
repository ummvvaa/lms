/**
 * Вариант ответа в тренажёре: буква, текст, состояние выбора.
 *
 * Свой элемент, а не кнопка реестра: у кнопки реестра правило по двум
 * атрибутам (`[data-slot][data-variant]`), и класс выбранного варианта ему
 * проигрывал — нажатие проходило, а на экране не менялось ничего (найдено
 * владельцем). Здесь выбор — атрибут `data-picked`, стили — в
 * `components/language.css`, а сам элемент — единственный на все экраны.
 */
import type { ReactNode } from 'react'

export function AnswerOption({
  letter,
  picked,
  onPick,
  children,
}: {
  letter: string
  picked: boolean
  onPick: () => void
  children: ReactNode
}) {
  return (
    <button
      type="button"
      role="radio"
      aria-checked={picked}
      data-slot="answer-option"
      data-picked={picked ? 'true' : 'false'}
      className="answer-option"
      onClick={onPick}
    >
      <span className="answer-option__letter">{letter}</span>
      <span className="answer-option__text">{children}</span>
    </button>
  )
}
