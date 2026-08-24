/** Виды спорта — справочник директора спорта. */
import DirectoryList, { type DirectorySetup } from './DirectoryList'

const SETUP: DirectorySetup = {
  kind: 'sport-types',
  title: 'Виды спорта',
  subtitle:
    'Из этого списка вид спорта выбирается в профиле ученика. Свободный текст сюда больше не попадает.',
  one: 'вид спорта',
  groupLabel: 'Категория',
  groupField: 'category',
  groups: [
    { value: 'team', title: 'Командный' },
    { value: 'individual', title: 'Индивидуальный' },
    { value: 'martial', title: 'Единоборства' },
    { value: 'other', title: 'Прочее' },
  ],
  emptyWhat:
    'Пока ни одного вида спорта. Заведите те, которыми занимаются ваши ученики: ' +
    'после этого вид спорта можно будет выбрать в профиле, а дашборд начнёт считать по видам.',
  forms: ['Футбол', 'Городская лига, две тренировки в неделю', ''],
}

export default function SportTypes() {
  return <DirectoryList setup={SETUP} />
}
