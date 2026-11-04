/**
 * Скачать разборы в Word: язык файла и что скачать, затем — файл сразу или
 * подготовка в фоне. Один ученик на языке разбора — файл сразу; нужен перевод
 * или общая картина по тестам — «Готовим файлы… 7 из 25» с отменой, окно можно
 * закрыть, про готовность скажет колокольчик. Ссылка из колокольчика открывает
 * это же окно на готовой выгрузке (`exportId`).
 */
import { useEffect, useState } from 'react'
import { toast } from 'sonner'
import { fetchFile, saveBlob } from '../../api/client'
import { useCareerExport, useCareerStartExport, type ExportLanguage } from '../../api/career'
import Modal from '../../components/Modal'
import RunState from '../../components/RunState'
import { Row, Rows, Segmented } from '../../components/patterns'
import { Button } from '../../components/ui/button'
import { useAuth } from '../../auth/AuthContext'
import { languagesOf } from '../../components/ProfileMenu'
import { language as uiLanguage, t } from '../../i18n'
import { formatDate } from '../../lib/format'

export type ExportScope = { value: string; label: string; request: { group?: number; students?: number[] } }

const isLanguage = (value: string | undefined): value is ExportLanguage => value === 'ru' || value === 'kk' || value === 'en'

async function save(path: string, fallback: string) {
  const file = await fetchFile(path, fallback)
  saveBlob(file.blob, file.name)
}

export default function ExportDialog({
  note,
  scopes = [],
  sourceLanguage,
  exportId = null,
  onClose,
}: {
  note: string
  scopes?: ExportScope[]
  /** язык разбора: выбран другой — окно говорит, что перевод сделается перед скачиванием */
  sourceLanguage?: string
  /** открыть готовящуюся или готовую выгрузку — из колокольчика */
  exportId?: number | null
  onClose: () => void
}) {
  const start = useCareerStartExport()
  // подписи языков — с сервера, каждая на своём языке, как в меню профиля
  const { me } = useAuth()
  const languages = languagesOf(me)
  const [lang, setLang] = useState<ExportLanguage>(isLanguage(sourceLanguage) ? sourceLanguage : isLanguage(uiLanguage()) ? (uiLanguage() as ExportLanguage) : 'ru')
  const [scope, setScope] = useState(scopes[0]?.value ?? '')
  const [job, setJob] = useState<number | null>(exportId)
  const state = useCareerExport(job)
  const data = state.data
  // готово, пока окно открыто, — файл скачивается сам один раз; из колокольчика — кнопкой
  const [watching, setWatching] = useState(false)
  const [saved, setSaved] = useState(false)
  const fileUrl = job ? `/career/exports/${job}/file/` : ''
  useEffect(() => {
    if (!watching || saved || data?.status !== 'done' || !data.has_file) return
    setSaved(true)
    save(fileUrl, data.file_name || t('профтест.zip'))
      .then(() => toast.success(t('Файл скачан')))
      .catch((error: Error) => toast.error(error.message))
  }, [watching, saved, data, fileUrl])

  const picked = scopes.find((item) => item.value === scope) ?? scopes[0]
  const run = () => {
    if (!picked) return
    start.mutate(
      { language: lang, ...picked.request },
      {
        onSuccess: (result) => {
          if (result.ready) {
            save(result.url, t('профтест.docx'))
              .then(() => {
                toast.success(t('Файл скачан'))
                onClose()
              })
              .catch((error: Error) => toast.error(error.message))
            return
          }
          if (result.already) toast.message(t('Такие файлы уже готовятся — показываю идущую подготовку'))
          setWatching(true)
          setJob(result.export.id)
        },
        onError: (error) => toast.error(error.message),
      },
    )
  }

  return (
    <Modal title={t('Скачать Word')} note={note} onClose={onClose}>
      {job === null ? (
        <>
          <div className="cexport__pick">
            <span className="eyebrow">{t('Язык файла')}</span>
            <Segmented<ExportLanguage> usageFilter={false} value={lang} onChange={setLang} label={t('Язык файла')} items={languages} />
          </div>
          {scopes.length > 1 && (
            <div className="cexport__pick">
              <span className="eyebrow">{t('Что скачать')}</span>
              <Segmented<string> usageFilter={false} value={scope} onChange={setScope} label={t('Что скачать')} items={scopes.map(({ value, label }) => ({ value, label }))} />
            </div>
          )}
          <p className="t-note">
            {sourceLanguage && sourceLanguage !== lang
              ? t('Разбор написан на другом языке: перевод сделается перед скачиванием и сохранится для следующих раз')
              : sourceLanguage
                ? t('В файл идут все готовые разборы ученика — версия профориентолога с правками')
                : t('В файл ученика идут все его готовые разборы с правками профориентолога; разборы на другом языке переводятся перед скачиванием')}
          </p>
          <div className="toolbar ctest__foot">
            <Button disabled={start.isPending || !picked} onClick={run}>
              {start.isPending ? t('Запускаю…') : t('Скачать')}
            </Button>
            <Button variant="outline" onClick={onClose}>
              {t('Отмена')}
            </Button>
          </div>
        </>
      ) : (
        <ExportState
          loading={state.isLoading}
          error={state.error}
          data={data}
          onSave={() => data && save(fileUrl, data.file_name || t('профтест.zip')).catch((error: Error) => toast.error(error.message))}
          onRefetch={() => void state.refetch()}
          onClose={onClose}
        />
      )}
    </Modal>
  )
}

function ExportState({
  loading,
  error,
  data,
  onSave,
  onRefetch,
  onClose,
}: {
  loading: boolean
  error: Error | null
  data: ReturnType<typeof useCareerExport>['data']
  onSave: () => void
  onRefetch: () => void
  onClose: () => void
}) {
  if (loading) return <p className="t-note">{t('Загрузка…')}</p>
  if (error || !data) return <p className="acad__note">{error?.message ?? t('Такой выгрузки нет')}</p>
  const lines = data.outcome.split('\n').filter(Boolean)
  return (
    <>
      {data.status === 'running' && (
        <>
          <RunState run={data.run} running={t('Готовим файлы… {done} из {total}', { done: data.done, total: data.total })} onChanged={onRefetch} />
          <p className="t-note">{t('Окно можно закрыть: подготовка продолжится, про готовность скажет колокольчик')}</p>
        </>
      )}
      {data.status !== 'running' && (
        <Rows>
          <Row
            icon={data.status === 'done' ? 'download' : 'alert'}
            tone={data.status === 'done' ? 'good' : data.status === 'failed' ? 'bad' : 'neutral'}
            title={data.status === 'done' ? data.file_name : data.status === 'expired' ? t('Файл удалён: срок хранения истёк — подготовьте заново') : data.status_title}
            note={data.status === 'done' && data.expires_at ? t('Хранится до {date}', { date: formatDate(data.expires_at) }) : (data.run?.error ?? undefined)}
          />
        </Rows>
      )}
      {lines.length > 0 && (
        <div className="cexport__outcome">
          {lines.map((line) => (
            <p key={line} className="t-note">
              {line}
            </p>
          ))}
        </div>
      )}
      <div className="toolbar ctest__foot">
        {data.has_file && <Button onClick={onSave}>{t('Скачать')}</Button>}
        <Button variant="outline" onClick={onClose}>
          {t('Закрыть')}
        </Button>
      </div>
    </>
  )
}
