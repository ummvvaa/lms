/**
 * Работа ментора с кружком (31.10.2026): ученики, задание, отметка по QR, заметки.
 *
 * Панели общие: у ментора каждая — свой пункт меню, у администратора —
 * вкладки карточки кружка (он может всё, что ментор). Ментор видит только
 * свой кружок и записанных в него; заметки — только он и администратор.
 * Отметка существует, пока её включил администратор: QR и «Пришли / Ещё нет»
 * взяты у секций (`sport/Session`, `sport/QrCode`).
 */
import { useRef, useState, type ReactNode } from 'react'
import { toast } from 'sonner'
import { useSearchParams } from 'react-router'
import {
  clubSessionToken,
  homeworkFilePath,
  useClubHomework,
  useClubMarkAction,
  useClubNotes,
  useClubSession,
  useClubStudents,
  useHomeworkAction,
  useMentorClubs,
  useNoteAction,
  type ClubCard,
  type ClubHomework,
  type MentorClub,
} from '../../api/clubs'
import { downloadFile } from '../../api/client'
import Field from '../../components/Field'
import Modal from '../../components/Modal'
import RowMenu, { RowMenuItem } from '../../components/RowMenu'
import { Segmented, ShowAll } from '../../components/patterns'
import { Chip, DataCard, EmptyNote, ErrorNote, Loading, ScreenHead } from '../../components/ui'
import { Button } from '../../components/ui/button'
import { Input } from '../../components/ui/input'
import { t, tk } from '../../i18n'
import { formatDateLong, formatDayMonth, formatTime } from '../../lib/format'
import QrCode from '../sport/QrCode'
import { useLiveToken } from '../sport/Session'
import '../directors/directors.css'
import '../sport/sport.css'
import './clubs.css'

const fail = (reason: unknown) => toast.error(reason instanceof Error ? reason.message : String(reason))

/** Кружок, с которым работает ментор: обычно один; несколько — выбор в адресе (`?club=`). */
function useCurrentClub(): { clubs: MentorClub[]; club: MentorClub | null; pick: (id: number) => void; ready: boolean; error: unknown } {
  const { data, isLoading, error } = useMentorClubs()
  const [params, setParams] = useSearchParams()
  const clubs = data?.clubs ?? []
  const club = clubs.find((row) => row.id === Number(params.get('club'))) ?? clubs[0] ?? null
  return {
    clubs,
    club,
    pick: (id) => setParams({ club: String(id) }, { replace: true }),
    ready: !isLoading || Boolean(data),
    error,
  }
}

/** Экран ментора: шапка, выбор кружка при нескольких и панель. */
function MentorScreen({
  title,
  subtitle,
  children,
}: {
  title: string
  subtitle: (club: MentorClub) => string
  children: (club: MentorClub) => ReactNode
}) {
  const { clubs, club, pick, ready, error } = useCurrentClub()
  if (!ready) return <Loading kind="cards" />
  if (error) return <ErrorNote error={error} />
  if (!club)
    return (
      <div className="lay-screen">
        <ScreenHead title={title} />
        <DataCard title={t('Кружок')} empty={t('кружок к вашей учётке ещё не привязан · привязывает администратор')} />
      </div>
    )
  return (
    <div className="lay-screen">
      <ScreenHead title={title} subtitle={subtitle(club)} />
      {clubs.length > 1 && (
        <Segmented
          value={String(club.id)}
          onChange={(value) => pick(Number(value))}
          label={t('Кружок')}
          items={clubs.map((row) => ({ value: String(row.id), label: row.title }))}
        />
      )}
      {children(club)}
    </div>
  )
}

export function MentorStudents() {
  return (
    <MentorScreen title={t('Ученики')} subtitle={(club) => `${club.title} · ${club.schedule}`}>
      {(club) => <StudentsPanel club={club} />}
    </MentorScreen>
  )
}

