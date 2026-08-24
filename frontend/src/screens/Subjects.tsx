/** Предметы олимпиад — справочник директора талантов. */
import DirectoryList, { type DirectorySetup } from './DirectoryList'

const SETUP: DirectorySetup = {
  kind: 'subjects',
  title: 'Предметы олимпиад',
  subtitle: 'Из этого списка предмет выбирается у активности. Свободный текст сюда больше не попадает.',
  one: 'предмет',
  groupLabel: 'Направление',
  groupField: 'area',
  groups: [
    { value: 'exact', title: 'Точные науки' },
    { value: 'natural', title: 'Естественные науки' },
    { value: 'humanities', title: 'Гуманитарные науки' },
    { value: 'languages', title: 'Языки' },
    { value: 'other', title: 'Прочее' },
  ],
  emptyWhat:
    'Пока ни одного предмета. Заведите те, по которым ваши ученики выступают: ' +
    'после этого предмет можно будет выбрать у активности, а отчёты начнут собираться по предметам.',
  forms: ['Математика', 'Республиканская олимпиада, областной и городской этапы', ''],
}

export default function Subjects() {
  return <DirectoryList setup={SETUP} />
}
