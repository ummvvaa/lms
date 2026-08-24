/**
 * Заведение учеников списком: файл → предпросмотр → создание.
 *
 * Из одной строки появляется всё сразу: карточка ученика, учётная запись
 * и временный пароль. Двойная работа — почта отдельно, ученик отдельно —
 * на двухстах пятидесяти людях превращается в неделю.
 *
 * Ничего не создаётся, пока человек не увидел предпросмотр и не нажал
 * подтверждение: строки с ошибками показываются отдельно, остальные
 * применяются — одна опечатка не отменяет работу за день.
 */
import { useRef, useState } from 'react'
import {
  useEnrollmentApply,
  useEnrollmentPreview,
  type EnrollmentPreview,
  type EnrollmentRow,
} from '../api/hooks'
import { ErrorNote, Loading } from './ui'
import { t } from '../i18n'

const STATUS: Record<EnrollmentRow['status'], { title: string; tone: string }> = {
  new: { title: 'будет заведён', tone: 'chip-ok' },
  exists: { title: 'уже есть', tone: 'chip-mute' },
  error: { title: 'ошибка', tone: 'chip-risk' },
}

export default function EnrollPanel({
  onDone,
  onIssued,
}: {
  onDone: (text: string) => void
  onIssued: (rows: { full_name: string; email: string; password: string }[]) => void
}) {
  const preview = useEnrollmentPreview()
  const apply = useEnrollmentApply()
  const fileInput = useRef<HTMLInputElement>(null)
  const [data, setData] = useState<EnrollmentPreview | null>(null)
  const [fileName, setFileName] = useState('')

  return (
    <section className="card card-pad users__form">
      <span className="eyebrow">{t('Завести учеников списком')}</span>
      <p className="muted users__linktext">
        {t(
          'Файл с колонками: ФИО, почта, класс, группа. Остальные колонки система пропустит. Из каждой строки появятся карточка ученика, учётная запись и временный пароль.',
        )}
      </p>

      <input
        ref={fileInput}
        type="file"
        accept=".csv,.xlsx,.xlsm"
        className="users__file"
        onChange={(event) => {
          const file = event.target.files?.[0]
          event.target.value = ''
          if (!file) return
          setFileName(file.name)
          setData(null)
          preview.mutate(file, { onSuccess: setData })
        }}
      />
      <div className="toolbar" style={{ marginBottom: 0 }}>
        <button className="btn btn-ghost btn-sm" onClick={() => fileInput.current?.click()}>
          {t('Выбрать файл')}
        </button>
        {fileName && <span className="muted">{fileName}</span>}
      </div>

      {preview.isPending && <Loading />}
      {preview.isError && <ErrorNote error={preview.error} />}

      {data && (
        <>
          <p className={`chip ${data.missing_columns.length ? 'chip-risk' : 'chip-mute'} users__linktext`}>
            {data.detail}
          </p>

          {data.rows.length > 0 && (
            <div className="users__wrap">
              <table className="history users__table">
                <thead>
                  <tr>
                    <th>{t('Строка')}</th>
                    <th>{t('ФИО')}</th>
                    <th>{t('Почта')}</th>
                    <th>{t('Класс')}</th>
                    <th>{t('Группа')}</th>
                    <th>{t('Что будет')}</th>
                  </tr>
                </thead>
                <tbody>
                  {data.rows.slice(0, 50).map((row) => (
                    <tr key={row.number} className={row.status === 'error' ? 'users__off' : undefined}>
                      <td className="num">{row.number}</td>
                      <td>{row.full_name || '—'}</td>
                      <td>{row.email || '—'}</td>
                      <td className="num">{row.grade || '—'}</td>
                      <td>{row.group || '—'}</td>
                      <td>
                        <span className={`chip ${STATUS[row.status].tone}`}>{STATUS[row.status].title}</span>
                        {row.reason && <span className="muted"> {row.reason}</span>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {data.rows.length > 50 && (
                <p className="muted">
                  {t('и ещё')} {data.rows.length - 50}
                </p>
              )}
            </div>
          )}

          <div className="toolbar" style={{ marginBottom: 0, marginTop: 12 }}>
            <button
              className="btn btn-primary btn-sm"
              disabled={data.will_create === 0 || apply.isPending}
              onClick={() =>
                apply.mutate(
                  data.rows.filter((row) => row.status === 'new'),
                  {
                    onSuccess: (result) => {
                      onDone(result.detail)
                      onIssued(result.rows)
                      setData(null)
                      setFileName('')
                    },
                  },
                )
              }
            >
              {t('Завести')} {data.will_create}
            </button>
            {apply.isError && <ErrorNote error={apply.error} />}
          </div>
        </>
      )}
    </section>
  )
}
