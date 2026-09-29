/**
 * Импорт расписания и сотрудников из книги школы: файл → предпросмотр → «Применить».
 *
 * Только у администратора: импорт заводит учётки сотрудников. Предпросмотр
 * ничего не пишет — сервер проходит файл в транзакции и откатывает её,
 * поэтому цифры здесь те же, что сделает «Применить». Применяется ровно тот
 * файл, что был в предпросмотре (отпечаток), всё одной транзакцией.
 *
 * Пароли новых учёток приходят один раз в ответе «Применить»: они на экране
 * и скачиваются списком один раз. В базе только их отпечатки.
 */
import { useRef, useState, type ReactNode } from 'react'
import { toast } from 'sonner'
import {
  useScheduleImportApply,
  useScheduleImportPreview,
  type ScheduleImportCredential,
  type ScheduleImportReport,
} from '../../api/academics'
import { download } from '../../api/client'
import DataTable from '../../components/DataTable'
import { Row, Rows, ShowAll } from '../../components/patterns'
import { Chip, ErrorNote, Loading } from '../../components/ui'
import { Button } from '../../components/ui/button'
import { Input } from '../../components/ui/input'
import { t } from '../../i18n'
import { dateWords } from './shared'

type Section = ScheduleImportReport['sections'][number]

function Block({ title, count, children }: { title: string; count?: number; children: ReactNode }) {
  return (
    <section className="acad__import-block">
      <div className="row-between">
        <b>{title}</b>
        {count !== undefined && <Chip className="num">{count}</Chip>}
      </div>
      {children}
    </section>
  )
}

function Report({ data }: { data: ScheduleImportReport }) {
  // смена куратора у 11 — первой: у них поступление, ошибка там дороже
  const curators = [...data.curator_changes].sort((a, b) => b.parallel - a.parallel || a.group.localeCompare(b.group))
  return (
    <>
      <Chip tone={data.errors.length ? 'bad' : data.warnings.length ? 'warn' : 'good'} className="users__linktext">
        {data.detail}
      </Chip>

      {data.errors.length > 0 && (
        <Block title={t('Ошибки — импорт не пойдёт, пока их не исправить в файле')} count={data.errors.length}>
          <Rows>
            <ShowAll limit={10}>
              {data.errors.map((text) => (
                <Row key={text} icon="alert" tone="bad" title={text} />
              ))}
            </ShowAll>
          </Rows>
        </Block>
      )}

      {data.sections.length > 0 && (
        <DataTable
          columns={[
            { key: 'title', title: t('Лист'), width: '40%', cell: (row: Section) => row.title },
            { key: 'created', title: t('Создастся'), width: '20%', align: 'right', cell: (row: Section) => <span className="num">{row.created}</span> },
            { key: 'updated', title: t('Обновится'), width: '20%', align: 'right', cell: (row: Section) => <span className="num">{row.updated}</span> },
            { key: 'unchanged', title: t('Без изменений'), width: '20%', align: 'right', cell: (row: Section) => <span className="num">{row.unchanged}</span> },
          ]}
          rows={data.sections}
          rowKey={(row) => row.code}
        />
      )}

      {data.lessons_from && (
        <p className="acad__note">
          {t('Еженедельные уроки действуют с 1 сентября, строки уроков заводятся с')} {dateWords(data.lessons_from)}:{' '}
          <b className="num">{data.lessons_to_create}</b>.{' '}
          {data.series_without_teacher > 0 &&
            `${t('Без учителя')}: ${data.series_without_teacher} — ${t('в расписании «учитель не назначен», отмечает администратор.')}`}
        </p>
      )}

      {curators.length > 0 && (
        <Block title={t('Смена куратора')} count={curators.length}>
          <Rows>
            {curators.map((row) => (
              <Row
                key={row.group}
                title={`${row.group} · ${row.parallel} ${t('параллель')}`}
                note={`${row.was || t('не назначен')} → ${row.will}, ${t('с')} ${dateWords(row.since)}`}
                right={row.parallel === 11 ? <Chip tone="warn" size="sm">{t('выпускная')}</Chip> : undefined}
              />
            ))}
          </Rows>
        </Block>
      )}

      {data.needs_role.length > 0 && (
        <Block title={t('Администрация: назначьте роль и включите')} count={data.needs_role.length}>
          <p className="muted">
            {t('Учётки заводятся выключенными и без пароля. Права администратора импорт не даёт никогда — роль и доступ назначаются в «Пользователях».')}
          </p>
          <Rows>
            {data.needs_role.map((row) => (
              <Row key={row.login} title={row.full_name} note={[row.position, row.login].filter(Boolean).join(' · ')} />
            ))}
          </Rows>
        </Block>
      )}

      {data.roles_kept.length > 0 && (
        <Block title={t('Роль не меняется')} count={data.roles_kept.length}>
          <p className="muted">{t('Импорт меняет только учителя на куратора и обратно. Остальное — руками в «Пользователях».')}</p>
          <Rows>
            {data.roles_kept.map((row) => (
              <Row key={row.full_name} title={row.full_name} note={`${t('в LMS')}: ${row.role} · ${t('в файле')}: ${row.file}`} />
            ))}
          </Rows>
        </Block>
      )}

      {data.warnings.length > 0 && (
        <Block title={t('Предупреждения')} count={data.warnings.length}>
          <Rows>
            <ShowAll limit={8}>
              {data.warnings.map((row, index) => (
                <Row key={`${index}-${row.text}`} icon="alert" tone="warn" title={row.text} />
              ))}
            </ShowAll>
          </Rows>
        </Block>
      )}

      {data.stale_series.length > 0 && (
        <Block title={t('Уроки в LMS, которых нет в файле')} count={data.stale_series.length}>
          <p className="muted">{t('Импорт их не удаляет. Если они лишние — уберите в расписании.')}</p>
          <Rows>
            <ShowAll limit={5}>
              {data.stale_series.map((text, index) => (
                <Row key={`${index}-${text}`} title={text} />
              ))}
            </ShowAll>
          </Rows>
        </Block>
      )}

      {data.groups_outside.length > 0 && (
        <p className="acad__note">
          {t('Группы в LMS, которых нет в файле, не меняются')}: {data.groups_outside.join(', ')}
        </p>
      )}
    </>
  )
}