export function MentorHomework() {
  return (
    <MentorScreen title={t('Домашнее задание')} subtitle={(club) => t('{club} · ученики видят его в «Кружках»', { club: club.title })}>
      {(club) => <HomeworkPanel club={club} />}
    </MentorScreen>
  )
}

export function MentorSession() {
  return (
    <MentorScreen title={t('Отметка')} subtitle={(club) => `${club.title} · ${club.schedule}`}>
      {(club) => <SessionPanel club={club} />}
    </MentorScreen>
  )
}

export function MentorNotes() {
  return (
    <MentorScreen title={t('Заметки')} subtitle={() => t('Видите только вы и администратор')}>
      {(club) => <NotesPanel club={club} />}
    </MentorScreen>
  )
}

/* --- Ученики ------------------------------------------------------------- */

export function StudentsPanel({ club }: { club: ClubCard }) {
  const { data, isLoading, error } = useClubStudents(club.id)
  const [noting, setNoting] = useState<number | null>(null)
  if (isLoading && !data) return <Loading />
  if (error) return <ErrorNote error={error} />
  if (!data) return null
  return (
    <DataCard title={t('Записаны в кружок')} count={data.rows.length}>
      {data.rows.length === 0 ? (
        <EmptyNote what={tk('в кружок пока никто не записан')} who={tk('ученики записываются в «Кружках»')} />
      ) : (
        <div className="dir__rows">
          <ShowAll limit={12}>
            {data.rows.map((row) => (
              <div key={row.id} className="dir__row">
                <span className="dir__what">
                  <b className="dir__name">{row.student.full_name}</b>
                  <span className="t-note">
                    {[row.student.group, t('записался {date}', { date: formatDayMonth(row.enrolled_at) })]
                      .filter(Boolean)
                      .join(' · ')}
                  </span>
                </span>
                {row.notes > 0 ? <Chip size="sm">{t('заметок {n}', { n: row.notes })}</Chip> : <span />}
                <span className="dir__acts">
                  <Button variant="outline" size="sm" onClick={() => setNoting(row.student.id)}>
                    {t('Заметка')}
                  </Button>
                </span>
              </div>
            ))}
          </ShowAll>
        </div>
      )}
      {noting !== null && (
        <NoteDialog
          club={club}
          student={noting}
          students={data.rows.map((row) => row.student)}
          onClose={() => setNoting(null)}
        />
      )}
    </DataCard>
  )
}

/* --- Задание ------------------------------------------------------------- */

export function HomeworkPanel({ club }: { club: ClubCard }) {
  const { data, isLoading, error } = useClubHomework(club.id)
  const [editing, setEditing] = useState<ClubHomework | 'new' | null>(null)
  const { withdraw } = useHomeworkAction(club.id)
  if (isLoading && !data) return <Loading />
  if (error) return <ErrorNote error={error} />
  if (!data) return null
  return (
    <DataCard
      title={t('Задания кружка')}
      count={data.rows.length || undefined}
      right={<Button onClick={() => setEditing('new')}>{t('Новое задание')}</Button>}
    >
      {data.rows.length === 0 ? (
        <EmptyNote what={tk('заданий пока нет')} who={tk('ученики кружка увидят задание в «Кружках»')} />
      ) : (
        <div className="dir__rows">
          {data.rows.map((row) => (
            <div key={row.id} className="dir__row">
              <span className="dir__what">
                <span className="clubs-text">{row.text}</span>
                <span className="t-note">
                  {[
                    t('срок {date}', { date: formatDateLong(row.due) }),
                    t('опубликовано {date}', { date: formatDayMonth(row.created_at) }),
                    row.file_name,
                  ]
                    .filter(Boolean)
                    .join(' · ')}
                </span>
              </span>
              {row.has_file ? <FileButton homework={row} /> : <span />}
              <span className="dir__acts">
                <RowMenu>
                  <RowMenuItem onClick={() => setEditing(row)}>{t('Изменить')}</RowMenuItem>
                  <RowMenuItem
                    onClick={() =>
                      withdraw.mutate(row.id, {
                        onSuccess: () => toast.success(t('Задание снято · ученики его больше не видят')),
                        onError: fail,
                      })
                    }
                  >
                    {t('Снять')}
                  </RowMenuItem>
                </RowMenu>
              </span>
            </div>
          ))}
        </div>
      )}
      {editing && (
        <HomeworkDialog club={club} row={editing === 'new' ? null : editing} onClose={() => setEditing(null)} />
      )}
    </DataCard>
  )
}

