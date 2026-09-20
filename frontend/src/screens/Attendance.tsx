/**
 * Посещаемость: группа за день и журнал за месяц.
 *
 * Экран один на двоих — куратор видит свои группы, директор школы все.
 * Разделять было бы двумя экранами, которые расходятся на третий месяц.
 * Разница в праве: вносит посещаемость куратор (и администратор), директор
 * школы лист читает — та же таблица, без переключения «был / не был».
 * Право приходит с сервера полем `may_mark`.
 *
 * Лист открывается с отметкой «все присутствуют»: снять три отметки
 * быстрее, чем поставить двадцать, а «никого не отмечали» и «все были» —
 * это разные вещи, и вторая встречается чаще. Что день ещё не сохраняли,
 * видно по подписи; у читающего неотмеченный день так и назван.
 *
 * Причина отсутствия — по желанию: заставлять писать «болел» у каждого
 * значит получить двадцать пустых «болел».
 *
 * Журнал — второй вид того же экрана: строки — ученики, столбцы — дни
 * месяца, в ячейке «был / не был / выходной», справа итог «отсутствовал
 * N из M». Выходной — день без единой отметки по группе: календаря
 * праздников нет. Выгрузка — через общий предпросмотр.
 */
import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { toast } from 'sonner'
import {
  useAttendanceDay,
  useAttendanceJournal,
  useSaveAttendance,
  type AttendanceCell,
  type AttendanceRow,
} from '../api/hooks'
import { ExportPreview } from '../components/ExportPreview'
import { DataCard, ErrorNote, Loading, ScreenHead, ScreenTabs } from '../components/ui'
import { Switch } from '../components/ui/switch'
import { Badge } from '../components/ui/badge'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'
import { SelectField } from '../components/SelectField'
import { t } from '../i18n'
import './attendance.css'

/**
 * Сегодня — по часам человека, а не по UTC.
 *
 * `toISOString()` отдаёт день в UTC, а школа живёт по Алматы (+5): после
 * семи вечера экран открывался бы вчерашним днём, и «сегодня» нельзя было
 * бы выбрать вовсе — `max` не пускает.
 */
const today = (): string => {
  const now = new Date()
  const month = String(now.getMonth() + 1).padStart(2, '0')
  const day = String(now.getDate()).padStart(2, '0')
  return `${now.getFullYear()}-${month}-${day}`
}

type View = 'day' | 'journal'

