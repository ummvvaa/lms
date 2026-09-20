/**
 * Куратор вносит данные ученика напрямую — по своим группам, без очереди.
 *
 * Рядом с путём «ученик вносит — куратор подтверждает» стоит второй:
 * куратор вносит сам, и значение сразу настоящее. Всё, что ученик может
 * внести о себе, — попытки, цели, достижения, спорт, вузы, документы.
 *
 * Формы здесь не свои: та же секция строк и та же форма, которыми директор
 * ведёт свой домен в карточке (`RowsSection`, `RowForm`). Право не
 * вычисляется — приходит с сервера картой `enters` из реестра доменов:
 * какие поля куратор пишет и может ли убрать запись. Владелец домена
 * остаётся владельцем — его имя стоит в подписи каждой секции.
 */
import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import {
  useActivityRows,
  useAttemptRows,
  useCompetitionRows,
  useCuratorUniversities,
  useDirectory,
  useDirectoryEntries,
  useDocuments,
  useExamGoalRows,
  useExamGoals,
  useProgramsOf,
  useSportProfile,
  useStudentRows,
  type CuratorCard as Card,
  type DocumentCell,
} from '../../api/hooks'
import RowForm, { type FieldDef, type RowValues } from '../../components/RowForm'
import { SelectField } from '../../components/SelectField'
import { ACTIVITY_CATEGORY, EXAM_TYPES, RowsSection, TIER_OPTIONS } from '../../components/StudentRows'
import { RowMenuItem } from '../../components/RowMenu'
import Modal from '../../components/Modal'
import { DataCard, ErrorNote, Loading } from '../../components/ui'
import { Badge } from '../../components/ui/badge'
import { Button } from '../../components/ui/button'
import { Input } from '../../components/ui/input'
import { t } from '../../i18n'

const SPORT_LEVELS = [
  { value: 'school', title: 'Школьный' },
  { value: 'city', title: 'Городской' },
  { value: 'regional', title: 'Областной' },
  { value: 'national', title: 'Республиканский' },
  { value: 'international', title: 'Международный' },
]

const IELTS_SECTIONS = ['listening', 'reading', 'writing', 'speaking'] as const

const dateOf = (value: string | null | undefined) => (value ? new Date(value).toLocaleDateString('ru') : '')
const text = (value: RowValues[string] | undefined) =>
  value === null || value === undefined ? '' : String(value)
const numberOrNull = (value: RowValues[string] | undefined) => (text(value) === '' ? null : Number(value))
const byCurator = (row: { entered_by_curator?: string[] }) => (row.entered_by_curator ?? []).length > 0

/** Подпись секции: куратор пишет, владелец владеет. */
const ownerNote = (card: Card, model: string) => `${t('ведёт:')} ${card.enters[model]?.owner ?? ''}`

function useRefreshCard(studentId: number) {
  const queryClient = useQueryClient()
  return () => {
    void queryClient.invalidateQueries({ queryKey: ['curator-card', studentId] })
    void queryClient.invalidateQueries({ queryKey: ['exam-goals'] })
  }
}