/** Кнопка скачивания файла задания — у ментора и у ученика кружка. */
export function FileButton({ homework }: { homework: ClubHomework }) {
  return (
    <Button
      variant="outline"
      size="sm"
      onClick={() => downloadFile(homeworkFilePath(homework.id), homework.file_name).catch(fail)}
    >
      {t('Файл')}
    </Button>
  )
}

function HomeworkDialog({ club, row, onClose }: { club: ClubCard; row: ClubHomework | null; onClose: () => void }) {
  const { publish, edit } = useHomeworkAction(club.id)
  const [text, setText] = useState(row?.text ?? '')
  const [due, setDue] = useState(row?.due ?? '')
  const [file, setFile] = useState<File | null>(null)
  const [dropFile, setDropFile] = useState(false)
  const input = useRef<HTMLInputElement>(null)
  const busy = publish.isPending || edit.isPending
  const done = (words: string) => {
    toast.success(words)
    onClose()
  }
  return (
    <Modal title={row ? t('Изменить задание') : t('Новое задание')} note={club.title} onClose={onClose}>
      <Field kind="textarea" name="club-hw-text" label={t('Задание')} value={text} onChange={setText} rows={5} autoFocus />
      <Field kind="date" name="club-hw-due" label={t('Срок')} value={due} onChange={setDue} />
      <div className="clubs-file">
        <Input
          ref={input}
          type="file"
          className="clubs-file__input"
          accept=".pdf,.doc,.docx,.ppt,.pptx,.xls,.xlsx,.txt,.png,.jpg,.jpeg,.zip"
          onChange={(event) => {
            setFile(event.target.files?.[0] ?? null)
            setDropFile(false)
          }}
        />
        <Button variant="outline" size="sm" onClick={() => input.current?.click()}>
          {file || (row?.has_file && !dropFile) ? t('Заменить файл') : t('Прикрепить файл')}
        </Button>
        <span className="t-note">
          {file?.name ?? (row?.has_file && !dropFile ? row.file_name : t('файл не обязателен · до 20 МБ'))}
        </span>
        {row?.has_file && !dropFile && !file && (
          <Button variant="ghost" size="sm" onClick={() => setDropFile(true)}>
            {t('Убрать файл')}
          </Button>
        )}
      </div>
      {(publish.error || edit.error) && <ErrorNote error={publish.error ?? edit.error} />}
      <div className="acad__actions">
        <Button variant="outline" onClick={onClose}>
          {t('Отмена')}
        </Button>
        <Button
          disabled={!text.trim() || !due || busy}
          onClick={() =>
            row
              ? edit.mutate(
                  { id: row.id, text, due, file, drop_file: dropFile },
                  { onSuccess: () => done(t('Задание сохранено')) },
                )
              : publish.mutate(
                  { text, due, file },
                  { onSuccess: () => done(t('Задание опубликовано · ученики кружка видят его в «Кружках»')) },
                )
          }
        >
          {row ? t('Сохранить') : t('Опубликовать')}
        </Button>
      </div>
    </Modal>
  )
}

/* --- Отметка по QR -------------------------------------------------------- */

const STATE_WORDS = {
  none: tk('сегодня встречи нет'),
  soon: tk('Код откроется в начале встречи'),
  past: tk('Встреча закончилась, отметки закрыты'),
}