export default function Attendance() {
  // группа и день приходят адресом (фаза 70): из карточки ученика
  // кликают по дню пропуска и попадают ровно в этот лист
  const [params, setParams] = useSearchParams()
  const view: View = params.get('view') === 'journal' ? 'journal' : 'day'
  const [group, setGroup] = useState<string>(params.get('group') ?? '')
  const [date, setDate] = useState<string>(params.get('date') ?? today())
  const sheet = useAttendanceDay(group, date)
  const save = useSaveAttendance()
  const [rows, setRows] = useState<AttendanceRow[]>([])

  // группа по умолчанию — первая своя: у куратора она чаще всего одна
  useEffect(() => {
    const groups = sheet.data?.groups ?? []
    if (!group && groups.length > 0) setGroup(String(groups[0].id))
  }, [sheet.data, group])

  useEffect(() => {
    if (sheet.data) setRows(sheet.data.rows)
  }, [sheet.data])

  const toggle = (student: number) =>
    setRows((old) => old.map((row) => (row.student === student ? { ...row, present: !row.present } : row)))

  const setReason = (student: number, reason: string) =>
    setRows((old) => old.map((row) => (row.student === student ? { ...row, reason } : row)))

  const absent = rows.filter((row) => !row.present).length

  if (sheet.isLoading && !sheet.data) return <Loading />

  const groups = sheet.data?.groups ?? []
  // право с сервера: куратор и администратор отмечают, директор школы читает
  const mayMark = sheet.data?.may_mark ?? false

  const tabs = (
    <ScreenTabs<View>
      value={view}
      onChange={(next) => {
        const query = new URLSearchParams(params)
        if (next === 'journal') query.set('view', 'journal')
        else query.delete('view')
        setParams(query, { replace: true })
      }}
      items={[
        { value: 'day', label: t('День') },
        { value: 'journal', label: t('Журнал за месяц') },
      ]}
    />
  )

  if (view === 'journal')
    return (
      <div>
        <ScreenHead
          title={t('Посещаемость')}
          subtitle={t('Группа за месяц: кто и в какие дни отсутствовал.')}
        />
        {tabs}
        <Journal group={group} onGroup={setGroup} groups={groups} />
      </div>
    )

  return (
    <div>
      <ScreenHead
        title={t('Посещаемость')}
        subtitle={
          mayMark
            ? t('Отметьте тех, кого не было. Остальные считаются присутствовавшими.')
            : t('Посещаемость вносит куратор группы. Здесь она на чтение.')
        }
      />
      {tabs}

      <div className="card card-pad att__bar">
        <label className="att__field">
          <span className="eyebrow">{t('Группа')}</span>
          <SelectField
            aria-label={t('Группа')}
            value={group}
            onChange={(event) => setGroup(event.target.value)}
          >
            {groups.map((row) => (
              <option key={row.id} value={row.id}>
                {row.code}
              </option>
            ))}
          </SelectField>
        </label>
        <label className="att__field">
          <span className="eyebrow">{t('День')}</span>
          <Input
            type="date"
            value={date}
            max={today()}
            aria-label={t('День')}
            onChange={(event) => setDate(event.target.value)}
          />
        </label>
        <span className="cfilters__spacer" />
        {sheet.data?.saved && <Badge variant="ok">{t('день отмечен')}</Badge>}
        {sheet.data?.late && <Badge variant="warn">{t('правка задним числом')}</Badge>}
        <Badge variant={absent > 0 ? 'warn' : 'mute'} className="num">
          {t('Отсутствуют:')} {absent}
        </Badge>
        {mayMark && (
          <Button
            disabled={save.isPending || rows.length === 0}
            onClick={() =>
              save.mutate(
                { group: Number(group), date, rows },
                {
                  onSuccess: (data) => toast.success(`${t('Отмечено учеников:')} ${data.written}`),
                  onError: (error) => toast.error(error.message),
                },
              )
            }
          >
            {t('Сохранить день')}
          </Button>
        )}
      </div>

      {sheet.error && <ErrorNote error={sheet.error} />}

      <DataCard
        title={sheet.data?.group_code ?? t('Группа')}
        note={
          !mayMark
            ? sheet.data?.saved
              ? t('Отметки куратора за этот день')
              : t('Этот день куратор ещё не отмечал')
            : sheet.data?.late
              ? t('День старше недели: правка попадёт в журнал отдельной записью')
              : t('Нажмите на строку, чтобы снять отметку')
        }
        count={rows.length}
      >
        {rows.length === 0 && <p className="muted">{t('В группе нет учеников')}</p>}
        <ul className="att__list">
          {rows.map((row) => (
            <li key={row.student} className={`att__row${row.present ? '' : ' att__row--absent'}`}>
              {mayMark ? (
                <button
                  type="button"
                  className="att__mark"
                  aria-pressed={!row.present}
                  aria-label={`${row.full_name}: ${row.present ? t('был') : t('не был')}`}
                  onClick={() => toggle(row.student)}
                >
                  {row.present ? t('был') : t('не был')}
                </button>
              ) : (
                // читающему — слово, а не кнопка; неотмеченный день так и назван:
                // «был» по умолчанию здесь выглядел бы как факт
                <span className="att__mark att__mark--read">
                  {!row.marked ? t('не отмечен') : row.present ? t('был') : t('не был')}
                </span>
              )}
              <span className="att__name">{row.full_name}</span>
              {!mayMark && !row.present && row.reason && <span className="muted att__why">{row.reason}</span>}
              {mayMark && !row.present && (
                <Input
                  className="att__reason"
                  value={row.reason}
                  placeholder={t('Причина — по желанию')}
                  aria-label={`${t('Причина')}: ${row.full_name}`}
                  onChange={(event) => setReason(row.student, event.target.value)}
                />
              )}
            </li>
          ))}
        </ul>
      </DataCard>
    </div>
  )
}

/** Текущий месяц — по часам человека, как и «сегодня». */
const thisMonth = (): string => today().slice(0, 7)

const shiftMonth = (month: string, by: number): string => {
  const [year, number] = month.split('-').map(Number)
  const moved = new Date(year, number - 1 + by, 1)
  return `${moved.getFullYear()}-${String(moved.getMonth() + 1).padStart(2, '0')}`
}

const monthTitle = (month: string): string => {
  const [year, number] = month.split('-').map(Number)
  return new Date(year, number - 1, 1).toLocaleDateString('ru', { month: 'long', year: 'numeric' })
}

