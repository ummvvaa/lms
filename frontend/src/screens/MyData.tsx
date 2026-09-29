/**
 * «Портфолио» — ученик рассказывает о себе, школа подтверждает (фаза 38).
 *
 * Обзор: процент заполнения (это «сколько вы о себе рассказали», а не
 * готовность к подаче), следующие шаги, профиль поступления и академические
 * результаты — плюс всё, что школа записала (инвариант №7: видно всё,
 * кроме трёх оценочных ярлыков, которых API ученику не отдаёт).
 *
 * Достижения, спорт и олимпиады вносит ученик — предложением владельцу
 * домена (фаза 37). Документы загружаются напрямую: это документы человека,
 * а не табличные данные, файл живёт вне корня веб-сервера.
 */
import { useMemo, useState } from 'react'
import { toast } from 'sonner'
import {
  useAtGoal,
  useAttempts,
  useContacts,
  useCredentials,
  useExamGoals,
  useMyProfile,
  useMyProposals,
  useMyUniversities,
  usePortfolio,
  usePropose,
  useRevealCredential,
  useSetCredential,
  useStudentRows,
  type Attempt,
  type MyProposal,
  type ProposeRow,
} from '../api/hooks'
import { useAuth } from '../auth/AuthContext'
import MyDocuments, { UploadForm } from './MyDocuments'
import BadgesBlock from '../components/BadgesBlock'
import { useDomainMeta } from '../api/hooks'
import {
  profileModelOf,
  type Domain,
  type DomainMeta,
} from '../api/types'
import { Chip, DataCard, EmptyNote, ErrorNote, Loading, ScreenHead, ScreenTabs } from '../components/ui'
import { Row, Rows } from '../components/patterns'
import { AddRowForm, ByCurator, ProfileCard, ProposeForm, RowsList } from '../components/PortfolioForms'
import { modelOf, pendingByField, pendingNewRows } from './portfolioData'
import Icon from '../layout/icons'
import './portfolio.css'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'
import { t } from '../i18n'

type Tab = 'overview' | 'achievements' | 'documents' | 'sport' | 'olympiads' | 'cv'

/**
 * Цели по экзаменам (фаза 39): таблица «экзамен · цель · даты · сохранить».
 *
 * Строка на экзамен из справочника. Сохранение уходит предложением
 * академическому директору; от дат растут календарь и напоминания.
 */