/** Вкладка «Экзамены»: официальные попытки и цели с датами. */
export function ExamsEntry({ card }: { card: Card }) {
  const rows = useStudentRows(card.id)
  const goals = useExamGoals(card.id)
  const kinds = useDirectoryEntries('exam-kinds')
  const attempts = useAttemptRows()
  const goalRows = useExamGoalRows()
  const refresh = useRefreshCard(card.id)

  const mayAttempt = Boolean(card.enters['students.ExamAttempt'])
  const mayGoal = Boolean(card.enters['students.ExamGoal'])
  if (!mayAttempt && !mayGoal) return null
  if (rows.isLoading || goals.isLoading) return <Loading kind="table" />
  if (rows.isError) return <ErrorNote error={rows.error} />

  const attemptFields: FieldDef[] = [
    { name: 'exam_type', label: 'Экзамен', kind: 'select', options: EXAM_TYPES, required: true },
    { name: 'date', label: 'Дата сдачи', kind: 'date', required: true },
    { name: 'total_score', label: 'Общий балл', kind: 'number', required: true },
    ...IELTS_SECTIONS.map((name): FieldDef => ({
      name,
      label: `${name[0].toUpperCase()}${name.slice(1)} — ${t('секция IELTS')}`,
      kind: 'number',
    })),
  ]
  const attemptBody = (values: RowValues) => ({
    exam_type: text(values.exam_type),
    date: text(values.date),
    total_score: numberOrNull(values.total_score),
    ...Object.fromEntries(IELTS_SECTIONS.map((name) => [name, numberOrNull(values[name])])),
  })

  const examOptions = (kinds.data?.results ?? [])
    .filter((row) => row.is_active)
    .map((row) => ({ value: String(row.id), title: row.name }))
  const goalFields: FieldDef[] = [
    { name: 'exam', label: 'Экзамен', kind: 'select', options: examOptions, required: true },
    { name: 'target_score', label: 'Целевой балл', kind: 'number' },
    { name: 'exam_date', label: 'Дата экзамена', kind: 'date' },
    { name: 'registration_date', label: 'Дата регистрации', kind: 'date' },
    { name: 'note', label: 'Примечание', kind: 'text' },
  ]
  const goalBody = (values: RowValues) => ({
    exam: Number(values.exam),
    target_score: numberOrNull(values.target_score),
    exam_date: text(values.exam_date) || null,
    registration_date: text(values.registration_date) || null,
    note: text(values.note),
  })
  const done = { onSuccess: refresh, onError: (e: Error) => toast.error(e.message) }

  return (
    <>
      {mayAttempt && (
        <RowsSection
          title={t('Официальные попытки')}
          note={ownerNote(card, 'students.ExamAttempt')}
          hint={t(
            'Балл с сертификата: дата и секции. Значение сразу настоящее — очереди нет. Пробники вносятся файлом на экране «Пробники», руками здесь не правятся.',
          )}
          model="students.ExamAttempt"
          path="/attempts/"
          role="curator"
          mayWrite
          mayRemove={card.enters['students.ExamAttempt'].remove}
          invalidate={[['curator-card', String(card.id)]]}
          empty={t('Официальных попыток пока нет')}
          fields={attemptFields}
          addLabel={t('Внести балл')}
          busy={attempts.create.isPending || attempts.update.isPending}
          onCreate={(values) =>
            attempts.create.mutate(
              { student: card.id, attempt_format: 'official', ...attemptBody(values) },
              done,
            )
          }
          onUpdate={(id, values) => attempts.update.mutate({ id, ...attemptBody(values) }, done)}
          rows={(rows.data?.attempts ?? []).map((row) => ({
            id: row.id,
            label: `${row.exam_type} ${row.total_score ?? '—'}`,
            note: `${dateOf(row.date)} · ${row.is_mock ? t('пробный') : t('официальный')}`,
            byCurator: byCurator(row),
            locked: row.is_mock,
            values: {
              exam_type: row.exam_type,
              date: row.date,
              total_score: row.total_score ?? '',
              ...Object.fromEntries(IELTS_SECTIONS.map((name) => [name, row[name] ?? ''])),
            },
          }))}
        />
      )}

      {mayGoal && (
        <RowsSection
          title={t('Цели и даты экзаменов')}
          note={ownerNote(card, 'students.ExamGoal')}
          model="students.ExamGoal"
          path="/exam-goals/"
          role="curator"
          mayWrite
          mayRemove={card.enters['students.ExamGoal'].remove}
          invalidate={[['exam-goals'], ['curator-card', String(card.id)]]}
          empty={t('Целей пока нет')}
          fields={goalFields}
          addLabel={t('Поставить цель')}
          busy={goalRows.create.isPending || goalRows.update.isPending}
          onCreate={(values) => goalRows.create.mutate({ student: card.id, ...goalBody(values) }, done)}
          onUpdate={(id, values) => goalRows.update.mutate({ id, ...goalBody(values) }, done)}
          rows={(goals.data?.results ?? []).map((row) => ({
            id: row.id,
            label: `${row.exam_name}: ${row.target_score ?? t('цель не поставлена')}`,
            note: row.exam_date
              ? `${t('экзамен')} ${dateOf(row.exam_date)}`
              : t('дата экзамена не назначена'),
            byCurator: byCurator(row),
            values: {
              exam: String(row.exam),
              target_score: row.target_score ?? '',
              exam_date: row.exam_date ?? '',
              registration_date: row.registration_date ?? '',
              note: row.note,
            },
          }))}
        />
      )}
    </>
  )
}

