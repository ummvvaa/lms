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
 *
 * С фазы 32 живёт в выезжающей панели (`Sheet`): предпросмотр файла
 * занимает пол-экрана, и встроенный в поток он сжимал список
 * пользователей под собой. Заголовок теперь у панели, а не здесь.
 */
import { useRef, useState } from 'react'
import {
  useEnrollmentApply,
  useEnrollmentPreview,
  type EnrollmentPreview,
  type EnrollmentRow,
} from '../api/hooks'
import { Chip, ErrorNote, Loading, type Tone } from './ui'
import { t } from '../i18n'
import { Button } from './ui/button'
import DataTable from './DataTable'
import { Input } from './ui/input'

const STATUS: Record<EnrollmentRow['status'], { title: string; tone: Tone }> = {
  new: { title: 'будет заведён', tone: 'good' },
  exists: { title: 'уже есть', tone: 'neutral' },
  error: { title: 'ошибка', tone: 'bad' },
}

type EnrollRow = EnrollmentPreview['rows'][number]

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
    <section className="users__form">
      <p className="muted users__linktext">
        {t(
          'Файл с колонками: ФИО, почта, группа. Остальные колонки система пропустит. Из каждой строки появятся карточка ученика, учётная запись и временный пароль.',
        )}
      </p>

      <Input
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
      <div className="toolbar mb-0">
        <Button variant="outline" size="sm" onClick={() => fileInput.current?.click()}>
          {t('Выбрать файл')}
        </Button>
        {fileName && <span className="muted">{fileName}</span>}
      </div>

      {preview.isPending && <Loading />}
      {preview.isError && <ErrorNote error={preview.error} />}

      {data && (
        <>
          <Chip
            tone={data.missing_columns.length ? 'bad' : 'neutral'}
            className="users__linktext">
            {data.detail}
          </Chip>

          {data.rows.length > 0 && (
            <div className="users__wrap">
              <DataTable
                columns={[
                  { key: 'n', title: t('Строка'), width: '10%', align: 'right', cell: (row: EnrollRow) => <span className="num">{row.number}</span> },
                  { key: 'name', title: t('ФИО'), width: '26%', cell: (row: EnrollRow) => row.full_name || <span className="t-note">{t('нет')}</span> },
                  { key: 'email', title: t('Почта'), width: '26%', cell: (row: EnrollRow) => row.email || <span className="t-note">{t('нет')}</span> },
                  { key: 'group', title: t('Группа'), width: '12%', cell: (row: EnrollRow) => row.group || <span className="t-note">{t('нет')}</span> },
                  {
                    key: 'status',
                    title: t('Что будет'),
                    width: '26%',
                    cell: (row: EnrollRow) => (
                      <>
                        <Chip tone={STATUS[row.status].tone} size="sm">
                          {STATUS[row.status].title}
                        </Chip>
                        {row.reason && <span className="t-note"> {row.reason}</span>}
                      </>
                    ),
                  },
                ]}
                rows={data.rows.slice(0, 50)}
                rowKey={(row) => row.number}
              />
              {data.rows.length > 50 && (
                <p className="muted">
                  {t('и ещё')} {data.rows.length - 50}
                </p>
              )}
            </div>
          )}

          <div className="toolbar mb-0 mt-3">
            <Button
              size="sm"
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
            </Button>
            {apply.isError && <ErrorNote error={apply.error} />}
          </div>
        </>
      )}
    </section>
  )
}
