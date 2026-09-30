/** Виды спорта — справочник директора спорта. */
import { tk } from '../i18n'
import DirectoryList, { type DirectorySetup } from './DirectoryList'

const SETUP: DirectorySetup = {
  kind: 'sport-types',
  title: tk('Виды спорта'),
  subtitle: tk('Из этого списка вид спорта выбирается в профиле ученика. Свободный текст сюда больше не попадает.'),
  one: tk('вид спорта'),
  groupLabel: tk('Категория'),
  groupField: 'category',
  groups: [
    { value: 'team', title: tk('Командный') },
    { value: 'individual', title: tk('Индивидуальный') },
    { value: 'martial', title: tk('Единоборства') },
    { value: 'other', title: tk('Прочее') },
  ],
  emptyWhat: tk(
    'Пока ни одного вида спорта. Заведите те, которыми занимаются ваши ученики: после этого вид спорта можно будет выбрать в профиле, а дашборд начнёт считать по видам.',
  ),
  forms: [tk('Футбол'), tk('Городская лига, две тренировки в неделю'), ''],
}

export default function SportTypes() {
  return <DirectoryList setup={SETUP} />
}
