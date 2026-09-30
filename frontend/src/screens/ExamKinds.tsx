/** Справочник экзаменов — ведёт академический директор (фаза 39). */
import DirectoryList, { type DirectorySetup } from './DirectoryList'
import { tk } from '../i18n'

const SETUP: DirectorySetup = {
  kind: 'exam-kinds',
  title: tk('Экзамены'),
  subtitle: tk(
    'Из этого списка ученик выбирает экзамен для цели. Школа показывает ученикам те экзамены, у которых стоит галочка «Показывать в списке выбора».',
  ),
  one: tk('экзамен'),
  groupLabel: '',
  groups: [],
  extras: [
    { field: 'min_score', label: tk('Минимум шкалы') },
    { field: 'max_score', label: tk('Максимум шкалы') },
  ],
  emptyWhat: tk(
    'Пока ни одного экзамена. Заведите те, что сдают ваши ученики: после этого экзамен можно выбрать в цели, а календарь и напоминания начнут работать.',
  ),
  forms: ['IELTS', tk('Международный экзамен по английскому'), ''],
}

export default function ExamKinds() {
  return <DirectoryList setup={SETUP} />
}