/** Значок ячейки: слово целиком — в подсказке и для читалки, в клетке — знак. */
const CELL_SIGN: Record<AttendanceCell, string> = { present: '+', absent: 'н', off: '', unmarked: '—' }

function Journal({
  group,
  onGroup,
  groups,
}: {
  group: string
  onGroup: (next: string) => void
  groups: { id: number; code: string }[]
}) {
  const [month, setMonth] = useState(thisMonth())
  const [absentOnly, setAbsentOnly] = useState(false)
  const [exporting, setExporting] = useState(false)
  const journal = useAttendanceJournal(group, month, absentOnly, true)
  const data = journal.data

  const exportPath = `/attendance/journal/export/?month=${month}${group ? `&group=${group}` : ''}${
    absentOnly ? '&absent_only=1' : ''
  }`

  return (
    <>
      <div className="card card-pad att__bar">
        <label className="att__field">
          <span className="eyebrow">{t('Группа')}</span>
          <SelectField
            aria-label={t('Группа')}
            value={group}
            onChange={(event) => onGroup(event.target.value)}
          >
            {groups.map((row) => (
              <option key={row.id} value={row.id}>
                {row.code}
              </option>
            ))}
          </SelectField>
        </label>
        <div className="att__field">
          <span className="eyebrow">{t('Месяц')}</span>
          <div className="att__month">
            <Button
              variant="outline"
              size="sm"
              aria-label={t('Предыдущий месяц')}
              onClick={() => setMonth(shiftMonth(month, -1))}
            >
              {'←'}
            </Button>
            <span className="att__monthname" aria-live="polite">
              {monthTitle(month)}
            </span>
            <Button
              variant="outline"
              size="sm"
              aria-label={t('Следующий месяц')}
              disabled={month >= thisMonth()}
              onClick={() => setMonth(shiftMonth(month, 1))}
            >
              {'→'}
            </Button>
          </div>
        </div>
        <label className="att__only">
          <Switch checked={absentOnly} onCheckedChange={setAbsentOnly} />
          {t('только с пропусками')}
        </label>
        <span className="cfilters__spacer" />
        <Button
          variant="outline"
          disabled={!data || data.rows.length === 0}
          onClick={() => setExporting(true)}
        >
          {t('Выгрузить')}
        </Button>
      </div>

      {journal.error && <ErrorNote error={journal.error} />}
      {journal.isLoading && !data && <Loading kind="table" />}

      {data && (
        <DataCard
          title={data.group_code || t('Группа')}
          note={`${t('Учебных дней в месяце:')} ${data.school_days}. ${t('День без отметок по группе — выходной.')}`}
          count={data.rows.length}
        >
          {data.rows.length === 0 ? (
            <p className="muted">
              {absentOnly ? t('В этом месяце никто не пропускал') : t('В группе нет учеников')}
            </p>
          ) : (
            <div className="att__scroll" tabIndex={0} role="region" aria-label={t('Журнал посещаемости')}>
              <table className="att__journal">
                <thead>
                  <tr>
                    <th className="att__who">{t('Ученик')}</th>
                    {data.days.map((day) => (
                      <th key={day.date} className={day.school_day ? undefined : 'att__off'}>
                        <span className="num">{day.day}</span>
                        <span className="att__wd">{day.weekday}</span>
                      </th>
                    ))}
                    <th className="att__sum">{t('Итог')}</th>
                  </tr>
                </thead>
                <tbody>
                  {data.rows.map((row) => (
                    <tr key={row.student}>
                      <th scope="row" className="att__who">
                        {row.full_name}
                      </th>
                      {row.cells.map((cell, index) => (
                        <td
                          key={data.days[index].date}
                          className={`att__cell att__cell--${cell}`}
                          title={`${data.days[index].day} ${data.days[index].weekday}: ${data.words[cell]}`}
                        >
                          <span aria-hidden>{CELL_SIGN[cell]}</span>
                          <span className="sr-only">{data.words[cell]}</span>
                        </td>
                      ))}
                      <td className="att__sum num">{row.summary}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <p className="muted att__legend">
            {t('«+» — был, «н» — не был, серая клетка — выходной, «—» — ученика в этот день не отмечали.')}
          </p>
        </DataCard>
      )}

      {exporting && (
        <ExportPreview
          path={exportPath}
          fallback={`poseshchaemost-${month}.xlsx`}
          title={t('Выгрузка журнала посещаемости')}
          onClose={() => setExporting(false)}
        />
      )}
    </>
  )
}
