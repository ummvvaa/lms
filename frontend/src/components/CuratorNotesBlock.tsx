/**
 * Заметки куратора в карточке директора (фаза 62) — только чтение.
 *
 * Показывается Кымбат и Салтанат; кому ещё — решает сервер списком ролей,
 * экран ученика этот блок не подключает никогда.
 */
import { useCuratorNotes } from '../api/hooks'
import { Chip, DataCard } from './ui'
import { Row, Rows } from './patterns'
import { t } from '../i18n'
import { formatDateTime } from '../lib/format'

export default function CuratorNotesBlock({ student }: { student: number }) {
  const { list } = useCuratorNotes(student)
  const rows = list.data?.results ?? []
  if (list.error || rows.length === 0) return null

  return (
    <DataCard
      title={t('Заметки куратора')}
      right={<Chip tone="warn">{t('ученик не видит')}</Chip>}
      count={rows.length}
    >
      <Rows>
        {rows.map((note) => (
          <Row
            key={note.id}
            icon="doc"
            title={note.text}
            note={`${note.author_name} · ${formatDateTime(note.created_at)}`}
          />
        ))}
      </Rows>
    </DataCard>
  )
}
