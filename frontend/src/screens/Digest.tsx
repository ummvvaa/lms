/** Дайджест: сводка словами и то, что ждёт решения.
 *
 * Текст сводки приходит с сервера готовым — здесь он только показывается.
 * Собирать фразы из имён полей на фронте нельзя (фаза 17). У директора —
 * его домен; у администратора — вся школа: за сутки и за неделю по всем
 * доменам, кто, что и у кого, что ждёт решения, учёба и отчёты родителям
 * по статусам (решение владельца, 27.09.2026).
 */
import { useNavigate } from 'react-router'
import { useDigest, type Digest as DigestData } from '../api/hooks'
import DataTable, { type Column } from '../components/DataTable'
import { Row, Rows, StatRow } from '../components/patterns'
import { Chip, DataCard, ErrorNote, Kpi, Loading, ScreenHead } from '../components/ui'
import { t } from '../i18n'
import { formatDateTime } from '../lib/format'
import './academics/academics.css'

type Change = DigestData['recent'][number]

export default function Digest() {
  const navigate = useNavigate()
  const { data, isLoading, error } = useDigest()
  if (isLoading) return <Loading kind="cards" />
  if (error) return <ErrorNote error={error} />
  if (!data) return null

  if (!data.domain) {
    return <ScreenHead title={t('Дайджест')} subtitle={data.headline} />
  }

  const school = data.domain === 'school'
  const columns: Column<Change>[] = [
    // таблица во всю ширину страницы и в ширину карточки: дата — числом,
    // текстовые колонки делят остаток; в левой колонке страницы семь колонок
    // резались многоточием даже на 1440. Домен — подписью под полем, а не
    // колонкой: седьмая колонка на окне 1024 не помещалась
    { key: 'when', title: t('Когда'), width: '160px', cell: (row) => <span className="num">{formatDateTime(row.created_at)}</span>, sortBy: (row) => row.created_at },
    ...(school
      ? [
          { key: 'student', title: t('У кого'), width: 'auto', cell: (row: Change) => row.student_title || <span className="t-note">{t('справочник')}</span> },
        ]
      : []),
    {
      key: 'field',
      title: t('Поле'),
      width: 'auto',
      cell: (row) =>
        school ? (
          <span>
            {row.field_title}
            <br />
            <span className="t-note">{row.domain_title || t('учёба')}</span>
          </span>
        ) : (
          row.field_title
        ),
    },
    {
      key: 'change',
      title: t('Было и стало'),
      // самая длинная клетка — два значения со стрелкой: ей доля больше
      width: '28%',
      cell: (row) => (
        <span className="num">
          <span className="t-note">{row.old_display || t('пусто')}</span> {'→'} <b>{row.new_display || t('пусто')}</b>
        </span>
      ),
    },
    ...(school ? [] : [{ key: 'source', title: t('Источник'), width: 'auto', cell: (row: Change) => <Chip size="sm">{row.source_title}</Chip> }]),
    {
      // кто правил и за какой домен (D6): владелец должен видеть,
      // что значение внёс администратор, а не он сам
      key: 'actor',
      title: t('Кто'),
      width: 'auto',
      cell: (row) => (
        <>
          {row.actor_name}
          {row.acting_for_title && <span className="t-note"> · {row.acting_for_title}</span>}
        </>
      ),
    },
  ]

  const academics = data.academics
  const reports = academics?.reports ?? null

  return (
    <div>
      <ScreenHead title={school ? t('Дайджест по школе') : t('Дайджест на сегодня')} subtitle={data.headline} />
      {school && academics && (
        <StatRow>
          <Kpi label={t('Ждёт решения')} value={data.pending.length || null} none={t('нет')} tone={data.pending.length ? 'warn' : undefined} to="/suggestions" />
          <Kpi label={t('Не отмечено')} value={academics.unmarked || null} none={t('всё отмечено')} tone={academics.unmarked ? 'warn' : undefined} note={academics.unmarked_teachers.slice(0, 3).join(', ') || undefined} to="/teachers" />
          <Kpi label={t('Накладки на неделе')} value={academics.conflicts || null} none={t('нет')} tone={academics.conflicts ? 'bad' : undefined} to="/schedule" />
          <Kpi
            label={t('Отчёты родителям')}
            value={reports ? t('{done} из {total}', { done: Number(reports.sent ?? 0), total: reports.total }) : null}
            none={t('не собирались')}
            note={reports ? t(reports.title) : undefined}
            to="/reports"
          />
        </StatRow>
      )}
      <div className="acad__stack">
        <div className="acad__cols">
          <div className="acad__stack">
            <DataCard title={school ? t('За сутки') : t('Что изменилось со вчера')} empty={data.lines.length === 0 && t('со вчера ничего не менялось')}>
              <Rows>
                {data.lines.map((line, index) => (
                  <Row key={index} icon="news" title={line} />
                ))}
              </Rows>
            </DataCard>
            {school && (
              <DataCard title={t('За неделю')} empty={(data.week_lines ?? []).length === 0 && t('за неделю правок не было')}>
                <Rows>
                  {(data.week_lines ?? []).map((line, index) => (
                    <Row key={index} icon="history" title={line} />
                  ))}
                </Rows>
              </DataCard>
            )}
          </div>
          <div className="acad__stack">
            <DataCard title={school ? t('Ждёт решения') : t('Ждёт вашего решения')} count={data.pending.length || undefined} empty={data.pending.length === 0 && t('ничего не ждёт решения')}>
              {school && (data.pending_lines ?? []).length > 0 && (
                <Rows>
                  {(data.pending_lines ?? []).map((line, index) => (
                    <Row key={`line-${index}`} icon="inbox" tone="warn" title={line} />
                  ))}
                </Rows>
              )}
              <Rows>
                {data.pending.map((row) => (
                  <Row key={row.id} icon="bulb" tone="warn" title={row.title} note={[row.domain_title, row.text].filter(Boolean).join(' · ')} onOpen={() => navigate(`/suggestions/${row.id}`)} openLabel={t('Открыть')} />
                ))}
              </Rows>
            </DataCard>
            {school && reports && (
              <DataCard title={t('Отчёты родителям')} note={t(reports.title)}>
                <Rows>
                  {reports.statuses.map((row) => (
                    <Row key={row.code} title={t(row.title)} value={Number(reports[row.code] ?? 0) || null} none={t('нет')} />
                  ))}
                </Rows>
              </DataCard>
            )}
          </div>
        </div>
        {/* семь колонок во всю ширину страницы, а не в левой колонке */}
        <DataCard title={t('Последние изменения')} count={data.recent.length || undefined} empty={data.recent.length === 0 && t('пока ничего не менялось')}>
          <DataTable columns={columns} rows={data.recent} rowKey={(row) => `${row.created_at}-${row.field_title}-${row.student_title ?? ''}`} limit={20} fit />
        </DataCard>
      </div>
    </div>
  )
}
