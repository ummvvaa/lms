/**
 * Отбор в олимпиадную группу — экран директора талантов.
 *
 * Отметка открывает ученику раздел материалов, снятие — закрывает.
 * Правка идёт через журнал изменений, как любое доменное поле.
 */
import { useState } from 'react'
import { useOlympiadGroup, usePickForGroup } from '../api/hooks'
import Empty from '../components/Empty'
import { counted, ErrorNote, Loading, ScreenHead } from '../components/ui'
import './materials.css'
import { t } from '../i18n'
import { SelectField } from '../components/SelectField'
import { Input } from '../components/ui/input'
import { Switch } from '../components/ui/switch'
import { Badge } from '../components/ui/badge'
import { Button } from '../components/ui/button'

export default function OlympiadGroup() {
  const [query, setQuery] = useState('')
  const [grade, setGrade] = useState('')
  const [onlyMembers, setOnlyMembers] = useState(false)
  const [flash, setFlash] = useState<string | null>(null)

  const list = useOlympiadGroup({ q: query, grade, member: onlyMembers ? 'true' : undefined })
  const pick = usePickForGroup()

  if (list.isLoading) return <Loading kind="table" />
  if (list.isError) return <ErrorNote error={list.error} />

  const rows = list.data?.students ?? []

  return (
    <div>
      <ScreenHead
        title={t('Олимпиадная группа')}
        subtitle={t(
          'Отмеченным открыт раздел материалов: они выкладывают разборы и видят чужие. Остальные его не видят вовсе.',
        )}
      />

      <Badge variant="mute" className="badge--line mat__flash">
        {list.data?.detail}
      </Badge>
      {flash && (
        <Badge variant="ok" className="badge--line mat__flash">
          {flash}
        </Badge>
      )}

      <div className="card card-pad mat__filters">
        <Input
          placeholder={t('Фамилия или имя')}
          aria-label={t('Поиск ученика')}
          value={query}
          onChange={(event) => setQuery(event.target.value)}
        />
        <SelectField aria-label={t('Класс')} value={grade} onChange={(event) => setGrade(event.target.value)}>
          <option value="">{t('все классы')}</option>
          {[9, 10, 11, 12].map((n) => (
            <option key={n} value={n}>
              {n} класс
            </option>
          ))}
        </SelectField>
        <label className="mat__check">
          <Switch checked={onlyMembers} onCheckedChange={setOnlyMembers} />
          {t('только те, кто в группе')}
        </label>
      </div>

      {rows.length === 0 ? (
        <Empty
          icon="medal"
          title={t('Никого не нашлось')}
          what={t('Снимите фильтры или заведите учеников — карточки заводит администратор.')}
          action={t('Снять фильтры')}
          onAction={() => {
            setQuery('')
            setGrade('')
            setOnlyMembers(false)
          }}
        />
      ) : (
        <div className="card card-pad">
          <table className="tbl dir__table">
            <thead>
              <tr>
                <th>{t('Ученик')}</th>
                <th>{t('Класс')}</th>
                <th>{t('Группа')}</th>
                <th>{t('Материалов')}</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.id}>
                  <td style={{ fontWeight: 650 }}>{row.full_name}</td>
                  <td className="muted num">{row.grade}</td>
                  <td className="muted">{row.group || '—'}</td>
                  <td className="num">
                    {row.materials === 0 ? (
                      <span className="muted">{t('нет')}</span>
                    ) : (
                      counted(row.materials, ['материал', 'материала', 'материалов'])
                    )}
                  </td>
                  <td style={{ textAlign: 'right' }}>
                    <Button
                      variant={row.in_group ? undefined : 'outline'}
                      size="sm"
                      disabled={pick.isPending}
                      onClick={() =>
                        pick.mutate(
                          { student: row.id, member: !row.in_group },
                          { onSuccess: (answer) => setFlash(answer.detail) },
                        )
                      }
                    >
                      {row.in_group ? '✓ В группе' : 'Отметить'}
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
