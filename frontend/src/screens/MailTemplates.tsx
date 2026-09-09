/**
 * Шаблоны писем (фаза 66): заготовки, из которых собираются письма.
 *
 * Ведёт их администратор: формулировки школы меняются чаще, чем выкаты,
 * и держать их в коде значило бы просить программиста поправить запятую.
 * Директора шаблоны видят, но не правят — иначе на одну и ту же просьбу
 * получилось бы пять разных писем.
 *
 * На каждый вид письма — свой текст на язык группы: семье пишут на её
 * языке. Переменные в тексте по-русски (`{ученик}`, `{группа}`), потому
 * что подставлять их будет человек, а не программист.
 */
import { useState } from 'react'
import { toast } from 'sonner'
import { useMailTemplates, useSaveMailTemplate, type MailTemplate } from '../api/hooks'
import { DataCard, ErrorNote, Loading, ScreenHead } from '../components/ui'
import { Badge } from '../components/ui/badge'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'
import { Textarea } from '../components/ui/textarea'
import { t } from '../i18n'

function TemplateCard({ row, mayEdit }: { row: MailTemplate; mayEdit: boolean }) {
  const save = useSaveMailTemplate()
  const [subject, setSubject] = useState(row.subject)
  const [body, setBody] = useState(row.body)
  const dirty = subject !== row.subject || body !== row.body

  return (
    <DataCard
      title={`${row.kind_title} · ${row.language_title}`}
      note={mayEdit ? undefined : t('Шаблоны ведёт администратор')}
    >
      <label className="letter__field">
        <span className="eyebrow">{t('Тема')}</span>
        <Input
          value={subject}
          disabled={!mayEdit}
          aria-label={`${t('Тема')}: ${row.kind_title} ${row.language_title}`}
          onChange={(event) => setSubject(event.target.value)}
        />
      </label>
      <label className="letter__field">
        <span className="eyebrow">{t('Текст')}</span>
        <Textarea
          rows={8}
          value={body}
          disabled={!mayEdit}
          aria-label={`${t('Текст')}: ${row.kind_title} ${row.language_title}`}
          onChange={(event) => setBody(event.target.value)}
        />
      </label>
      {mayEdit && (
        <div className="ctask__actions">
          <span className="cfilters__spacer" />
          <Button
            size="sm"
            disabled={!dirty || save.isPending}
            onClick={() =>
              save.mutate(
                { id: row.id, subject, body },
                {
                  onSuccess: () => toast.success(t('Шаблон сохранён')),
                  onError: (error) => toast.error(error.message),
                },
              )
            }
          >
            {t('Сохранить')}
          </Button>
        </div>
      )}
    </DataCard>
  )
}

export default function MailTemplates() {
  const templates = useMailTemplates()

  if (templates.isLoading) return <Loading />
  if (templates.error) return <ErrorNote error={templates.error} />

  const data = templates.data
  const rows = data?.rows ?? []

  return (
    <div>
      <ScreenHead
        title={t('Шаблоны писем')}
        subtitle={t(
          'Из них собираются письма родителям и ученикам. Система их не отправляет — открывает почту.',
        )}
      />

      <div className="card card-pad" style={{ marginBottom: 16 }}>
        <span className="eyebrow">{t('Переменные')}</span>
        <div className="toolbar">
          {(data?.variables ?? []).map((name) => (
            <Badge key={name} variant="mute">{`{${name}}`}</Badge>
          ))}
        </div>
        <p className="muted">
          {t('Неизвестная переменная останется в тексте как есть — так видно опечатку в шаблоне.')}
        </p>
      </div>

      <div className="cgrid">
        <div className="cgrid__main">
          {rows.map((row) => (
            <TemplateCard key={row.id} row={row} mayEdit={data?.may_edit ?? false} />
          ))}
        </div>
      </div>
    </div>
  )
}