function GoalsCard({ meta, proposals }: { meta: DomainMeta | undefined; proposals: MyProposal[] }) {
  const goals = useExamGoals()
  const atGoal = useAtGoal()
  const propose = usePropose()
  const [draft, setDraft] = useState<Record<string, Record<string, string>>>({})

  const model = modelOf(meta, 'students.ExamGoal')
  const exams = model?.fields.find((f) => f.name === 'exam')?.choices ?? []
  const rows = goals.data?.results ?? []

  // отправленное и нерешённое: новые цели по имени экзамена, правки — по записи
  const pendingNew = new Map<string, Record<string, string>>()
  const pendingEdits = new Map<string, Record<string, string>>()
  for (const proposal of proposals) {
    if (proposal.status !== 'pending') continue
    for (const change of proposal.changes) {
      if (change.model !== 'students.ExamGoal') continue
      if (change.new_object_key) {
        const key = `${proposal.id}:${change.new_object_key}`
        pendingNew.set(key, { ...pendingNew.get(key), [change.field]: change.new_value })
      } else if (change.object_id) {
        pendingEdits.set(change.object_id, {
          ...pendingEdits.get(change.object_id),
          [change.field]: change.new_value,
        })
      }
    }
  }
  const pendingByExam = new Map<string, Record<string, string>>()
  for (const fields of pendingNew.values()) {
    if (fields.exam) pendingByExam.set(fields.exam, fields)
  }

  const save = (examName: string) => {
    const values = draft[examName]
    // Кнопка не выключается: выключенная выглядит сломанной, и человек
    // не понимает, чего от него хотят. Пустую строку она объясняет словами
    if (!values || Object.values(values).every((v) => v === '')) {
      toast.error(t('Укажите балл или дату — тогда будет что отправить'))
      return
    }
    const existing = rows.find((row) => row.exam_name === examName)
    const rowsToSend: ProposeRow[] = Object.entries(values)
      .filter(([, value]) => value !== '')
      .map(([field, value]) =>
        existing
          ? { model: 'students.ExamGoal', field, value, object_id: String(existing.id) }
          : { model: 'students.ExamGoal', field, value, new_object_key: `goal-${examName}` },
      )
    if (!existing)
      rowsToSend.push({
        model: 'students.ExamGoal',
        field: 'exam',
        value: examName,
        new_object_key: `goal-${examName}`,
      })
    propose.mutate(rowsToSend, {
      onSuccess: (result) => {
        if (result.accepted > 0) toast.success(t('Отправлено на проверку'))
        result.rejected.forEach((row) => toast.error(row.reason))
        setDraft((prev) => ({ ...prev, [examName]: {} }))
      },
    })
  }

  return (
    <DataCard
      title={t('Цели по экзаменам')}
    >
      {exams.map((exam) => {
        const existing = rows.find((row) => row.exam_name === exam.value)
        const waiting = pendingByExam.get(exam.value) ?? (existing && pendingEdits.get(String(existing.id)))
        const rowDraft = draft[exam.value] ?? {}
        const valueOf = (field: string, current: string | null) =>
          rowDraft[field] ?? waiting?.[field] ?? current ?? ''
        return (
          <div key={exam.value} className="goals__row" data-exam={exam.value}>
            <span className="goals__exam">
              {exam.title}
              {waiting && <Chip tone="neutral">{t('ждёт проверки')}</Chip>}
            </span>
            <Input
              className="num goals__score"
              placeholder={t('Цель')}
              aria-label={`${t('Целевой балл')}: ${exam.title}`}
              value={valueOf('target_score', existing?.target_score ?? null)}
              onChange={(e) =>
                setDraft((prev) => ({ ...prev, [exam.value]: { ...rowDraft, target_score: e.target.value } }))
              }
            />
            <Input
              type="date"
              aria-label={`${t('Дата экзамена')}: ${exam.title}`}
              value={valueOf('exam_date', existing?.exam_date ?? null)}
              onChange={(e) =>
                setDraft((prev) => ({ ...prev, [exam.value]: { ...rowDraft, exam_date: e.target.value } }))
              }
            />
            <Input
              type="date"
              aria-label={`${t('Дата регистрации')}: ${exam.title}`}
              value={valueOf('registration_date', existing?.registration_date ?? null)}
              onChange={(e) =>
                setDraft((prev) => ({
                  ...prev,
                  [exam.value]: { ...rowDraft, registration_date: e.target.value },
                }))
              }
            />
            <Button className="goals__save" disabled={propose.isPending} onClick={() => save(exam.value)}>
              {t('Сохранить')}
            </Button>
          </div>
        )
      })}
      {atGoal.data?.available && atGoal.data.open_after > atGoal.data.open_before && (
        <p className="muted propose__note mt-3">
          {t('Если сдадите на цель, по требованиям откроется программ:')}{' '}
          <b className="num">{atGoal.data.open_after}</b> (+{atGoal.data.open_after - atGoal.data.open_before}
          ). {t('Это соответствие требованиям, а не шанс поступления.')}
        </p>
      )}
    </DataCard>
  )
}

/** Секции попытки строкой «L 6.5 · R 7.0 · W 6.0 · S 6.5» — пусто у не-IELTS. */
function sectionsOf(row: Attempt): string {
  return (['listening', 'reading', 'writing', 'speaking'] as const)
    .map((name) => (row[name] === null ? '' : `${name[0].toUpperCase()} ${row[name]}`))
    .filter(Boolean)
    .join(' · ')
}

type ChecklistRow = {
  code: string
  title: string
  done: boolean
  state: 'none' | 'pending' | 'confirmed' | 'rejected' | 'expiring'
  state_title: string
  reject_reason: string
  /** документ задан ссылкой на файл вне системы (фаза 65) */
  is_link?: boolean
  external_url?: string
  document?: number | null
  /** документ загрузил куратор за ученика */
  entered_by_curator?: boolean
}

