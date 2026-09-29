/**
 * Группы — отдельный экран директора школы.
 *
 * Раньше это была секция дашборда, до которой надо было доскроллить.
 * Данные те же, что и у дашборда (`/dashboards/behavior/`), запрос общий:
 * TanStack Query отдаёт его из кэша.
 */
import { useState } from 'react'
import { useDashboard } from '../../api/hooks'
import { Segmented } from '../../components/patterns'
import { PARALLELS, parallelTitle } from '../../lib/parallels'
import EmptyDashboard, { useSchoolIsEmpty } from '../../components/EmptyDashboard'
import { Bar, Chip, EmptyNote, ErrorNote, Loading, ScreenHead } from '../../components/ui'
import { t } from '../../i18n'
import type { BehaviorData } from './data'

export default function Groups() {
  const { data, isLoading, error } = useDashboard<BehaviorData>('behavior')
  // фильтр по параллели — у сотрудника; учеников не касается
  const [parallel, setParallel] = useState('')
  const schoolIsEmpty = useSchoolIsEmpty()
  if (isLoading) return <Loading kind="table" />
  if (error) return <ErrorNote error={error} />
  if (!data) return null
  if (schoolIsEmpty)
    return (
      <EmptyDashboard
        title={t('Группы')}
        hint={t('Здесь появятся учебные группы')}
        what={t('Заведите группы — и по ним пойдёт вся раскладка.')}
        detail={t(
          'У каждой группы видно число учеников, заполненность профилей и сколько человек в зоне риска.',
        )}
      />
    )

  return (
    <div>
      <ScreenHead
        title={t('Группы')}
      />

      <Segmented<string>
        value={parallel}
        onChange={setParallel}
        label={t('Параллель')}
        items={[
          { value: '', label: `${t('Все')} ${data.groups.length}` },
          ...PARALLELS.map((value) => ({
            value: String(value),
            label: `${value} · ${data.groups.filter((g) => g.parallel === value).length}`,
          })),
        ]}
      />

      <div className="grid grid--cards">
        {data.groups.filter((g) => !parallel || String(g.parallel) === parallel).map((g) => (
          <div key={g.code} className="card card-pad">
            <div className="row-between">
              <b className="t-value">
                {g.code} <span className="t-note">{parallelTitle(g.parallel)}</span>
              </b>
              <Chip tone="neutral" className="num">
                {g.students_count} чел.
              </Chip>
            </div>
            <div className="row-between mt-3.5 mx-0 mb-1.5 t-note">
              <span className="muted">{t('Заполненность профилей')}</span>
              <b className="num">{g.students_count ? Math.round((g.filled / g.students_count) * 100) : 0}%</b>
            </div>
            <Bar percent={g.students_count ? (g.filled / g.students_count) * 100 : 0} />
            {g.critical > 0 && (
              <div className="mt-3">
                <Chip tone="bad" className="num">
                  {g.critical} в зоне риска
                </Chip>
              </div>
            )}
          </div>
        ))}
        {data.groups.length === 0 && <EmptyNote what="учебных групп пока нет" who="заводит администратор" />}
      </div>
    </div>
  )
}
