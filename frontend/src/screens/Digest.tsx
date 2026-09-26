/** Дайджест на сегодня: сводка словами и то, что ждёт решения.
 *
 * Текст сводки приходит с сервера готовым — здесь он только показывается.
 * Собирать фразы из имён полей на фронте нельзя (фаза 17). Лента слева,
 * очередь решений и последние правки — строками и таблицей.
 */
import { useNavigate } from 'react-router-dom'
import { useDigest, type Digest as DigestData } from '../api/hooks'
import DataTable, { type Column } from '../components/DataTable'
import { Row, Rows } from '../components/patterns'
import { Chip, DataCard, ErrorNote, Loading, ScreenHead } from '../components/ui'
import { t } from '../i18n'
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

  const columns: Column<Change>[] = [
    { key: 'when', title: t('Когда'), width: '16%', cell: (row) => <span className="num">{new Date(row.created_at).toLocaleString('ru', { dateStyle: 'short', timeStyle: 'short' })}</span>, sortBy: (row) => row.created_at },
    { key: 'field', title: t('Поле'), width: '22%', cell: (row) => row.field_title },
    {
      key: 'change',
      title: t('Было и стало'),
      width: '30%',
      cell: (row) => (
        <span className="num">
          <span className="t-note">{row.old_display || t('пусто')}</span> {'→'} <b>{row.new_display || t('пусто')}</b>
        </span>
      ),
    },
    { key: 'source', title: t('Источник'), width: '12%', cell: (row) => <Chip size="sm">{row.source_title}</Chip> },
    {
      // кто правил и за какой домен (D6): владелец должен видеть,
      // что значение внёс администратор, а не он сам
      key: 'actor',
      title: t('Кто'),
      width: '20%',
      cell: (row) => (
        <>
          {row.actor_name}
          {row.acting_for_title && <span className="t-note"> · {row.acting_for_title}</span>}
        </>
      ),
    },
  ]

  return (
    <div>
      <ScreenHead title={t('Дайджест на сегодня')} subtitle={data.headline} />
      <div className="acad__cols">
        <div className="acad__stack">
          <DataCard title={t('Что изменилось со вчера')} empty={data.lines.length === 0 && t('со вчера ничего не менялось')}>
            <Rows>
              {data.lines.map((line, index) => (
                <Row key={index} icon="news" title={line} />
              ))}
            </Rows>
          </DataCard>
          <DataCard title={t('Последние изменения')} count={data.recent.length || undefined} empty={data.recent.length === 0 && t('пока ничего не менялось')}>
            <DataTable columns={columns} rows={data.recent} rowKey={(row) => `${row.created_at}-${row.field_title}`} limit={20} />
          </DataCard>
        </div>
        <div className="acad__stack">
          <DataCard title={t('Ждёт вашего решения')} count={data.pending.length || undefined} empty={data.pending.length === 0 && t('ничего не ждёт решения')}>
            <Rows>
              {data.pending.map((row) => (
                <Row key={row.id} icon="bulb" tone="warn" title={row.title} note={row.text} onOpen={() => navigate(`/suggestions/${row.id}`)} openLabel={t('Открыть')} />
              ))}
            </Rows>
          </DataCard>
        </div>
      </div>
    </div>
  )
}
