/**
 * «Кружки» у администратора (31.10.2026): список, заведение, правка и архив.
 *
 * Слева кружки с числом записанных, справа — карточка кружка: ментор, дни
 * и время, кому можно записываться, окно записи, отметка посещения и список
 * записанных с фильтром по группе и выгрузкой в Excel. Архив мягкий: кружок
 * пропадает у учеников, записи и история остаются, вернуть можно отсюда же.
 */
import { useState } from 'react'
import { toast } from 'sonner'
import { useSearchParams } from 'react-router'
import { downloadFile } from '../../api/client'
import {
  useArchiveClub,
  useClubMembers,
  useClubs,
  useMentorAccounts,
  useSaveClub,
  type ClubAdminRow,
  type ClubDraft,
} from '../../api/clubs'
import Field from '../../components/Field'
import Modal from '../../components/Modal'
import { ShowAll } from '../../components/patterns'
import { Chip, DataCard, EmptyNote, ErrorNote, Loading, ScreenHead, ScreenTabs } from '../../components/ui'
import { Button } from '../../components/ui/button'
import { Switch } from '../../components/ui/switch'
import { t, tk } from '../../i18n'
import { formatDateTimeLong, formatDayMonth } from '../../lib/format'
import { WEEKDAYS } from '../sport/words'
import '../directors/directors.css'
import '../sport/sport.css'
import './clubs.css'

const fail = (reason: unknown) => toast.error(reason instanceof Error ? reason.message : String(reason))

/** Параллели школы — галочки «Кому можно записываться». */
export const PARALLELS = [8, 9, 10, 11]

export default function Clubs() {
  const [params, setParams] = useSearchParams()
  const archived = params.get('archived') === '1'
  const { data, isLoading, error } = useClubs(archived)
  const [creating, setCreating] = useState(false)
  if (isLoading && !data) return <Loading kind="cards" />
  if (error) return <ErrorNote error={error} />
  if (!data) return null
  const picked = data.rows.find((row) => row.id === Number(params.get('open'))) ?? data.rows[0] ?? null
  const show = (next: Record<string, string>) => setParams(next, { replace: true })

  return (
    <div className="lay-screen">
      <ScreenHead
        title={t('Кружки')}
        subtitle={t('Расписание, ментор, кому можно записываться и кто записан')}
        actions={<Button onClick={() => setCreating(true)}>{t('Новый кружок')}</Button>}
      />
      <ScreenTabs
        value={archived ? 'archived' : 'live'}
        onChange={(next) => show(next === 'archived' ? { archived: '1' } : {})}
        items={[
          { value: 'live', label: t('Действующие') },
          { value: 'archived', label: t('Архив · {n}', { n: data.archived_total }) },
        ]}
      />
      {data.rows.length === 0 ? (
        <DataCard
          title={archived ? t('Архив') : t('Кружки')}
          empty={archived ? t('в архиве пусто') : t('кружков пока нет')}
        />
      ) : (
        <div className="sport-pair">
          <DataCard title={t('Кружки')} count={data.rows.length}>
            <div className="sport-today">
              {data.rows.map((row) => (
                <Button
                  key={row.id}
                  variant="ghost"
                  className={`sport-slot${row.id === picked?.id ? ' sport-slot--on' : ''}`}
                  aria-pressed={row.id === picked?.id}
                  onClick={() => show({ ...(archived ? { archived: '1' } : {}), open: String(row.id) })}
                >
                  <span className="sport-slot__line">
                    <b>{row.title}</b>
                    {row.marks_enabled && (
                      <Chip tone="info" size="sm">
                        {t('отметка')}
                      </Chip>
                    )}
                  </span>
                  <span className="t-note num">{row.schedule}</span>
                  <span className="t-note num">
                    {t('{mentor} · записано {n}', { mentor: row.mentor_name, n: row.enrolled })}
                  </span>
                </Button>
              ))}
            </div>
          </DataCard>
          {picked && <ClubCard club={picked} key={picked.id} />}
        </div>
      )}
      {creating && <ClubDialog club={null} onClose={() => setCreating(false)} />}
    </div>
  )
}