/** Подпись статуса проверки для ученика (фаза 62): имени проверившего здесь нет. */
function DocumentState({ row }: { row: ChecklistRow }) {
  // документ-ссылка (фаза 65): файла у нас нет, есть адрес — по нему
  // ученик и проверит, что школа записала именно его документ
  const link = row.is_link ? (
    <a
      className="portfolio__link"
      href={`/api/documents/${row.document}/file/`}
      target="_blank"
      rel="noreferrer"
    >
      {t('ссылка')}
    </a>
  ) : null
  if (row.state === 'confirmed' || row.state === 'expiring')
    return (
      <>
        {link}
        {row.entered_by_curator && <ByCurator />}
        <Chip tone="good">{t('Подтверждён')}</Chip>
      </>
    )
  if (row.state === 'pending')
    return (
      <>
        {link}
        <Chip tone="warn">{t('Ждёт проверки')}</Chip>
      </>
    )
  if (row.state === 'rejected') return <Chip tone="bad">{t('Отклонён')}</Chip>
  return link
}

function DocumentsCard({ checklist }: { checklist: ChecklistRow[] }) {
  const done = checklist.filter((row) => row.done).length
  // «Загрузить» открывает то же окно, что вкладка документов: тип уже
  // выбран строкой. Системного поля выбора файла в строке нет — оно
  // сжимало название до столбика букв (замечание владельца, 27.09.2026)
  const [uploading, setUploading] = useState<{ code: string; title: string } | null>(null)

  return (
    <DataCard
      title={t('Готовность документов')}
      right={<Chip tone="good" className="num">{`${done} ${t('из')} ${checklist.length}`}</Chip>}
    >
      <Rows>
        {checklist.map((row) => (
          <Row
            key={row.code}
            lead={
              <span
                className={`portfolio__check${row.done ? ' portfolio__check--on' : ''}`}
                aria-hidden="true"
              >
                {row.done ? <Icon name="check" size={11} /> : null}
              </span>
            }
            title={t(row.title)}
            note={row.state === 'rejected' ? `${t('Причина:')} ${row.reject_reason}` : undefined}
            right={row.done ? <DocumentState row={row} /> : <Chip tone={row.state === 'rejected' ? 'bad' : 'neutral'}>{t(row.state_title || 'Не загружен')}</Chip>}
            acts={
              !row.done ? (
                <Button size="sm" variant={row.state === 'rejected' ? 'outline' : 'default'} onClick={() => setUploading({ code: row.code, title: t(row.title) })}>
                  {row.state === 'rejected' ? t('Загрузить заново') : t('Загрузить')}
                </Button>
              ) : undefined
            }
          />
        ))}
      </Rows>
      {uploading && <UploadForm docType={uploading.code} title={uploading.title} onClose={() => setUploading(null)} />}
    </DataCard>
  )
}

/** Вкладка «Документы»: одна карточка по типам — `MyDocuments`. */
function DocumentsTab() {
  return <MyDocuments />
}

/**
 * Свои пароли от почты и Common App (фаза 65).
 *
 * Школа хранит их зашифрованными, чтобы помочь с подачей документов.
 * Ученик — хозяин своих: видит, что записано, показывает по кнопке
 * и меняет сам, без очереди. Показ пишется в журнал так же, как у
 * сотрудников: журнал здесь не про недоверие, а про то, чтобы любой
 * доступ к паролю был виден.
 */
function MyCredentialsCard({ studentId }: { studentId: number }) {
  const state = useCredentials(studentId)
  const reveal = useRevealCredential(studentId)
  const save = useSetCredential(studentId)
  const [shown, setShown] = useState<Record<string, string>>({})
  const [editing, setEditing] = useState<string>('')
  const [draft, setDraft] = useState('')

  if (state.isLoading || !state.data) return null

  return (
    <DataCard
      title={t('Мои пароли')}
    >
      <Rows>
        {state.data.rows.map((row) => (
          <Row
            key={row.kind}
            title={t(row.title)}
            note={row.present ? (shown[row.kind] ?? state.data.mask) : t('не записан')}
            right={
              editing === row.kind ? (
                <span className="filepick filepick--row">
                  <Input
                    value={draft}
                    aria-label={t(row.title)}
                    onChange={(event) => setDraft(event.target.value)}
                  />
                  <Button
                    size="sm"
                    disabled={save.isPending}
                    onClick={() =>
                      save.mutate(
                        { kind: row.kind, password: draft },
                        {
                          onSuccess: () => {
                            setEditing('')
                            setDraft('')
                            setShown((old) => ({ ...old, [row.kind]: '' }))
                            toast.success(t('Пароль сохранён'))
                          },
                          onError: (error) => toast.error(error.message),
                        },
                      )
                    }
                  >
                    {t('Сохранить')}
                  </Button>
                </span>
              ) : (
                <span className="filepick filepick--row">
                  {row.present && !shown[row.kind] && (
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={reveal.isPending}
                      onClick={() =>
                        reveal.mutate(row.kind, {
                          onSuccess: (data) => setShown((old) => ({ ...old, [row.kind]: data.password })),
                          onError: (error) => toast.error(error.message),
                        })
                      }
                    >
                      {t('Показать')}
                    </Button>
                  )}
                  <Button size="sm" variant="ghost" onClick={() => setEditing(row.kind)}>
                    {row.present ? t('Изменить') : t('Записать')}
                  </Button>
                </span>
              )
            }
          />
        ))}
      </Rows>
    </DataCard>
  )
}