/** Вкладка «Вузы»: добавить из каталога, категория, приоритетный, убрать. */
export function UniversitiesEntry({ card }: { card: Card }) {
  const rows = useStudentRows(card.id)
  const list = useCuratorUniversities(card.id)
  const universities = useDirectory()
  const [university, setUniversity] = useState<number | null>(null)
  const programs = useProgramsOf(university)
  const entry = card.enters['universities.StudentUniversity']
  if (!entry) return null
  if (rows.isLoading) return <Loading kind="table" />
  if (rows.isError) return <ErrorNote error={rows.error} />

  const programOptions = (programs.data?.results ?? []).map((row) => ({
    value: String(row.id),
    title: `${row.university_name} — ${row.name}`,
  }))
  const fields: FieldDef[] = [
    { name: 'program', label: 'Программа', kind: 'select', options: programOptions, required: true },
    { name: 'tier', label: 'Категория', kind: 'select', options: TIER_OPTIONS, required: true },
  ]
  const tierOnly: FieldDef[] = [fields[1]]
  const failed = { onError: (e: Error) => toast.error(e.message) }
  const tierTitle = (code: string) => TIER_OPTIONS.find((row) => row.value === code)?.title ?? code

  return (
    <>
      <label className="rows__picker">
        <span className="rowform__label">{t('Каталог: сначала выберите вуз')}</span>
        <SelectField
          value={university === null ? '' : String(university)}
          onChange={(event) => setUniversity(event.target.value ? Number(event.target.value) : null)}
        >
          <option value="">{t('— вуз не выбран —')}</option>
          {(universities.data?.results ?? []).map((row) => (
            <option key={row.id} value={row.id}>
              {row.name}
            </option>
          ))}
        </SelectField>
      </label>
      <RowsSection
        title={t('Список вузов')}
        note={ownerNote(card, 'universities.StudentUniversity')}
        hint={t(
          'Программы, которые добавил ученик или вы, можно менять и убирать. Строку, которую завела Асем, снимает она.',
        )}
        model="universities.StudentUniversity"
        path="/student-universities/"
        role="curator"
        mayWrite
        mayRemove={entry.remove}
        invalidate={[['curator-card', String(card.id)]]}
        empty={t('Вузов в списке пока нет')}
        fields={university === null ? tierOnly : fields}
        addLabel={t('Добавить из каталога')}
        busy={list.add.isPending || list.tier.isPending}
        onCreate={(values) => {
          if (!values.program) {
            toast.error(t('Сначала выберите вуз и программу'))
            return
          }
          list.add.mutate({ program: Number(values.program), tier: text(values.tier) }, failed)
        }}
        onUpdate={(id, values) => list.tier.mutate({ id, tier: text(values.tier) }, failed)}
        extraActions={(row) => (
          <RowMenuItem onClick={() => list.priority.mutate(row.id, failed)}>
            {t('Сделать приоритетным')}
          </RowMenuItem>
        )}
        rows={(rows.data?.universities ?? []).map((row) => ({
          id: row.id,
          label: `${row.university_name} — ${row.program_name}`,
          note: [row.is_priority ? t('приоритетный') : '', tierTitle(row.tier)].filter(Boolean).join(' · '),
          byCurator: byCurator(row),
          // решение директора по поступлению отменяет он сам
          locked: row.added_by !== 'student',
          values: { tier: row.tier },
        }))}
      />
    </>
  )
}