/** Окно записи словами: «открыта всегда», «открыта до …» или «закрыта». */
export function windowWords(club: Pick<ClubAdminRow, 'open' | 'enroll_until'>): string {
  if (!club.enroll_until) return t('открыта всегда')
  return club.open
    ? t('открыта до {when}', { when: formatDateTimeLong(club.enroll_until) })
    : t('закрыта с {when}', { when: formatDateTimeLong(club.enroll_until) })
}

type CardTab = 'members'

function ClubCard({ club }: { club: ClubAdminRow }) {
  const [editing, setEditing] = useState(false)
  const [tab, setTab] = useState<CardTab>('members')
  const save = useSaveClub()
  const archive = useArchiveClub()
  const [archiving, setArchiving] = useState(false)
  return (
    <DataCard
      className="card--beam"
      title={club.title}
      note={club.schedule}
      right={
        club.archived ? (
          <Button
            variant="outline"
            size="sm"
            disabled={save.isPending}
            onClick={() =>
              save.mutate(
                { id: club.id, archived: false },
                { onSuccess: () => toast.success(t('Кружок возвращён из архива')), onError: fail },
              )
            }
          >
            {t('Вернуть из архива')}
          </Button>
        ) : (
          <span className="dir__acts">
            <Button variant="outline" size="sm" onClick={() => setEditing(true)}>
              {t('Изменить')}
            </Button>
            <Button variant="ghost" size="sm" onClick={() => setArchiving(true)}>
              {t('В архив')}
            </Button>
          </span>
        )
      }
    >
      {club.description && <p className="clubs-text">{club.description}</p>}
      <div className="dir__lines">
        <div className="dir__line">
          <span>{t('Ментор')}</span>
          <b>{club.mentor_account ? `${club.mentor_name} · ${club.mentor_account}` : club.mentor_name}</b>
        </div>
        <div className="dir__line">
          <span>{t('Кому можно записываться')}</span>
          <b className="num">{t('параллели {grades}', { grades: club.parallels.join(', ') })}</b>
        </div>
        <div className="dir__line">
          <span>{t('Запись')}</span>
          <b>{windowWords(club)}</b>
        </div>
        <div className="dir__line">
          <span>{t('Отметка посещения')}</span>
          {club.archived ? (
            <b>{club.marks_enabled ? t('включена') : t('выключена')}</b>
          ) : (
            <Switch
              checked={club.marks_enabled}
              aria-label={t('Отметка посещения')}
              disabled={save.isPending}
              onCheckedChange={(next) =>
                save.mutate(
                  { id: club.id, marks_enabled: next },
                  {
                    onSuccess: () =>
                      toast.success(
                        next
                          ? t('Отметка включена · ментор показывает QR на встрече')
                          : t('Отметка выключена · у ученика, ментора и куратора её нет'),
                      ),
                    onError: fail,
                  },
                )
              }
            />
          )}
        </div>
      </div>
      <ScreenTabs value={tab} onChange={setTab} items={[{ value: 'members', label: t('Записанные') }]} />
      {tab === 'members' && <Members club={club} />}
      {editing && <ClubDialog club={club} onClose={() => setEditing(false)} />}
      {archiving && (
        <Modal title={t('Убрать кружок в архив?')} note={club.title} onClose={() => setArchiving(false)}>
          <p className="t-note">
            {t('Кружок пропадёт у учеников и ментора. Записи, задания и заметки останутся, вернуть можно из вкладки «Архив».')}
          </p>
          <div className="acad__actions">
            <Button variant="outline" onClick={() => setArchiving(false)}>
              {t('Отмена')}
            </Button>
            <Button
              variant="destructive"
              disabled={archive.isPending}
              onClick={() =>
                archive.mutate(club.id, {
                  onSuccess: () => {
                    toast.success(t('Кружок в архиве'))
                    setArchiving(false)
                  },
                  onError: fail,
                })
              }
            >
              {t('В архив')}
            </Button>
          </div>
        </Modal>
      )}
    </DataCard>
  )
}

