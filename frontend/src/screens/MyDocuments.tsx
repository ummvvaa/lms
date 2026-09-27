/**
 * «Мои документы» ученика — одна карточка вместо трёх.
 *
 * Раньше на вкладке стояли «Готовность документов», «Загрузить документ»
 * и «Мои документы»: чек-лист слева и список справа показывали одно и то же
 * дважды, а у строки списка «Ждёт проверки», «Открыть» и «Убрать» ложились
 * друг под друга — при десяти документах карточка переставала читаться.
 *
 * Теперь список один — по типам документа. У строки: состояние (не загружен,
 * ждёт проверки, подтверждён, отклонён с причиной, истекает), дата и справа
 * в одну линию действия значками — «Открыть», «Убрать», как в блоке
 * «Поступление». Документа нет — в строке кнопка «Загрузить»: форма открывается
 * с уже выбранным типом. Несколько файлов одного типа (перезагрузка после
 * отклонения) раскрываются под строкой историей. На телефоне строка та же,
 * действия — словами под названием.
 *
 * Имени проверяющего ученик не видит: сервер его сюда не отдаёт (фаза 62).
 */
import { useState } from 'react'
import { toast } from 'sonner'
import { ChevronDownIcon, ChevronUpIcon, ExternalLinkIcon, Trash2Icon } from 'lucide-react'
import { useDocuments, usePortfolio, type StudentDocumentRow } from '../api/hooks'
import Modal from '../components/Modal'
import { Chip, DataCard, ErrorNote, Loading, type Tone } from '../components/ui'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'
import { Tooltip, TooltipContent, TooltipTrigger } from '../components/ui/tooltip'
import { usePhone } from '../phone'
import { t } from '../i18n'

type State = 'none' | 'pending' | 'confirmed' | 'rejected' | 'expiring' | 'superseded'

const STATE_TONE: Record<State, Tone> = {
  none: 'neutral',
  pending: 'warn',
  confirmed: 'good',
  rejected: 'bad',
  expiring: 'warn',
  superseded: 'neutral',
}

const STATE_TITLE: Record<State, string> = {
  none: 'Не загружен',
  pending: 'Ждёт проверки',
  confirmed: 'Подтверждён',
  rejected: 'Отклонён',
  expiring: 'Истекает',
  superseded: 'Заменён',
}

/** Типы, у которых спрашивается срок действия (фаза 62). */
const NEEDS_EXPIRY = ['passport', 'exam_certificate']

const dateOf = (value: string) => new Date(value).toLocaleDateString('ru')

/** Состояние файла: у подтверждённого с близким сроком сервер отдаёт «истекает». */
const stateOf = (row: StudentDocumentRow): State =>
  (row.status as string) === 'superseded' ? 'superseded' : row.state

/** Действие строки: на ноутбуке — значок с подсказкой, на телефоне — слово. */
function Action({
  phone,
  icon,
  label,
  disabled,
  onClick,
}: {
  phone: boolean
  icon: React.ReactNode
  label: string
  disabled?: boolean
  onClick: () => void
}) {
  if (phone)
    return (
      <Button size="sm" variant="ghost" disabled={disabled} onClick={onClick}>
        {t(label)}
      </Button>
    )
  return (
    <Tooltip>
      <TooltipTrigger
        render={<Button variant="ghost" size="icon" className="mydocs__ibtn" disabled={disabled} />}
        aria-label={t(label)}
        onClick={onClick}
      >
        {icon}
      </TooltipTrigger>
      <TooltipContent>{t(label)}</TooltipContent>
    </Tooltip>
  )
}