export default function MyData() {
  const { me } = useAuth()
  const meta = useDomainMeta()
  const profile = useMyProfile()
  const portfolio = usePortfolio()
  const attempts = useAttempts()
  const universities = useMyUniversities()
  const rows = useStudentRows(me?.student_id ?? null)
  const contacts = useContacts({ student: me?.student_id ?? null })
  const proposals = useMyProposals()
  const [tab, setTab] = useState<Tab>('overview')

  const myProposals = useMemo(() => proposals.data?.results ?? [], [proposals.data])
  const pending = useMemo(() => pendingByField(myProposals), [myProposals])

  if (meta.isLoading || profile.isLoading || portfolio.isLoading) return <Loading kind="cards" />
  if (profile.error) return <ErrorNote error={profile.error} />
  if (!profile.data) return null

  const card = profile.data as unknown as Record<string, Record<string, unknown>>
  const domains: Domain[] = meta.data?.domains ?? []
  const state = portfolio.data
  const attemptRows = attempts.data?.results ?? []
  const activities = rows.data?.activities ?? []
  const competitions = rows.data?.competitions ?? []
  const contactRows = contacts.data?.results ?? []
  const declined = myProposals.filter((p) => p.status === 'rejected' && p.reject_reason)
  // куратор внёс значение сам, пока предложение ждало: не отказ, а «внесли за вас»
  const superseded = myProposals.filter((p) => p.status === 'superseded')

  // Три числа для крупной карточки: сколько разделов начато, сколько
  // документов загружено и сколько предложений директора уже приняли
  const sections = state?.sections ?? []
  const totalSections = sections.length
  const filledSections = sections.filter((section) => section.value > 0).length
  const documentsDone = (state?.documents ?? []).filter((doc) => doc.done).length
  const confirmedCount = myProposals.filter((proposal) =>
    ['applied', 'partially_applied'].includes(proposal.status),
  ).length

  // поля академических результатов, которые ученик вправе предложить:
  // форма внесения баллов открывается прямо в карточке (фаза 49)
  const examDomain = domains.find((d) => d.code === 'exam')
  const examModel = examDomain ? profileModelOf(examDomain) : undefined
  const examProposable = (examModel?.fields ?? []).filter((f) => f.student_proposable)

  const activityModel = modelOf(meta.data, 'students.Activity')
  const competitionModel = modelOf(meta.data, 'students.Competition')

  const domainCard = (code: string) => (
    <ProfileCard key={code} code={code} domains={domains} card={card} pending={pending} />
  )


  const olympiadRows = activities.filter((a) => a.category === 'olympiad')
  const achievementRows = activities.filter((a) => a.category !== 'olympiad')
  const pendingActivities = pendingNewRows(myProposals, 'students.Activity')
  const pendingOlympiads = pendingActivities.filter((r) => r.category === 'olympiad')
  const pendingAchievements = pendingActivities.filter((r) => r.category !== 'olympiad')
  const pendingCompetitions = pendingNewRows(myProposals, 'students.Competition')

  return (
    <div>
      <ScreenHead
        title={t('Портфолио')}
        actions={
          <Button
            variant="outline"
            onClick={() => {
              window.location.href = '/api/portfolio/cv/'
            }}
          >
            {t('Экспорт CV')}
          </Button>
        }
      />

      {superseded.length > 0 && (
        <div className="card card-pad propose__declined">
          <span className="eyebrow">{t('Куратор внёс за вас')}</span>
          <ul className="propose__declinedlist">
            {superseded.slice(0, 5).map((proposal) => (
              <li key={proposal.id}>
                {proposal.changes.map((c) => (
                  <span key={`${c.model}.${c.field}`}>
                    <b>{t(c.field_title)}</b>
                    <span className="muted">
                      {' — '}
                      {t('куратор внёс значение')} {c.superseded_value || t('нет')}.{' '}
                    </span>
                  </span>
                ))}
                <span className="muted">{t('Ваше предложение закрыто, отклонения нет.')}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {declined.length > 0 && (
        <div className="card card-pad propose__declined">
          <span className="eyebrow">{t('Возвращено на доработку')}</span>
          <ul className="propose__declinedlist">
            {declined.slice(0, 5).map((proposal) => (
              <li key={proposal.id}>
                <b>{proposal.changes.map((c) => t(c.field_title)).join(', ')}</b>
                <span className="muted"> — {proposal.reject_reason}. </span>
                <span className="muted">{t('Поправьте и внесите заново в карточке ниже.')}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <ScreenTabs
        value={tab}
        onChange={setTab}
        items={[
          { value: 'overview', label: t('Обзор') },
          { value: 'achievements', label: t('Достижения') },
          { value: 'documents', label: t('Документы') },
          { value: 'sport', label: t('Спорт') },
          { value: 'olympiads', label: t('Олимпиады') },
          { value: 'cv', label: 'CV' },
        ]}
      />

      {tab === 'overview' && (
        <div className="portfolio__two">
          {/* Слева — то, что ученик вносит: баллы, цели, документы; справа —
              то, по чему он себя сверяет: заполненность, профиль поступления
              и список вузов. До фазы 49 всё это стояло одной колонкой,
              и правая половина экрана оставалась пустой */}
          <div className="portfolio__main">
            <DataCard
              title={t('Академические результаты')}
            >
              <div className="portfolio__academics">
                <div className="portfolio__score">
                  <span className="portfolio__scorelabel">GPA</span>
                  <b className="num portfolio__scorevalue">{state?.academics.gpa ?? t('нет')}</b>
                  <span className="portfolio__scorenote">{t('из 4.0')}</span>
                </div>
                <div className="portfolio__score">
                  <span className="portfolio__scorelabel">IELTS</span>
                  <b className="num portfolio__scorevalue">{state?.academics.ielts ?? t('нет')}</b>
                  <span className="portfolio__scorenote">
                    {state?.academics.ielts ? t('внесён') : t('не внесён')}
                  </span>
                </div>
                <div className="portfolio__score">
                  <span className="portfolio__scorelabel">SAT</span>
                  <b className="num portfolio__scorevalue">{state?.academics.sat ?? t('нет')}</b>
                  <span className="portfolio__scorenote">
                    {state?.academics.sat ? t('внесён') : t('не внесён')}
                  </span>
                </div>
              </div>
              {/* Форма открывается прямо здесь: до фазы 49 кнопка внесения
                  уводила на другой экран, откуда надо было возвращаться */}
              {examModel && examProposable.length > 0 && (
                <ProposeForm
                  model={examModel}
                  fields={examProposable}
                  current={card.exam}
                  pending={pending}
                  label={t('Внести баллы')}
                  certificate
                />
              )}
            </DataCard>

            <GoalsCard meta={meta.data} proposals={myProposals} />

            <DocumentsCard checklist={state?.documents ?? []} />

            <DataCard
              title={t('Достижения')}
              count={achievementRows.length + pendingAchievements.length}
              right={
                <Button variant="outline" size="sm" onClick={() => setTab('achievements')}>
                  {t('Смотреть всё')}
                </Button>
              }
            >
              {achievementRows.length + pendingAchievements.length === 0 && (
                <EmptyNote what={t('пока пусто — первое достижение вносится вами')} />
              )}
              <Rows>
                {achievementRows.slice(0, 4).map((row) => (
                  <Row
                    key={row.id}
                    icon="star"
                    tone="warn"
                    title={row.title}
                    note={[row.subject_name, row.date && new Date(row.date).toLocaleDateString('ru')]
                      .filter(Boolean)
                      .join(' · ')}
                  />
                ))}
              </Rows>
            </DataCard>

            <DataCard
              title={t('Сданные экзамены и пробные')}
              count={attemptRows.length}
            >
              {attemptRows.length === 0 && (
                <EmptyNote what={t('попыток пока нет — они появятся после первой сдачи')} />
              )}
              <Rows>
                {attemptRows.slice(0, 10).map((row) => (
                  <Row
                    key={row.id}
                    icon="target"
                    tone="info"
                    title={`${row.exam_type} ${row.total_score ?? t('без балла')}`}
                    note={[
                      new Date(row.date).toLocaleDateString('ru'),
                      // секции показываются как в бланке — по буквам (фаза 63)
                      sectionsOf(row),
                    ]
                      .filter(Boolean)
                      .join(' · ')}
                    right={
                      row.is_mock ? (
                        <Chip tone="neutral">{t('пробник школы')}</Chip>
                      ) : (
                        <Chip tone="good">{t('официальный')}</Chip>
                      )
                    }
                  />
                ))}
              </Rows>
              {attemptRows.some((row) => row.is_mock) && (
                <p className="muted rows__note">
                  {t(
                    'Пробник проводит учитель, балл вносит школа. Если результат неверный — обратись к куратору.',
                  )}
                </p>
              )}
            </DataCard>

            {domainCard('exam')}
            {domainCard('behavior')}
            {domainCard('talent')}
            {domainCard('sport')}

            <DataCard
              title={t('Контакты родителей')}
              count={contactRows.length}
            >
              {contactRows.length === 0 && <EmptyNote what={t('контактов пока не записано')} />}
              <Rows>
                {contactRows.map((row) => (
                  <Row
                    key={row.id}
                    icon="person"
                    tone="accent"
                    title={`${row.full_name}${row.is_primary ? ` · ${t('основной')}` : ''}`}
                    note={[row.relation_title, row.phone].filter(Boolean).join(' · ')}
                  />
                ))}
              </Rows>
            </DataCard>
          </div>

          <div className="portfolio__side">
            {/* Заполненность: процент, полоса и что именно заполнить.
                Это «сколько рассказал», а не готовность к подаче —
                величины разные, и путать их нельзя */}
            <DataCard
              title={`${t('Заполнено на')} ${state?.percent ?? 0}%`}
            >
              <div className="bar portfolio__fillbar">
                {/* цвет полосы задаётся явно: у `.bar > i` своего фона нет,
                    и без него заполненная часть невидима */}
                <i style={{ width: `${state?.percent ?? 0}%`, background: 'var(--accent)' }} />
              </div>
              {(state?.next_steps ?? []).length === 0 && (
                <EmptyNote what={t('всё заполнено — портфолио рассказано целиком')} />
              )}
              <Rows>
                {(state?.next_steps ?? []).map((step, index) => (
                  <Row
                    key={index}
                    title={t(step.text)}
                    right={<Chip tone="warn">{t('Нет')}</Chip>}
                    onOpen={() => setTab(step.tab as Tab)}
                    openLabel={t('Заполнить')}
                  />
                ))}
              </Rows>
              <div className="portfolio__fillfacts">
                <div>
                  <span className="eyebrow">{t('Заполнено')}</span>
                  <b className="num">
                    {filledSections} {t('из')} {totalSections}
                  </b>
                </div>
                <div>
                  <span className="eyebrow">{t('Документов')}</span>
                  <b className="num">{documentsDone}</b>
                </div>
                <div>
                  <span className="eyebrow">{t('Подтверждено')}</span>
                  <b className="num">{confirmedCount}</b>
                </div>
              </div>
            </DataCard>

            {domainCard('admission')}

            {me?.student_id && <MyCredentialsCard studentId={me.student_id} />}

            <DataCard
              title={t('Вузы в вашем списке')}
              count={universities.data?.length ?? 0}
            >
              {(universities.data?.length ?? 0) === 0 && (
                <EmptyNote what={t('список пуст — выберите программы в каталоге')} />
              )}
              <Rows>
                {(universities.data ?? []).slice(0, 10).map((row) => (
                  <Row
                    key={row.program}
                    title={row.university_name}
                    note={row.program_name}
                    right={
                      <span className="num portfolio__percent">
                        {row.percent}
                        {t('% соответствия')}
                      </span>
                    }
                  />
                ))}
              </Rows>
            </DataCard>
          </div>
        </div>
      )}

      {tab === 'achievements' && (
        <div className="grid grid--two">
          <DataCard
            title={t('Достижения')}
            count={achievementRows.length}
          >
            <RowsList
              rows={achievementRows.map((row) => ({
                id: row.id,
                label: row.title,
                byCurator: (row.entered_by_curator ?? []).length > 0,
                note: row.is_confirmed ? t('подтверждено') : t('ждёт подтверждения'),
              }))}
              pendingRows={pendingAchievements.map((row) => ({ label: row.title ?? '', note: '' }))}
              emptyText={t('Достижений пока нет — добавьте первое')}
            />
            {activityModel && (
              <AddRowForm
                model="students.Activity"
                fields={activityModel.fields.filter(
                  (f) => f.student_proposable && !['subject', 'proof_url'].includes(f.name),
                )}
                submitLabel={t('Добавить достижение')}
                withFile
              />
            )}
          </DataCard>
          {/* бейджи школы — рядом, но своим именем: два блока «Достижения»
              на одном экране путают (фаза 46) */}
          <BadgesBlock limit={4} />
        </div>
      )}

      {tab === 'sport' && (
        <div className="grid grid--two">
          {domainCard('sport')}
          <DataCard
            title={t('Спортивные соревнования')}
            count={competitions.length}
          >
            <RowsList
              rows={competitions.map((row) => ({
                id: row.id,
                label: row.name,
                note: row.result || '',
                byCurator: (row.entered_by_curator ?? []).length > 0,
              }))}
              pendingRows={pendingCompetitions.map((row) => ({
                label: row.name ?? '',
                note: row.result ?? '',
              }))}
              emptyText={t('Соревнований пока нет')}
            />
            {competitionModel && (
              <AddRowForm
                model="students.Competition"
                fields={competitionModel.fields.filter((f) => f.student_proposable && f.name !== 'proof_url')}
                submitLabel={t('Добавить соревнование')}
                withFile
              />
            )}
          </DataCard>
        </div>
      )}

      {tab === 'olympiads' && (
        <div className="grid grid--two">
          <DataCard
            title={t('Олимпиады')}
            count={olympiadRows.length}
          >
            <RowsList
              rows={olympiadRows.map((row) => ({
                id: row.id,
                label: row.title,
                note: [row.subject_name, row.is_confirmed ? t('подтверждено') : t('ждёт подтверждения')]
                  .filter(Boolean)
                  .join(' · '),
              }))}
              pendingRows={pendingOlympiads.map((row) => ({
                label: row.title ?? '',
                note: row.subject ?? '',
              }))}
              emptyText={t('Олимпиад пока нет — даже школьный этап считается')}
            />
            {activityModel && (
              <AddRowForm
                model="students.Activity"
                fields={activityModel.fields.filter(
                  (f) => f.student_proposable && !['category', 'proof_url'].includes(f.name),
                )}
                fixed={{ category: 'olympiad' }}
                submitLabel={t('Добавить олимпиаду')}
                withFile
              />
            )}
          </DataCard>
        </div>
      )}

      {tab === 'documents' && <DocumentsTab />}

      {/* CV собирается на сервере из портфолио и на нём не хранится:
          профиль меняется каждый день, копия резюме устаревала бы молча */}
      {tab === 'cv' && (
        <div className="portfolio__col">
          <DataCard
            title={t('CV собирается из портфолио')}
            right={
              <Button
                size="sm"
                onClick={() => {
                  window.location.href = '/api/portfolio/cv/'
                }}
              >
                {t('Открыть CV')}
              </Button>
            }
          />
          <DataCard title={t('Что попадёт в CV')}>
            <Rows>
              {sections.map((section) => (
                <Row
                  key={section.code}
                  icon="checklist"
                  tone={section.value > 0 ? 'good' : 'neutral'}
                  title={t(section.title)}
                  right={<span className="num portfolio__percent">{section.value}%</span>}
                />
              ))}
            </Rows>
          </DataCard>
        </div>
      )}
    </div>
  )
}
