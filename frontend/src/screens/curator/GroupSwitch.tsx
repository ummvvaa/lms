/**
 * Переключатель групп куратора (фаза 61).
 *
 * «Все мои группы» и сегмент на каждую — общий `Segmented`. Фильтрует всё:
 * очередь, учеников, счётчики, корзины и задачи. У куратора с одной группой
 * переключателя нет — выбирать не из чего; группа названа текстом, чтобы
 * было видно, по кому собран экран (фаза 80).
 */
import { type CuratorGroup } from '../../api/hooks'
import { Segmented } from '../../components/patterns'
import { counted } from '../../components/ui'
import { t } from '../../i18n'
import { ALL } from './state'

export default function GroupSwitch({
  groups,
  value,
  onChange,
  /** без пункта «все»: экран собирается по одной группе */
  single = false,
}: {
  groups: CuratorGroup[]
  value: string
  onChange: (next: string) => void
  single?: boolean
}) {
  if (groups.length === 0) return null
  if (groups.length === 1)
    return (
      <p className="gswitch gswitch--one t-note">
        <b>{`${t('Группа')} ${groups[0].code}`}</b>
        <span className="num">{counted(groups[0].students, ['ученик', 'ученика', 'учеников'])}</span>
      </p>
    )

  return (
    <div className="gswitch">
      <Segmented
        value={value}
        onChange={onChange}
        label={t('Мои группы')}
        items={[
          ...(single ? [] : [{ value: ALL, label: t('Все мои группы') }]),
          ...groups.map((group) => ({
            value: group.code,
            label: (
              <>
                {group.code} <span className="gswitch__note num">{group.students}</span>
              </>
            ),
          })),
        ]}
      />
    </div>
  )
}