/** Форма загрузки: тип уже выбран строкой, из которой её открыли. */
function UploadForm({ docType, title, onClose }: { docType: string; title: string; onClose: () => void }) {
  const { uploadDocument } = useDocuments()
  const [file, setFile] = useState<File | null>(null)
  const [expires, setExpires] = useState('')
  const [note, setNote] = useState('')
  const needsExpiry = NEEDS_EXPIRY.includes(docType)

  return (
    <Modal
      title={`${t('Загрузить документ')}: ${title}`}
      note={t('PDF, JPG или PNG — файл виден вам и школе')}
      onClose={onClose}
    >
      <div className="propose__form">
        <div className="field">
          <label className="field__label t-caps" htmlFor="document-file">
            {t('Файл')}
          </label>
          <div className="field__control">
            <Input id="document-file" type="file" accept=".pdf,.jpg,.jpeg,.png" aria-label={t('Файл документа')} onChange={(event) => setFile(event.target.files?.[0] ?? null)} />
          </div>
        </div>
        {needsExpiry && (
          <label className="propose__field">
            <span className="muted propose__label">{t('Действует до')}</span>
            <Input type="date" value={expires} onChange={(event) => setExpires(event.target.value)} />
          </label>
        )}
        <label className="propose__field">
          <span className="muted propose__label">{t('Примечание')}</span>
          <Input value={note} onChange={(event) => setNote(event.target.value)} />
        </label>
        <div className="propose__actions">
          <Button variant="outline" size="sm" onClick={onClose}>
            {t('Отмена')}
          </Button>
          <Button
            size="sm"
            disabled={uploadDocument.isPending || file === null}
            onClick={() => {
              if (!file) return
              uploadDocument.mutate(
                { file, doc_type: docType, note, expires_at: needsExpiry && expires ? expires : undefined },
                {
                  onSuccess: () => {
                    toast.success(t('Документ загружен'))
                    onClose()
                  },
                  onError: (error) => toast.error(error.message),
                },
              )
            }}
          >
            {t('Загрузить')}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

export default function MyDocuments() {
  const phone = usePhone()
  const { query, removeDocument } = useDocuments()
  const portfolio = usePortfolio()
  const [uploading, setUploading] = useState<{ code: string; title: string } | null>(null)
  const [opened, setOpened] = useState<ReadonlySet<string>>(new Set())

  if (query.isLoading || portfolio.isLoading) return <Loading />
  if (query.error) return <ErrorNote error={query.error} />

  const files = [...(query.data?.results ?? [])].sort((a, b) => b.created_at.localeCompare(a.created_at))
  const checklist = portfolio.data?.documents ?? []
  // строки карточки: типы чек-листа и «Прочее», если такие файлы есть
  const types = [
    ...checklist.map((row) => ({ code: row.code, title: row.title, reason: row.reject_reason })),
    ...(files.some((file) => file.doc_type === 'other')
      ? [{ code: 'other', title: 'Прочее', reason: '' }]
      : []),
  ]
  const collected = checklist.filter((row) => row.done).length

  const remove = (id: number) =>
    removeDocument.mutate(id, {
      onSuccess: () => toast.success(t('Документ в архиве')),
      onError: (error) => toast.error(error.message),
    })

  const actionsOf = (file: StudentDocumentRow) => (
    <>
      <Action
        phone={phone}
        icon={<ExternalLinkIcon />}
        label="Открыть"
        onClick={() => window.open(`/api/documents/${file.id}/file/`)}
      />
      <Action
        phone={phone}
        icon={<Trash2Icon />}
        label="Убрать"
        disabled={removeDocument.isPending}
        onClick={() => remove(file.id)}
      />
    </>
  )

  return (
    <>
      <DataCard
        title={t('Мои документы')}
        note={t('По типам: что загружено, что проверено и чего не хватает')}
        right={
          <Chip tone="good" className="num">
            {`${collected} ${t('из')} ${checklist.length}`}
          </Chip>
        }
      >
        <ul className="mydocs">
          {types.map((type) => {
            const own = files.filter((file) => file.doc_type === type.code)
            const current = own[0]
            const history = own.slice(1)
            // у «Прочего» своего статуса нет: файл проверяется вместе с достижением
            const state: State = current ? (type.code === 'other' ? 'confirmed' : stateOf(current)) : 'none'
            const isOpen = opened.has(type.code)
            // отклонённый и заменённый документ загружают заново — кнопка в той же строке
            const wantsUpload =
              !current || state === 'rejected' || state === 'superseded' || type.code === 'other'

            return (
              <li key={type.code} className="mydocs__item">
                <div className="mydocs__row">
                  <div className="mydocs__what">
                    <span className="mydocs__title">{t(type.title)}</span>
                    <span className="mydocs__meta">
                      {type.code !== 'other' && (
                        <Chip tone={STATE_TONE[state]}>{t(STATE_TITLE[state])}</Chip>
                      )}
                      {/* значение внесли за ученика — он должен это видеть; имени куратора нет */}
                      {current?.entered_by_curator && <Chip tone="neutral">{t('внёс куратор')}</Chip>}
                      {current && <span className="muted num">{dateOf(current.created_at)}</span>}
                      {current?.expires_at && (
                        <span className="muted num">
                          {t('до')} {dateOf(current.expires_at)}
                        </span>
                      )}
                    </span>
                    {state === 'rejected' && current?.reject_reason && (
                      <span className="mydocs__reason">
                        {t('Причина:')} {current.reject_reason}
                      </span>
                    )}
                  </div>
                  <div className="mydocs__acts">
                    {wantsUpload && (
                      <Button
                        size="sm"
                        variant={current ? 'outline' : 'default'}
                        onClick={() => setUploading({ code: type.code, title: t(type.title) })}
                      >
                        {current && type.code !== 'other' ? t('Загрузить заново') : t('Загрузить')}
                      </Button>
                    )}
                    {current && actionsOf(current)}
                  </div>
                </div>

                {history.length > 0 && (
                  <>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="mydocs__more"
                      aria-expanded={isOpen}
                      onClick={() => {
                        const next = new Set(opened)
                        if (isOpen) next.delete(type.code)
                        else next.add(type.code)
                        setOpened(next)
                      }}
                    >
                      {isOpen ? <ChevronUpIcon /> : <ChevronDownIcon />}
                      {t('Прежние файлы:')} {history.length}
                    </Button>
                    {isOpen && (
                      <ul className="mydocs__history">
                        {history.map((file) => (
                          <li key={file.id} className="mydocs__row mydocs__row--old">
                            <div className="mydocs__what">
                              <span className="mydocs__meta">
                                {type.code !== 'other' && (
                                  <Chip tone={STATE_TONE[stateOf(file)]}>
                                    {t(STATE_TITLE[stateOf(file)])}
                                  </Chip>
                                )}
                                <span className="muted num">{dateOf(file.created_at)}</span>
                                {file.title && <span className="muted">{file.title}</span>}
                              </span>
                              {file.reject_reason && (
                                <span className="mydocs__reason">
                                  {t('Причина:')} {file.reject_reason}
                                </span>
                              )}
                            </div>
                            <div className="mydocs__acts">{actionsOf(file)}</div>
                          </li>
                        ))}
                      </ul>
                    )}
                  </>
                )}
              </li>
            )
          })}
        </ul>
        {/* файл вне чек-листа — грамота, справка: загружается тем же окном */}
        {!types.some((type) => type.code === 'other') && (
          <Button
            variant="ghost"
            size="sm"
            className="mydocs__other"
            onClick={() => setUploading({ code: 'other', title: t('Прочее') })}
          >
            {t('Загрузить другой документ')}
          </Button>
        )}
      </DataCard>

      {uploading && (
        <UploadForm docType={uploading.code} title={uploading.title} onClose={() => setUploading(null)} />
      )}
    </>
  )
}