/** Вкладка «Портфолио»: достижения и олимпиады, профиль спорта, соревнования. */
export function PortfolioEntry({ card }: { card: Card }) {
  const rows = useStudentRows(card.id)
  const subjects = useDirectoryEntries('subjects')
  const sportTypes = useDirectoryEntries('sport-types')
  const activities = useActivityRows()
  const competitions = useCompetitionRows()
  const sport = useSportProfile(card.id)
  const [editingSport, setEditingSport] = useState(false)
  const refresh = useRefreshCard(card.id)

  if (rows.isLoading) return <Loading kind="table" />
  if (rows.isError) return <ErrorNote error={rows.error} />

  const options = (source: typeof subjects) =>
    (source.data?.results ?? [])
      .filter((row) => row.is_active)
      .map((row) => ({ value: String(row.id), title: row.name }))
  const done = { onSuccess: refresh, onError: (e: Error) => toast.error(e.message) }

  const activityFields: FieldDef[] = [
    { name: 'category', label: 'Категория', kind: 'select', options: ACTIVITY_CATEGORY, required: true },
    { name: 'title', label: 'Название', kind: 'text', required: true },
    { name: 'subject', label: 'Предмет олимпиады', kind: 'select', options: options(subjects) },
    { name: 'date', label: 'Дата', kind: 'date' },
    { name: 'description', label: 'Описание', kind: 'textarea' },
    { name: 'proof_url', label: 'Ссылка на подтверждение', kind: 'text' },
  ]
  const activityBody = (values: RowValues) => ({
    category: text(values.category),
    title: text(values.title),
    subject: values.subject ? Number(values.subject) : null,
    date: text(values.date) || null,
    description: text(values.description),
    proof_url: text(values.proof_url),
  })

  const competitionFields: FieldDef[] = [
    { name: 'name', label: 'Соревнование', kind: 'text', required: true },
    { name: 'sport_type', label: 'Вид спорта', kind: 'select', options: options(sportTypes) },
    { name: 'level', label: 'Уровень', kind: 'select', options: SPORT_LEVELS },
    { name: 'date', label: 'Дата', kind: 'date' },
    { name: 'result', label: 'Результат', kind: 'text' },
    { name: 'has_certificate', label: 'Есть сертификат', kind: 'checkbox' },
  ]
  const competitionBody = (values: RowValues) => ({
    name: text(values.name),
    sport_type: values.sport_type ? Number(values.sport_type) : null,
    level: text(values.level),
    date: text(values.date) || null,
    result: text(values.result),
    has_certificate: Boolean(values.has_certificate),
  })

  const sportFields: FieldDef[] = [
    { name: 'sport_type', label: 'Вид спорта', kind: 'select', options: options(sportTypes) },
    { name: 'level', label: 'Уровень занятий', kind: 'select', options: SPORT_LEVELS },
    { name: 'rank', label: 'Спортивный разряд', kind: 'text' },
    { name: 'leadership_role', label: 'Лидерская роль в команде', kind: 'text' },
  ]
  const profile = sport.query.data
  const sportName = options(sportTypes).find((row) => row.value === String(profile?.sport_type ?? ''))?.title

  return (
    <>
      {card.enters['students.Activity'] && (
        <RowsSection
          title={t('Достижения и олимпиады')}
          note={ownerNote(card, 'students.Activity')}
          model="students.Activity"
          path="/activities/"
          role="curator"
          mayWrite
          mayRemove={card.enters['students.Activity'].remove}
          invalidate={[['curator-card', String(card.id)]]}
          empty={t('Активностей пока нет')}
          fields={activityFields}
          addLabel={t('Добавить')}
          busy={activities.create.isPending || activities.update.isPending}
          onCreate={(values) => activities.create.mutate({ student: card.id, ...activityBody(values) }, done)}
          onUpdate={(id, values) => activities.update.mutate({ id, ...activityBody(values) }, done)}
          rows={(rows.data?.activities ?? []).map((row) => ({
            id: row.id,
            label: row.title,
            note: [row.subject_name, dateOf(row.date)].filter(Boolean).join(' · ') || undefined,
            byCurator: byCurator(row),
            values: {
              category: row.category,
              title: row.title,
              subject: row.subject === null ? '' : String(row.subject),
              date: row.date ?? '',
              description: '',
              proof_url: '',
            },
          }))}
        />
      )}

      {card.enters['students.SportProfile'] && (
        <DataCard
          title={t('Спорт')}
          note={ownerNote(card, 'students.SportProfile')}
          right={
            <Button variant="outline" size="sm" onClick={() => setEditingSport(!editingSport)}>
              {editingSport ? t('Отмена') : t('Изменить')}
            </Button>
          }
        >
          {!editingSport && (
            <dl className="ckv">
              <dt>{t('Вид спорта')}</dt>
              <dd>{sportName ?? '—'}</dd>
              <dt>{t('Уровень занятий')}</dt>
              <dd>{SPORT_LEVELS.find((row) => row.value === profile?.level)?.title ?? '—'}</dd>
              <dt>{t('Спортивный разряд')}</dt>
              <dd>{profile?.rank || '—'}</dd>
              <dt>{t('Лидерская роль в команде')}</dt>
              <dd>{profile?.leadership_role || '—'}</dd>
            </dl>
          )}
          {!editingSport && profile && byCurator(profile) && (
            <Badge variant="mute">{t('внёс куратор')}</Badge>
          )}
          {editingSport && (
            <RowForm
              fields={sportFields}
              row={{
                sport_type: profile?.sport_type ? String(profile.sport_type) : '',
                level: profile?.level ?? '',
                rank: profile?.rank ?? '',
                leadership_role: profile?.leadership_role ?? '',
              }}
              busy={sport.save.isPending}
              submitLabel={t('Сохранить')}
              onCancel={() => setEditingSport(false)}
              onSubmit={(values) =>
                sport.save.mutate(
                  {
                    sport_type: values.sport_type ? Number(values.sport_type) : null,
                    level: text(values.level),
                    rank: text(values.rank),
                    leadership_role: text(values.leadership_role),
                  },
                  { onSuccess: () => setEditingSport(false), onError: (e) => toast.error(e.message) },
                )
              }
            />
          )}
        </DataCard>
      )}

      {card.enters['students.Competition'] && (
        <RowsSection
          title={t('Спортивные соревнования')}
          note={ownerNote(card, 'students.Competition')}
          model="students.Competition"
          path="/competitions/"
          role="curator"
          mayWrite
          mayRemove={card.enters['students.Competition'].remove}
          invalidate={[['curator-card', String(card.id)]]}
          empty={t('Соревнований пока нет')}
          fields={competitionFields}
          addLabel={t('Добавить')}
          busy={competitions.create.isPending || competitions.update.isPending}
          onCreate={(values) =>
            competitions.create.mutate({ student: card.id, ...competitionBody(values) }, done)
          }
          onUpdate={(id, values) => competitions.update.mutate({ id, ...competitionBody(values) }, done)}
          rows={(rows.data?.competitions ?? []).map((row) => ({
            id: row.id,
            label: row.name,
            note: [row.result, dateOf(row.date)].filter(Boolean).join(' · ') || undefined,
            byCurator: byCurator(row),
            values: {
              name: row.name,
              sport_type: '',
              level: '',
              date: row.date ?? '',
              result: row.result,
              has_certificate: false,
            },
          }))}
        />
      )}
    </>
  )
}