/** Записанные за всё время: действующие сверху, вышедшие — с датой выхода. */
function Members({ club }: { club: ClubAdminRow }) {
  const [group, setGroup] = useState('')
  const { data, isLoading, error } = useClubMembers(club.id, group)
  if (isLoading && !data) return <Loading />
  if (error) return <ErrorNote error={error} />
  if (!data) return null
  return (
    <div className="sport-list">
      <div className="filters clubs-filters">
        <Field
          kind="select"
          name="club-group"
          label={t('Группа')}
          value={group}
          onChange={setGroup}
          placeholder={t('Все группы')}
          options={data.groups.map((row) => ({ value: String(row.id), title: row.code }))}
        />
        <Button
          variant="outline"
          onClick={() =>
            downloadFile(`/clubs/${club.id}/members/export/${group ? `?group=${group}` : ''}`, `${club.title}.xlsx`)
              .then(() => toast.success(t('Файл xlsx скачан')))
              .catch(fail)
          }
        >
          {t('Скачать Excel')}
        </Button>
      </div>
      {data.rows.length === 0 ? (
        <EmptyNote what={tk('в кружок пока никто не записан')} who={tk('ученики записываются в «Кружках»')} />
      ) : (
        <div className="dir__rows">
          <ShowAll limit={8}>
            {data.rows.map((row) => (
              <div key={row.id} className="dir__row">
                <span className="dir__what">
                  <b className="dir__name">{row.student.short_name}</b>
                  <span className="t-note">
                    {[row.student.group, t('записался {date}', { date: formatDayMonth(row.enrolled_at) })]
                      .filter(Boolean)
                      .join(' · ')}
                  </span>
                </span>
                {row.left && row.ended_at ? (
                  <Chip size="sm">{t('вышел {date}', { date: formatDayMonth(row.ended_at) })}</Chip>
                ) : (
                  <Chip tone="good" size="sm">
                    {t('в кружке')}
                  </Chip>
                )}
                <span />
              </div>
            ))}
          </ShowAll>
        </div>
      )}
    </div>
  )
}

interface MeetingDraft {
  key: string
  weekday: number
  starts: string
  ends: string
}

