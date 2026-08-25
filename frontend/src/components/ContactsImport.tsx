/**
 * Загрузка контактов родителей файлом.
 *
 * Правила те же, что у остальных загрузок: сначала предпросмотр —
 * сколько заведётся, что уже есть, где ошибка построчно, — и только
 * потом применение. Отменяется загрузка целиком из истории загрузок.
 */
import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'
import { DataCard, ErrorNote } from './ui'
import { t } from '../i18n'

interface ContactRow {
  number: number
  student: number | null
  student_email: string
  student_name: string
  full_name: string
  relation: string
  phone: string
  email: string
  preferred_channel: string
  note: string
  is_primary: boolean
  status: 'new' | 'exists' | 'error'
  reason: string
}

interface ContactsPreview {
  columns: Record<string, string>
  missing_columns: string[]
  total: number
  will_create: number
  already_exist: number
  with_errors: number
  rows: ContactRow[]
  detail: string
}

export default function ContactsImport() {
  const queryClient = useQueryClient()
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<ContactsPreview | null>(null)
  const [applied, setApplied] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function upload(selected: File) {
    setBusy(true)
    setError(null)
    setApplied(null)
    setPreview(null)
    try {
      const body = new FormData()
      body.append('file', selected)
      setPreview(await api<ContactsPreview>('/contacts/import/preview/', { method: 'POST', body }))
      setFile(selected)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось прочитать файл')
    } finally {
      setBusy(false)
    }
  }

  async function apply() {
    if (!preview) return
    setBusy(true)
    try {
      const result = await api<{ detail: string }>('/contacts/import/apply/', {
        method: 'POST',
        body: JSON.stringify({
          rows: preview.rows.filter((row) => row.status === 'new'),
          file_name: file?.name ?? '',
        }),
      })
      setApplied(result.detail)
      setPreview(null)
      void queryClient.invalidateQueries({ queryKey: ['contacts'] })
      void queryClient.invalidateQueries({ queryKey: ['imports'] })
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось завести контакты')
    } finally {
      setBusy(false)
    }
  }

  const broken = preview?.rows.filter((row) => row.status === 'error') ?? []

  return (
    <>
      <DataCard
        title={t('Файл со списком контактов')}
        note={t('XLSX или CSV, ученик ищется по почте')}
        hint={t(
          'Колонки распознаются по заголовку первой строки: почта ученика, ФИО родителя, кем приходится, телефон, почта, способ связи, примечание, основной. Обязательны первые две.',
        )}
      >
        <label className="filepick">
          <input
            type="file"
            accept=".csv,.xlsx,.xlsm"
            onChange={(event) => {
              const selected = event.target.files?.[0]
              if (selected) void upload(selected)
            }}
          />
          <span className="btn btn-primary btn-sm">{t('Выбрать файл')}</span>
          <span className="muted filepick__name">{file ? file.name : t('Файл не выбран')}</span>
        </label>
        {busy && <p className="muted">{t('Обрабатываю…')}</p>}
        {error && <ErrorNote error={new Error(error)} />}
        {applied && <p className="chip chip-ok">{applied}</p>}
      </DataCard>

      {preview && (
        <DataCard title={t('Что будет загружено')} note={preview.detail}>
          <div className="toolbar">
            <span className="chip chip-ok num">Заведётся: {preview.will_create}</span>
            {preview.already_exist > 0 && (
              <span className="chip chip-mute num">Уже есть: {preview.already_exist}</span>
            )}
            {preview.with_errors > 0 && (
              <span className="chip chip-warn num">С ошибками: {preview.with_errors}</span>
            )}
            <span className="toolbar__spacer" />
            <button
              className="btn btn-primary btn-sm"
              disabled={busy || preview.will_create === 0}
              onClick={() => void apply()}
            >
              {t('Завести контакты')}
            </button>
          </div>

          {preview.missing_columns.length > 0 && <p className="chip chip-warn">{preview.detail}</p>}

          {broken.length > 0 && (
            <div className="imp__problems">
              <span className="datacard__title">{t('Что поправить в файле')}</span>
              <ul className="imp__problemlist">
                {broken.slice(0, 20).map((row) => (
                  <li key={row.number}>
                    <b>Строка {row.number}</b>: {row.reason}
                  </li>
                ))}
              </ul>
            </div>
          )}

          <table className="history">
            <tbody>
              {preview.rows.slice(0, 20).map((row) => (
                <tr key={row.number}>
                  <td className="muted">стр. {row.number}</td>
                  <td style={{ fontWeight: 650 }}>{row.full_name || '—'}</td>
                  <td className="muted">{row.student_name || row.student_email}</td>
                  <td className="num">{row.phone || row.email || '—'}</td>
                  <td>
                    <span
                      className={`chip ${
                        row.status === 'new' ? 'chip-ok' : row.status === 'exists' ? 'chip-mute' : 'chip-warn'
                      }`}
                    >
                      {row.status === 'new' ? 'заведётся' : row.status === 'exists' ? 'уже есть' : 'ошибка'}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {preview.total > 20 && (
            <p className="muted rows__empty">
              Показаны первые 20 из {preview.total} строк — применятся все подходящие.
            </p>
          )}
        </DataCard>
      )}
    </>
  )
}