export function SessionPanel({ club }: { club: ClubCard }) {
  const session = useClubSession(club.marks_enabled ? club.id : null, true)
  const live = session.data?.state === 'live'
  const { token, left } = useLiveToken(club.id, live, clubSessionToken)
  const actions = useClubMarkAction(club.id)
  const [tab, setTab] = useState<'came' | 'wait'>('came')
  const box = useRef<HTMLDivElement>(null)
  if (!club.marks_enabled)
    return <DataCard title={t('Отметка')} empty={t('отметка в этом кружке выключена · включает администратор')} />
  if (session.isLoading && !session.data) return <Loading />
  if (session.error) return <ErrorNote error={session.error} />
  const data = session.data
  if (!data) return null
  const url = token?.token ? `${window.location.origin}/k/${token.token}` : ''
  const came = data.students.filter((s) => s.came)
  const waiting = data.students.filter((s) => !s.came)
  const shown = tab === 'came' ? came : waiting
  return (
    <div className="sport-pair clubs-session">
      <DataCard
        className="card--beam"
        title={club.title}
        note={[formatDateLong(data.date), data.time].filter(Boolean).join(' · ')}
      >
        <div className="sport-qr" ref={box}>
          {live && url ? (
            <>
              <QrCode value={url} />
              <p className="sport-qr__count">
                {t('новый код через')} <b className="num">{left}</b>
              </p>
              <p className="t-note">
                {t('Фото кода, отправленное другу, через {n} секунд не сработает', { n: token?.ttl ?? 20 })}
              </p>
            </>
          ) : (
            <EmptyNote what={data.state === 'live' ? tk('Код загружается') : STATE_WORDS[data.state]} />
          )}
        </div>
        {live && (
          <div className="acad__actions">
            <Button
              variant="outline"
              disabled={!url}
              onClick={() => {
                void box.current?.requestFullscreen?.().catch(() => undefined)
              }}
            >
              {t('На весь экран')}
            </Button>
          </div>
        )}
      </DataCard>
      <DataCard
        title={t('Отметились')}
        right={<Chip className="num">{t('{came} из {n}', { came: came.length, n: data.students.length })}</Chip>}
      >
        <Segmented
          value={tab}
          onChange={setTab}
          label={t('Кто пришёл')}
          items={[
            { value: 'came', label: t('Пришли {n}', { n: came.length }) },
            { value: 'wait', label: t('Ещё нет {n}', { n: waiting.length }) },
          ]}
        />
        {shown.length === 0 ? (
          <EmptyNote what={tab === 'came' ? tk('пока никто не отметился') : tk('отметились все')} />
        ) : (
          <div className="dir__rows sport-roster">
            {shown.map((student) => (
              <div key={student.id} className="dir__row">
                <span className="dir__what">
                  <b className="dir__name">{student.short_name}</b>
                  <span className="t-note">
                    {[
                      student.group,
                      student.came && student.at
                        ? student.method === 'manual'
                          ? t('вручную · {time}', { time: formatTime(student.at) })
                          : t('по QR · {time}', { time: formatTime(student.at) })
                        : '',
                    ]
                      .filter(Boolean)
                      .join(' · ')}
                  </span>
                </span>
                <span />
                <span className="dir__acts">
                  {student.came
                    ? student.method === 'manual' && (
                        <Button
                          variant="ghost"
                          size="sm"
                          disabled={actions.unmark.isPending}
                          onClick={() => actions.unmark.mutate(student.id, { onError: fail })}
                        >
                          {t('Снять')}
                        </Button>
                      )
                    : data.state !== 'soon' &&
                      data.state !== 'none' && (
                        <Button
                          variant="outline"
                          size="sm"
                          disabled={actions.mark.isPending}
                          onClick={() =>
                            actions.mark.mutate(student.id, {
                              onSuccess: () => toast.success(t('{name} отмечен вручную', { name: student.short_name })),
                              onError: fail,
                            })
                          }
                        >
                          {t('Отметить')}
                        </Button>
                      )}
                </span>
              </div>
            ))}
          </div>
        )}
      </DataCard>
    </div>
  )
}

