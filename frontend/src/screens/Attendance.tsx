/**
 * Посещаемость: группа за день (фаза 66).
 *
 * Экран один на двоих — куратор видит свои группы, директор школы все.
 * Разделять было бы двумя экранами, которые расходятся на третий месяц.
 *
 * Лист открывается с отметкой «все присутствуют»: снять три отметки
 * быстрее, чем поставить двадцать, а «никого не отмечали» и «все были» —
 * это разные вещи, и вторая встречается чаще. Что день ещё не сохраняли,
 * видно по подписи.
 *
 * Причина отсутствия — по желанию: заставлять писать «болел» у каждого
 * значит получить двадцать пустых «болел».
 */
import { useEffect, useState } from 'react'
import { toast } from 'sonner'
import { useAttendanceDay, useSaveAttendance, type AttendanceRow } from '../api/hooks'
import { DataCard, ErrorNote, Loading, ScreenHead } from '../components/ui'
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

export default function Attendance() {
  const [group, setGroup] = useState<string>('')
  const [date, setDate] = useState<string>(today())
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

  return (
    <div>
      <ScreenHead
        title={t('Посещаемость')}
        subtitle={t('Отметьте тех, кого не было. Остальные считаются присутствовавшими.')}
      />

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
      </div>

      {sheet.error && <ErrorNote error={sheet.error} />}

      <DataCard
        title={sheet.data?.group_code ?? t('Группа')}
        note={
          sheet.data?.late
            ? t('День старше недели: правка попадёт в журнал отдельной записью')
            : t('Нажмите на строку, чтобы снять отметку')
        }
        count={rows.length}
      >
        {rows.length === 0 && <p className="muted">{t('В группе нет учеников')}</p>}
        <ul className="att__list">
          {rows.map((row) => (
            <li key={row.student} className={`att__row${row.present ? '' : ' att__row--absent'}`}>
              <button
                type="button"
                className="att__mark"
                aria-pressed={!row.present}
                aria-label={`${row.full_name}: ${row.present ? t('был') : t('не был')}`}
                onClick={() => toggle(row.student)}
              >
                {row.present ? t('был') : t('не был')}
              </button>
              <span className="att__name">{row.full_name}</span>
              {!row.present && (
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
