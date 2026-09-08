/**
 * Заметки куратора в карточке директора (фаза 62) — только чтение.
 *
 * Показывается Кымбат и Салтанат; кому ещё — решает сервер списком ролей,
 * экран ученика этот блок не подключает никогда.
 */
import { useCuratorNotes } from '../api/hooks'
import { DataCard } from './ui'
import { Badge } from './ui/badge'
import { Row, Rows } from './patterns'
import { t } from '../i18n'

export default function CuratorNotesBlock({ student }: { student: number }) {
  const { list } = useCuratorNotes(student)
  const rows = list.data?.results ?? []
  if (list.error || rows.length === 0) return null

  return (
    <DataCard
      title={t('Заметки куратора')}
      right={<Badge variant="warn">{t('ученик не видит')}</Badge>}
      count={rows.length}
    >
      <Rows>
        {rows.map((note) => (
          <Row
            key={note.id}
            icon="doc"
            title={note.text}
            note={`${note.author_name} · ${new Date(note.created_at).toLocaleString('ru')}`}
          />
        ))}
      </Rows>
    </DataCard>
  )
}