/* --- Заметки ------------------------------------------------------------- */

export function NotesPanel({ club }: { club: ClubCard }) {
  const students = useClubStudents(club.id)
  const [student, setStudent] = useState('')
  const { data, isLoading, error } = useClubNotes(club.id, student ? Number(student) : null)
  const { remove } = useNoteAction(club.id)
  const [adding, setAdding] = useState(false)
  if (isLoading && !data) return <Loading />
  if (error) return <ErrorNote error={error} />
  if (!data) return null
  const members = (students.data?.rows ?? []).map((row) => row.student)
  return (
    <DataCard
      title={t('Заметки об учениках')}
      count={data.rows.length || undefined}
      right={
        <Button disabled={members.length === 0} onClick={() => setAdding(true)}>
          {t('Новая заметка')}
        </Button>
      }
    >
      <div className="filters clubs-filters">
        <Field
          kind="select"
          name="club-note-student"
          label={t('Ученик')}
          value={student}
          onChange={setStudent}
          placeholder={t('Все ученики')}
          options={members.map((row) => ({ value: String(row.id), title: row.full_name }))}
        />
      </div>
      {data.rows.length === 0 ? (
        <EmptyNote what={tk('заметок пока нет')} who={tk('видите только вы и администратор')} />
      ) : (
        <div className="dir__rows">
          <ShowAll limit={10}>
            {data.rows.map((row) => (
              <div key={row.id} className="dir__row">
                <span className="dir__what">
                  <b className="dir__name">{row.student.full_name}</b>
                  <span className="clubs-text">{row.text}</span>
                  <span className="t-note">{[formatDateLong(row.created_at), row.author].filter(Boolean).join(' · ')}</span>
                </span>
                <span />
                <span className="dir__acts">
                  <RowMenu>
                    <RowMenuItem
                      onClick={() =>
                        remove.mutate(row.id, {
                          onSuccess: () => toast.success(t('Заметка убрана в архив')),
                          onError: fail,
                        })
                      }
                    >
                      {t('Убрать')}
                    </RowMenuItem>
                  </RowMenu>
                </span>
              </div>
            ))}
          </ShowAll>
        </div>
      )}
      {adding && (
        <NoteDialog
          club={club}
          student={student ? Number(student) : (members[0]?.id ?? null)}
          students={members}
          onClose={() => setAdding(false)}
        />
      )}
    </DataCard>
  )
}

function NoteDialog({
  club,
  student,
  students,
  onClose,
}: {
  club: ClubCard
  student: number | null
  students: { id: number; full_name: string }[]
  onClose: () => void
}) {
  const { add } = useNoteAction(club.id)
  const [who, setWho] = useState(student ? String(student) : '')
  const [text, setText] = useState('')
  return (
    <Modal title={t('Заметка об ученике')} note={t('видите только вы и администратор')} onClose={onClose}>
      <Field
        kind="select"
        name="club-note-who"
        label={t('Ученик')}
        value={who}
        onChange={setWho}
        options={students.map((row) => ({ value: String(row.id), title: row.full_name }))}
      />
      <Field
        kind="textarea"
        name="club-note-text"
        label={t('Заметка')}
        value={text}
        onChange={setText}
        rows={4}
        placeholder={t('например: есть потенциал, сделал прототип')}
        autoFocus
      />
      {add.error && <ErrorNote error={add.error} />}
      <div className="acad__actions">
        <Button variant="outline" onClick={onClose}>
          {t('Отмена')}
        </Button>
        <Button
          disabled={!who || !text.trim() || add.isPending}
          onClick={() =>
            add.mutate(
              { student: Number(who), text },
              {
                onSuccess: () => {
                  toast.success(t('Заметка сохранена'))
                  onClose()
                },
              },
            )
          }
        >
          {t('Сохранить')}
        </Button>
      </div>
    </Modal>
  )
}
