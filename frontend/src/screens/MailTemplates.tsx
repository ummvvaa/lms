/**
 * Шаблоны писем: заготовки, из которых собираются письма.
 *
 * Ведёт их администратор: формулировки школы меняются чаще, чем выкаты,
 * и держать их в коде значило бы просить программиста поправить запятую.
 * Директора шаблоны видят, но не правят — иначе на одну и ту же просьбу
 * получилось бы пять разных писем.
 *
 * На каждый вид письма — свой текст на язык группы: семье пишут на её
 * языке. Переменные в тексте по-русски (`{ученик}`, `{группа}`), потому
 * что подставлять их будет человек, а не программист. Строки таблицей,
 * текст правится в правой панели.
 */
import { useEffect, useState } from 'react'
import { toast } from 'sonner'
import { useMailTemplates, useSaveMailTemplate, type MailTemplate } from '../api/hooks'
import DataTable, { type Column } from '../components/DataTable'
import EditDrawer from '../components/EditDrawer'
import Field from '../components/Field'
import { Chip, DataCard, ErrorNote, Loading, ScreenHead } from '../components/ui'
import { Button } from '../components/ui/button'
import { t } from '../i18n'
import { NoteCard } from './academics/shared'
import './academics/academics.css'

/** Правка одного шаблона: тема и текст, «Сохранить», когда что-то изменилось. */
function TemplateEditor({ row, mayEdit, onClose }: { row: MailTemplate; mayEdit: boolean; onClose: () => void }) {
  const save = useSaveMailTemplate()
  const [subject, setSubject] = useState(row.subject)
  const [body, setBody] = useState(row.body)
  useEffect(() => {
    setSubject(row.subject)
    setBody(row.body)
  }, [row])
  const dirty = subject !== row.subject || body !== row.body
  return (
    <div className="acad__form">
      <Field label={t('Тема')} name="subject" value={subject} readOnly={!mayEdit} onChange={setSubject} />
      <Field kind="textarea" label={t('Текст')} name="body" value={body} rows={12} readOnly={!mayEdit} onChange={setBody} />
      <div className="acad__actions">
        {mayEdit && (
          <Button
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
        )}
        <Button variant="outline" onClick={onClose}>
          {t('Закрыть')}
        </Button>
      </div>
    </div>
  )
}

export default function MailTemplates() {
  const templates = useMailTemplates()
  const [openId, setOpenId] = useState<number | null>(null)

  if (templates.isLoading) return <Loading kind="table" />
  if (templates.error) return <ErrorNote error={templates.error} />

  const data = templates.data
  const rows = data?.rows ?? []
  const mayEdit = data?.may_edit ?? false
  const open = rows.find((row) => row.id === openId) ?? null

  const columns: Column<MailTemplate>[] = [
    { key: 'kind', title: t('Вид письма'), width: '28%', cell: (row) => <b>{row.kind_title}</b>, sortBy: (row) => row.kind_title },
    { key: 'lang', title: t('Язык'), width: '14%', cell: (row) => row.language_title, sortBy: (row) => row.language_title },
    { key: 'subject', title: t('Тема'), width: '46%', cell: (row) => row.subject || <span className="t-note">{t('без темы')}</span> },
    {
      key: 'open',
      title: '',
      width: '12%',
      align: 'right',
      cell: (row) => (
        <Button variant="secondary" size="sm" onClick={() => setOpenId(row.id)}>
          {mayEdit ? t('Править') : t('Открыть')}
        </Button>
      ),
    },
  ]

  return (
    <div>
      <ScreenHead
        title={t('Шаблоны писем')}
        subtitle={t('Из них собираются письма родителям и ученикам. Система их не отправляет — открывает почту.')}
      />

      <div className="acad__cols">
        <div className="acad__stack">
          <DataCard
            title={t('Шаблоны')}
            count={rows.length || undefined}
            note={mayEdit ? undefined : t('Шаблоны ведёт администратор')}
            empty={rows.length === 0 && t('шаблоны появятся после первой миграции писем')}
          >
            <DataTable columns={columns} rows={rows} rowKey={(row) => row.id} onRowClick={(row) => setOpenId(row.id)} selected={(row) => row.id === openId} />
          </DataCard>
        </div>
        <div className="acad__stack">
          <DataCard title={t('Переменные')} note={t('Неизвестная переменная останется в тексте как есть — так видно опечатку в шаблоне.')}>
            <div className="acad__chips">
              {(data?.variables ?? []).map((name) => (
                <Chip key={name}>{`{${name}}`}</Chip>
              ))}
            </div>
          </DataCard>
          <NoteCard title={t('Кто правит')}>{t('Тексты ведёт администратор: на одну просьбу — одно письмо. Директора и кураторы берут шаблон в диалоге письма и подставляют переменные руками.')}</NoteCard>
        </div>
      </div>

      <EditDrawer open={open !== null} onClose={() => setOpenId(null)} title={open ? open.kind_title : ''} sub={open ? open.language_title : undefined}>
        {open && <TemplateEditor row={open} mayEdit={mayEdit} onClose={() => setOpenId(null)} />}
      </EditDrawer>
    </div>
  )
}
