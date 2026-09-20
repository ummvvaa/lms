/**
 * Предпросмотр выгрузки: сначала таблица на экране, потом «Скачать xlsx».
 *
 * Один компонент на все выгрузки — ученики, документы, журнал, пробник,
 * отчёт импорта, выданные пароли, журнал посещаемости, пользователи. Файл
 * раньше скачивался сразу, и что в нём, человек узнавал уже в Excel: не та
 * группа, не тот фильтр — и второй файл в «Загрузках».
 *
 * Данные приходят с той же ручки, что и файл (`?preview=1`): сервер собирает
 * их из тех же колонок и строк (`core/exports.py`), поэтому разойтись с файлом
 * им не с чем. В кэш запросов предпросмотр не кладётся — в выдаче паролей
 * в нём лежат пароли, и жить дольше окна им незачем.
 */
import { useEffect, useState } from 'react'
import { toast } from 'sonner'
import { DownloadIcon } from 'lucide-react'
import { downloadFile, get, post } from '../api/client'
import Modal from './Modal'
import { ErrorNote, Loading, ScreenTabs } from './ui'
import { Button } from './ui/button'
import { t } from '../i18n'

interface PreviewSheet {
  title: string
  columns: string[]
  rows: string[][]
  total: number
}

interface PreviewPayload {
  filename: string
  sheets: PreviewSheet[]
  preview_rows: number
}

const withPreview = (path: string) => `${path}${path.includes('?') ? '&' : '?'}preview=1`

export function ExportPreview({
  path,
  fallback,
  title,
  body,
  onClose,
}: {
  /** ручка выгрузки — та же, что отдаёт файл */
  path: string
  /** имя файла, если сервер его не назвал */
  fallback: string
  title: string
  /** тело запроса, когда выгрузка собирается по данным экрана (выдача паролей) */
  body?: Record<string, unknown>
  onClose: () => void
}) {
  const [data, setData] = useState<PreviewPayload | null>(null)
  const [error, setError] = useState<Error | null>(null)
  const [sheet, setSheet] = useState('0')
  const [saving, setSaving] = useState(false)
  // тело сравниваем по содержимому: объект у вызывающего пересоздаётся на каждой отрисовке
  const bodyText = body ? JSON.stringify(body) : ''

  useEffect(() => {
    let alive = true
    const request = bodyText
      ? post<PreviewPayload>(path, { ...(JSON.parse(bodyText) as Record<string, unknown>), preview: true })
      : get<PreviewPayload>(withPreview(path))
    request
      .then((payload) => alive && setData(payload))
      .catch(
        (reason: unknown) => alive && setError(reason instanceof Error ? reason : new Error(String(reason))),
      )
    return () => {
      alive = false
    }
  }, [path, bodyText])

  const page = data?.sheets[Number(sheet)] ?? data?.sheets[0]

  return (
    <Modal title={title} note={data?.filename} onClose={onClose} full>
      {error && <ErrorNote error={error} />}
      {!data && !error && <Loading kind="table" />}
      {data && (
        <div className="xprev">
          <div className="xprev__bar">
            {data.sheets.length > 1 ? (
              <ScreenTabs
                value={sheet}
                onChange={setSheet}
                items={data.sheets.map((item, index) => ({ value: String(index), label: item.title }))}
              />
            ) : (
              <span />
            )}
            <Button
              size="sm"
              disabled={saving}
              onClick={() => {
                setSaving(true)
                downloadFile(path, fallback, bodyText ? { method: 'POST', body: bodyText } : undefined)
                  .then(() => toast.success(t('Файл скачан')))
                  .catch(() => toast.error(t('Не удалось скачать файл')))
                  .finally(() => setSaving(false))
              }}
            >
              <DownloadIcon />
              {t('Скачать xlsx')}
            </Button>
          </div>

          {!page || page.rows.length === 0 ? (
            <p className="muted xprev__empty">{t('В выгрузке нет строк — файл будет пустым.')}</p>
          ) : (
            <>
              <div className="xprev__scroll" tabIndex={0} role="region" aria-label={t('Таблица выгрузки')}>
                <table className="tbl xprev__table">
                  <thead>
                    <tr>
                      {page.columns.map((column, index) => (
                        <th key={`${column}-${index}`}>{column}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {page.rows.map((row, number) => (
                      <tr key={number}>
                        {row.map((cell, index) => (
                          <td key={index}>{cell === '' ? <span className="muted">{'—'}</span> : cell}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="muted xprev__note">
                {page.total > page.rows.length
                  ? `${t('Показаны первые строки:')} ${page.rows.length} ${t('из')} ${page.total}. ${t('В файле — все.')}`
                  : `${t('Строк в файле:')} ${page.total}`}
              </p>
            </>
          )}
        </div>
      )}
    </Modal>
  )
}

/**
 * Кнопка выгрузки с предпросмотром: нажали — увидели таблицу — скачали.
 * Экрану достаточно поставить её вместо прежней кнопки «Выгрузить».
 */
export default function ExportButton({
  path,
  fallback,
  title,
  label = 'Выгрузить',
  body,
  variant = 'outline',
  disabled,
}: {
  path: string
  fallback: string
  title: string
  label?: string
  body?: Record<string, unknown>
  variant?: 'outline' | 'ghost' | 'default'
  disabled?: boolean
}) {
  const [open, setOpen] = useState(false)
  return (
    <>
      <Button size="sm" variant={variant} disabled={disabled} onClick={() => setOpen(true)}>
        {t(label)}
      </Button>
      {open && (
        <ExportPreview
          path={path}
          fallback={fallback}
          title={t(title)}
          body={body}
          onClose={() => setOpen(false)}
        />
      )}
    </>
  )
}
