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
 *
 * «Заменить расписание с даты»: дата входит в отпечаток, поэтому смена
 * галочки или даты заново запускает предпросмотр — применяется то, что видели.
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
import { Checkbox } from '../../components/ui/checkbox'
import { Input } from '../../components/ui/input'
import { t } from '../../i18n'
import { todayAlmaty } from '../../lib/dates'
import { dateWords } from './shared'

type Section = ScheduleImportReport['sections'][number]

/** Раздел отчёта загрузки: заголовок, число и строки — общий для загрузок учебной части. */
export function Block({ title, count, children }: { title: string; count?: number; children: ReactNode }) {
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

      {data.replace_from && <Replace data={data} />}

      {data.lessons_from && (
        <p className="acad__note">
          {t('Еженедельные уроки действуют с 1 сентября, строки уроков заводятся с {date}:', { date: dateWords(data.lessons_from) })}{' '}
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
                title={`${row.group} · ${t('{n} параллель', { n: row.parallel })}`}
                note={`${row.was || t('не назначен')} → ${row.will}, ${t('с {date}', { date: dateWords(row.since) })}`}
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

      {data.without_teacher.length > 0 && (
        <Block title={t('Без учителя')} count={data.without_teacher.length}>
          <p className="muted">{t('Учителя назначьте в его карточке на странице «Учителя»: «Добавить группу».')}</p>
          <Rows>
            <ShowAll limit={5}>
              {data.without_teacher.map((row) => (
                <Row
                  key={`${row.cohort}-${row.subject}`}
                  title={`${row.subject} · ${row.cohort}`}
                  note={t('Уроков в неделю: {n}', { n: row.count })}
                />
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

/** Замена с даты: что заканчивается, что удаляется, что остаётся и что не трогается. */
function Replace({ data }: { data: ScheduleImportReport }) {
  const date = dateWords(data.replace_from ?? '')
  const numbers = [
    { key: 'ended', title: t('Еженедельных уроков закончится накануне {date}', { date }), value: data.series_ended },
    { key: 'deleted', title: t('Уроков с {date} удалится — на них нет данных', { date }), value: data.lessons_deleted },
    { key: 'kept', title: t('Уроков с {date} останется — на них есть данные', { date }), value: data.lessons_kept.length },
    { key: 'created', title: t('Уроков заведётся с {date} по новому расписанию', { date }), value: data.lessons_to_create },
  ]
  return (
    <>
      <Block title={t('Замена расписания с {date}', { date })}>
        <p className="muted">
          {t('Уроки до этой даты не меняются. Пары «группа + предмет», которых в файле нет, не трогаются.')}
        </p>
        <Rows>
          {numbers.map((row) => (
            <Row key={row.key} title={row.title} right={<Chip className="num">{row.value}</Chip>} />
          ))}
        </Rows>
      </Block>

      {data.lessons_kept.length > 0 && (
        <Block title={t('Остаются из-за данных')} count={data.lessons_kept.length}>
          <p className="muted">
            {t('Импорт их не удаляет: на них оценки, посещаемость, ДЗ, тема или СОР и СОЧ. Лишние уберите в расписании.')}
          </p>
          <Rows>
            <ShowAll limit={10}>
              {data.lessons_kept.map((row) => (
                <Row
                  key={row.id}
                  title={`${dateWords(row.date)} · ${t('{n} урок', { n: row.slot })} · ${row.subject} · ${row.cohort}`}
                  note={[row.teacher || t('учитель не назначен'), row.data].join(' · ')}
                />
              ))}
            </ShowAll>
          </Rows>
        </Block>
      )}

      {data.journals_passed.length > 0 && (
        <Block title={t('Журнал передаётся с {date}', { date })} count={data.journals_passed.length}>
          <p className="muted">{t('Журнал общий: оценки до даты замены остаются в нём.')}</p>
          <Rows>
            <ShowAll limit={8}>
              {data.journals_passed.map((row) => (
                <Row
                  key={`${row.subject}-${row.cohort}`}
                  title={`${row.subject} · ${row.cohort}`}
                  note={`${row.was || t('не назначен')} → ${row.will || t('учитель не назначен')}`}
                />
              ))}
            </ShowAll>
          </Rows>
        </Block>
      )}

      {data.untouched.length > 0 && (
        <Block title={t('Не трогаются: этих пар в файле нет')} count={data.untouched.length}>
          <Rows>
            <ShowAll limit={5}>
              {data.untouched.map((row) => (
                <Row
                  key={`${row.subject}-${row.cohort}-${row.teacher}`}
                  title={`${row.subject} · ${row.cohort}`}
                  note={[row.teacher || t('учитель не назначен'), t('Уроков в неделю: {n}', { n: row.count })].join(' · ')}
                />
              ))}
            </ShowAll>
          </Rows>
        </Block>
      )}

      {data.subgroups_unused.length > 0 && (
        <p className="acad__note">
          {t('Подгруппы больше не используются, не удаляются')}: {data.subgroups_unused.join(', ')}
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
  const today = todayAlmaty()
  const [replace, setReplace] = useState(false)
  const [since, setSince] = useState(today)
  const replaceFrom = replace && since ? since : null

  // дата — в отпечатке: другой режим или дата — новый предпросмотр
  const check = (picked: File | null, from: string | null) => {
    setData(null)
    if (picked) preview.mutate({ file: picked, replaceFrom: from }, { onSuccess: setData })
  }

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
      <div className="acad__replace">
        <label className="acad__replace-check">
          <Checkbox
            checked={replace}
            aria-label={t('Заменить расписание с даты')}
            onCheckedChange={(on) => {
              setReplace(Boolean(on))
              check(file, on ? since : null)
            }}
          />
          {t('Заменить расписание с даты')}
        </label>
        <Input
          type="date"
          className="acad__replace-date"
          aria-label={t('Дата замены')}
          value={since}
          min={today}
          disabled={!replace}
          onChange={(event) => {
            setSince(event.target.value)
            if (event.target.value >= today) check(file, event.target.value)
          }}
        />
      </div>
      {replace && (
        <p className="muted">
          {t('Прежние еженедельные уроки пар «группа + предмет» из файла, которых в нём нет, закончатся накануне даты. Их уроки с даты без данных удалятся, с данными — останутся и будут названы. Сменился учитель — журнал передаётся ему с даты.')}
        </p>
      )}
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
          check(picked, replaceFrom)
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
                  { file, fingerprint: data.fingerprint, replaceFrom: data.replace_from },
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