/** Новый кружок или правка: поля из A, встречи по дням, параллели, окно записи, отметка. */
function ClubDialog({ club, onClose }: { club: ClubAdminRow | null; onClose: () => void }) {
  const save = useSaveClub()
  const mentors = useMentorAccounts()
  const [title, setTitle] = useState(club?.title ?? '')
  const [description, setDescription] = useState(club?.description ?? '')
  const [mentorName, setMentorName] = useState(club?.mentor_name ?? '')
  const [mentor, setMentor] = useState(club?.mentor ? String(club.mentor) : '')
  const [meetings, setMeetings] = useState<MeetingDraft[]>(
    club?.meetings.map((row, index) => ({ key: `m-${index}`, ...row })) ?? [
      { key: 'm-0', weekday: 0, starts: '15:00', ends: '18:00' },
    ],
  )
  const [parallels, setParallels] = useState<number[]>(club?.parallels ?? PARALLELS)
  const [until, setUntil] = useState(Boolean(club?.enroll_until))
  const [date, setDate] = useState(club?.enroll_until ? club.enroll_until.slice(0, 10) : '')
  const [time, setTime] = useState(club?.enroll_until ? club.enroll_until.slice(11, 16) : '23:59')
  const [marks, setMarks] = useState(club?.marks_enabled ?? false)
  const change = (index: number, patch: Partial<MeetingDraft>) =>
    setMeetings((rows) => rows.map((row, i) => (i === index ? { ...row, ...patch } : row)))
  const body: Partial<ClubDraft> & { id: number | null } = {
    id: club?.id ?? null,
    title,
    description,
    mentor_name: mentorName,
    mentor: mentor ? Number(mentor) : null,
    enroll_until: until && date ? `${date}T${time || '23:59'}:00` : null,
    marks_enabled: marks,
    meetings: meetings.map(({ weekday, starts, ends }) => ({ weekday, starts, ends })),
    parallels,
  }
  return (
    <Modal title={club ? t('Изменить кружок') : t('Новый кружок')} note={club?.title} onClose={onClose} wide>
      <Field name="club-title" label={t('Название')} value={title} onChange={setTitle} autoFocus={!club} />
      <Field
        kind="textarea"
        name="club-description"
        label={t('Описание')}
        value={description}
        onChange={setDescription}
        rows={3}
      />
      <div className="clubs-pair">
        <Field
          name="club-mentor-name"
          label={t('Ментор')}
          value={mentorName}
          onChange={setMentorName}
          hint={t('имя на карточке кружка')}
        />
        <Field
          kind="select"
          name="club-mentor"
          label={t('Учётка ментора')}
          value={mentor}
          onChange={setMentor}
          placeholder={t('Без учётки')}
          options={(mentors.data?.rows ?? []).map((row) => ({ value: String(row.id), title: row.title }))}
          hint={t('учётки с ролью «Ментор» заводятся в «Пользователях»')}
        />
      </div>
      <span className="t-card">{t('Дни и время')}</span>
      <div className="sport-edit">
        {meetings.map((row, index) => (
          <div key={row.key} className="sport-edit__row clubs-meeting">
            <Field
              kind="select"
              name={`club-day-${index}`}
              label={t('День')}
              value={String(row.weekday)}
              onChange={(value) => change(index, { weekday: Number(value) })}
              options={WEEKDAYS.map((label, value) => ({ value: String(value), title: t(label) }))}
            />
            <Field
              kind="time"
              name={`club-starts-${index}`}
              label={t('Начало')}
              value={row.starts}
              onChange={(value) => change(index, { starts: value })}
            />
            <Field
              kind="time"
              name={`club-ends-${index}`}
              label={t('Конец')}
              value={row.ends}
              onChange={(value) => change(index, { ends: value })}
            />
            <Button
              variant="ghost"
              size="sm"
              className="sport-edit__drop"
              disabled={meetings.length === 1}
              onClick={() => setMeetings((rows) => rows.filter((_row, i) => i !== index))}
            >
              {t('Убрать')}
            </Button>
          </div>
        ))}
      </div>
      <Button
        variant="outline"
        size="sm"
        onClick={() =>
          setMeetings((rows) => [
            ...rows,
            { key: `m-${Date.now()}`, weekday: ((rows[rows.length - 1]?.weekday ?? -1) + 1) % 7, starts: '15:00', ends: '18:00' },
          ])
        }
      >
        {t('Добавить день')}
      </Button>
      <span className="t-card">{t('Кому можно записываться')}</span>
      <div className="clubs-checks">
        {PARALLELS.map((grade) => (
          <Field
            key={grade}
            kind="checkbox"
            name={`club-parallel-${grade}`}
            label={t('{n} параллель', { n: grade })}
            checked={parallels.includes(grade)}
            onChange={(checked) =>
              setParallels((rows) => (checked ? [...rows, grade].sort((a, b) => a - b) : rows.filter((p) => p !== grade)))
            }
          />
        ))}
      </div>
      <span className="t-card">{t('Окно записи')}</span>
      <div className="clubs-pair">
        <Field
          kind="select"
          name="club-window"
          label={t('Запись')}
          value={until ? 'until' : 'always'}
          onChange={(value) => setUntil(value === 'until')}
          options={[
            { value: 'always', title: t('Открыта всегда') },
            { value: 'until', title: t('Открыта до даты') },
          ]}
        />
        {until && (
          <span className="sport-window__form">
            <Field kind="date" name="club-until-date" label={t('До даты')} value={date} onChange={setDate} />
            <Field kind="time" name="club-until-time" label={t('Время')} value={time} onChange={setTime} />
          </span>
        )}
      </div>
      <Field
        kind="checkbox"
        name="club-marks"
        label={t('Отметка посещения по QR')}
        checked={marks}
        onChange={setMarks}
        hint={t('пока выключена, отметки нет ни у ученика, ни у ментора, ни у куратора')}
      />
      {save.error && <ErrorNote error={save.error} />}
      <div className="acad__actions">
        <Button variant="outline" onClick={onClose}>
          {t('Отмена')}
        </Button>
        <Button
          disabled={!title.trim() || !mentorName.trim() || parallels.length === 0 || (until && !date) || save.isPending}
          onClick={() =>
            save.mutate(body, {
              onSuccess: () => {
                toast.success(club ? t('Кружок сохранён') : t('Кружок заведён'))
                onClose()
              },
            })
          }
        >
          {club ? t('Сохранить') : t('Завести')}
        </Button>
      </div>
    </Modal>
  )
}
