/** Справочник экзаменов — ведёт академический директор (фаза 39). */
import DirectoryList, { type DirectorySetup } from './DirectoryList'

const SETUP: DirectorySetup = {
  kind: 'exam-kinds',
  title: 'Экзамены',
  subtitle:
    'Из этого списка ученик выбирает экзамен для цели. ЕНТ здесь наравне с международными: ' +
    'часть учеников сдаёт и его, и IELTS с SAT.',
  one: 'экзамен',
  groupLabel: '',
  groups: [],
  extras: [
    { field: 'min_score', label: 'Минимум шкалы' },
    { field: 'max_score', label: 'Максимум шкалы' },
  ],
  emptyWhat:
    'Пока ни одного экзамена. Заведите те, что сдают ваши ученики: после этого экзамен ' +
    'можно выбрать в цели, а календарь и напоминания начнут работать.',
  forms: ['IELTS', 'Международный экзамен по английскому', ''],
}

export default function ExamKinds() {
  return <DirectoryList setup={SETUP} />
}