function Credentials({ rows }: { rows: ScheduleImportCredential[] }) {
  const [saved, setSaved] = useState(false)
  const [busy, setBusy] = useState(false)
  const save = () => {
    setBusy(true)
    download('/users/handout/export/', { rows, kind: 'staff' }, 'paroli-sotrudnikov.xlsx')
      .then(() => setSaved(true))
      .catch((error: Error) => toast.error(error.message))
      .finally(() => setBusy(false))
  }
  return (
    <Block title={t('Выданные пароли')} count={rows.length}>
      <p className="muted">
        {t('Пароли показываются один раз и скачиваются списком один раз: в базе только их отпечаток. Срок временного пароля — 48 часов.')}
      </p>
      <DataTable
        columns={[
          { key: 'name', title: t('ФИО'), width: '45%', cell: (row: ScheduleImportCredential) => row.full_name },
          { key: 'login', title: t('Логин'), width: '30%', cell: (row: ScheduleImportCredential) => row.login },
          { key: 'password', title: t('Временный пароль'), width: '25%', cell: (row: ScheduleImportCredential) => <span className="users__password">{row.password}</span> },
        ]}
        rows={rows}
        rowKey={(row) => row.login}
        limit={10}
      />
      <div className="toolbar mb-0 mt-3">
        <Button size="sm" disabled={saved || busy} onClick={save}>
          {saved ? t('Список скачан') : t('Скачать список')}
        </Button>
      </div>
    </Block>
  )
}

export default function ScheduleImport() {
  const preview = useScheduleImportPreview()
  const apply = useScheduleImportApply()
  const fileInput = useRef<HTMLInputElement>(null)
  const [file, setFile] = useState<File | null>(null)
  const [data, setData] = useState<ScheduleImportReport | null>(null)
  const [done, setDone] = useState<ScheduleImportReport | null>(null)

  if (done) {
    return (
      <div className="acad__import">
        <Report data={done} />
        {done.credentials.length > 0 && <Credentials rows={done.credentials} />}
      </div>
    )
  }

  return (
    <div className="acad__import">
      <p className="muted">
        {t('Книга школы с листами «Сотрудники», «Группы», «Предметы», «Звонки», «Подгруппы», «Уроки». Сначала предпросмотр: база не меняется, пока не нажата «Применить». Повторный импорт того же файла ничего не удваивает.')}
      </p>
      <Input
        ref={fileInput}
        type="file"
        accept=".xlsx,.xlsm"
        className="users__file"
        onChange={(event) => {
          const picked = event.target.files?.[0]
          event.target.value = ''
          if (!picked) return
          setFile(picked)
          setData(null)
          preview.mutate(picked, { onSuccess: setData })
        }}
      />
      <div className="toolbar mb-0">
        <Button variant="outline" size="sm" onClick={() => fileInput.current?.click()}>
          {t('Выбрать файл')}
        </Button>
        {file && <span className="muted">{file.name}</span>}
      </div>

      {preview.isPending && <Loading />}
      {preview.isError && <ErrorNote error={preview.error} />}

      {data && (
        <>
          <Report data={data} />
          <div className="toolbar mb-0 mt-3">
            <Button
              size="sm"
              disabled={data.errors.length > 0 || apply.isPending || !file}
              onClick={() =>
                file &&
                apply.mutate(
                  { file, fingerprint: data.fingerprint },
                  {
                    onSuccess: (result) => {
                      toast.success(result.detail)
                      setDone(result)
                    },
                  },
                )
              }
            >
              {apply.isPending ? t('Применяется…') : t('Применить')}
            </Button>
            {apply.isError && <ErrorNote error={apply.error} />}
          </div>
        </>
      )}
    </div>
  )
}
