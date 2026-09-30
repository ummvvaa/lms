/**
 * Уровень английского ученика (A1–C2) — для отчёта родителям (30.09.2026).
 * Вносят учитель GE/EEP своего состава, Кымбат, куратор группы
 * и администратор; из балла IELTS уровень не выводится. Ученику не показывается.
 */
import { useState } from 'react'
import { toast } from 'sonner'
import { useSetEnglishLevel, type EnglishLevelInfo } from '../../api/academics'
import Field from '../../components/Field'
import { Row, Rows } from '../../components/patterns'
import { DataCard } from '../../components/ui'
import { Button } from '../../components/ui/button'
import { t } from '../../i18n'
import { todayAlmaty } from '../../lib/dates'
import { dateWords } from './shared'

export default function EnglishLevel({ student, info }: { student: number; info: EnglishLevelInfo }) {
  const save = useSetEnglishLevel()
  const [level, setLevel] = useState(info.level || info.levels[2] || 'B1')
  const [since, setSince] = useState(todayAlmaty())
  return (
    <DataCard title={t('Уровень английского')}>
      <Rows>
        <Row
          title={info.level || t('не внесён')}
          note={info.since ? [t('с {date}', { date: dateWords(info.since) }), ...(info.history[0]?.by ? [info.history[0].by] : [])].join(' · ') : t('вносят учитель GE/EEP, академический директор или куратор')}
        />
        {info.history.slice(1, 4).map((row) => (
          <Row key={`${row.level}-${row.since}`} title={row.level} note={[t('с {date}', { date: dateWords(row.since) }), ...(row.by ? [row.by] : [])].join(' · ')} />
        ))}
      </Rows>
      {info.may_edit && (
        <div className="acad__form">
          <div className="acad__pair">
            <Field kind="select" name="english-level" label={t('Уровень')} value={level} onChange={setLevel} options={info.levels.map((code) => ({ value: code, title: code }))} />
            <Field kind="date" name="english-since" label={t('С даты')} value={since} max={todayAlmaty()} onChange={setSince} />
          </div>
          <div className="acad__actions">
            <Button
              size="sm"
              disabled={save.isPending}
              onClick={() => save.mutate({ student, level, since }, { onSuccess: () => toast.success(t('Уровень сохранён')), onError: (e) => toast.error(e.message) })}
            >
              {t('Сохранить уровень')}
            </Button>
          </div>
        </div>
      )}
    </DataCard>
  )
}