/** Типы документов со сроком действия — как у ученика при загрузке. */
const WITH_EXPIRY = ['passport', 'exam_certificate']

/**
 * «Загрузить» у типа документа: файл ложится сразу подтверждённым.
 * Перезагрузка оставляет прежний файл в истории; удалить документ куратор
 * не может. Срок действия правится отдельно, без нового файла.
 */
export function DocumentEntry({
  card,
  cell,
  onClose,
}: {
  card: Card
  cell: DocumentCell
  onClose: () => void
}) {
  const documents = useDocuments(card.id)
  const refresh = useRefreshCard(card.id)
  const [file, setFile] = useState<File | null>(null)
  const [expires, setExpires] = useState(cell.expires_at ?? '')
  const needsExpiry = WITH_EXPIRY.includes(cell.code)
  const busy = documents.uploadDocument.isPending || documents.editDocument.isPending
  const finish = {
    onSuccess: () => {
      refresh()
      onClose()
    },
    onError: (e: Error) => toast.error(e.message),
  }

  return (
    <Modal title={`${t(cell.title ?? cell.code)} — ${card.full_name}`} onClose={onClose}>
      <p className="muted">
        {t(
          'Документ, который загружаете вы, сразу считается подтверждённым. Прежний файл остаётся в истории загрузок.',
        )}
      </p>
      <label className="rowform__field">
        <span className="rowform__label">{t('Файл')}</span>
        <Input
          type="file"
          aria-label={t('Файл документа')}
          onChange={(event) => setFile(event.target.files?.[0] ?? null)}
        />
      </label>
      {needsExpiry && (
        <label className="rowform__field">
          <span className="rowform__label">{t('Действует до')}</span>
          <Input type="date" value={expires} onChange={(event) => setExpires(event.target.value)} />
        </label>
      )}
      <div className="rowform__actions">
        <Button variant="outline" size="sm" onClick={onClose}>
          {t('Отмена')}
        </Button>
        {needsExpiry && cell.document && (
          <Button
            variant="outline"
            size="sm"
            disabled={busy || expires === (cell.expires_at ?? '')}
            onClick={() =>
              documents.editDocument.mutate(
                { id: cell.document as number, expires_at: expires || null },
                finish,
              )
            }
          >
            {t('Сохранить срок')}
          </Button>
        )}
        <Button
          size="sm"
          disabled={busy || file === null}
          onClick={() =>
            file &&
            documents.uploadDocument.mutate(
              { file, doc_type: cell.code, expires_at: needsExpiry && expires ? expires : undefined },
              finish,
            )
          }
        >
          {t('Загрузить')}
        </Button>
      </div>
    </Modal>
  )
}
