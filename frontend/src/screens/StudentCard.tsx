/**
 * Карточка ученика: пять доменов на одной странице.
 * Свой домен редактируется, чужие показаны с подписью «ведёт: <имя>».
 */
import { useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import {
  useBatchSave,
  useDomainMeta,
  useStudent,
  useStudentHistory,
  type StudentCard as Card,
} from '../api/hooks'
import { profileModelOf, type Domain, type DomainField } from '../api/types'
import { useAuth } from '../auth/AuthContext'
import BuildReportDialog from '../components/BuildReportDialog'
import { REPORT_ROLES } from '../layout/nav'
import CuratorCard from './curator/Card'
import CuratorNotesBlock from '../components/CuratorNotesBlock'
import DeleteButton from '../components/DeleteButton'
import StudentRegistryCard from '../components/StudentRegistryCard'
import PasswordLinkButton from '../components/PasswordLinkButton'
import AdmissionBlock from '../components/AdmissionBlock'
import GradesTab from './academics/GradesTab'
import DataTable from '../components/DataTable'
import { Chip, DataCard, ErrorNote, Hint, Loading, Ring, ScreenTabs } from '../components/ui'
import { Input } from '../components/ui/input'
import './card.css'
import { t } from '../i18n'
import { PublishStudents } from '../assistant/context'
import { Button } from '../components/ui/button'

/** Сырое значение поля — то же, что сервер увидит в базе.
 *
 * У ссылки на справочник это название записи, а не её ключ: сервер и в
 * журнале, и в сверке `expected` работает с названием (фаза 18).
 */
function raw(student: Card, domain: Domain, field: DomainField): string {
  const profile = (student as unknown as Record<string, Record<string, unknown>>)[domain.code]
  if (field.type === 'reference') return String(profile?.[`${field.name}_name`] ?? '')
  const value = profile?.[field.name]
  if (value === null || value === undefined) return ''
  if (typeof value === 'boolean') return value ? 'да' : 'нет'
  return String(value)
}

function shown(student: Card, domain: Domain, field: DomainField): string {
  const profile = (student as unknown as Record<string, Record<string, unknown>>)[domain.code]
  if (field.type === 'reference') return String(profile?.[`${field.name}_name`] || t('нет'))
  const raw = profile?.[field.name]
  // пустое значение — слово, не прочерк (правило вида)
  if (raw === null || raw === undefined || raw === '') return t('нет')
  if (typeof raw === 'boolean') return raw ? 'да' : 'нет'
  const choice = field.choices?.find((c) => c.value === raw)
  return choice ? choice.title : String(raw)
}

type HistoryEntry = NonNullable<ReturnType<typeof useStudentHistory>['data']>[number]

export default function StudentCardScreen() {
  const { me } = useAuth()
  // У куратора карточка своя (фаза 61): пять вкладок на чтение вместо
  // доменных полей на правку — править ему нечего, он подтверждает
  if (me?.role === 'curator') return <CuratorCard />
  return <DirectorStudentCard />
}

function DirectorStudentCard() {
  const { id } = useParams()
  const navigate = useNavigate()
  const { me } = useAuth()
  const studentId = Number(id)
  const meta = useDomainMeta()
  const student = useStudent(Number.isFinite(studentId) ? studentId : null)
  const history = useStudentHistory(Number.isFinite(studentId) ? studentId : null)
  const batch = useBatchSave()

  const [tab, setTab] = useState<'domains' | 'history' | 'grades'>('domains')
  // отчёт родителям на одного ученика — у четырёх ролей (27.09.2026)
  const [reporting, setReporting] = useState(false)
  // вкладка «Успеваемость» — у Кымбат и администратора: журналы и посещаемость по урокам
  // оценки читают Кымбат, администратор и трое директоров без журнала; Салтанат — нет
  const seesGrades = ['director_exam', 'director_admission', 'director_talent', 'director_sport', 'admin'].includes(me?.role ?? '')
  const [edits, setEdits] = useState<Record<string, string>>({})
  const [problems, setProblems] = useState<string[]>([])

  const domains = useMemo(() => meta.data?.domains ?? [], [meta.data])
  const mine = domains.find((d) => d.is_mine)

  if (student.isLoading || meta.isLoading) return <Loading />
  if (student.error) return <ErrorNote error={student.error} />
  if (!student.data) return null

  const card = student.data
  const readiness = card.readiness

  async function save() {
    if (!mine || !student.data) return
    const card = student.data
    // правка помнит свой домен: ключ — «домен:поле». Администратор с фазы 68
    // редактирует все пять доменов сразу, и «статус» дисциплины не должен
    // уехать в модель поступления только потому, что поле называется так же
    const changes = Object.entries(edits).flatMap(([key, value]) => {
      const [code, field] = key.split(':')
      const domain = domains.find((d) => d.code === code)
      const model = domain ? profileModelOf(domain) : undefined
      if (!domain || !model) return []
      const spec = model.fields.find((f) => f.name === field)
      return [
        {
          student: studentId,
          model: model.label,
          field,
          value: value.trim() === '' ? null : value.trim(),
          // прежнее значение — чтобы сервер не дал затереть чужую правку.
          // В таблице так было с самого начала, а карточка это теряла
          expected: spec ? raw(card, domain, spec) : '',
        },
      ]
    })
    const result = await batch.mutateAsync(changes)
    setEdits({})
    setProblems([
      ...result.conflicts.map(
        (c) =>
          `${c.field_title}: пока вы правили, там появилось «${c.actual_display}». Ваше значение не применено`,
      ),
      ...result.rejected.map((r) => r.reason),
    ])
    void student.refetch()
    void history.refetch()
  }

  return (
    <div>
      <PublishStudents ids={[card.id]} />
      <div className="toolbar">
        <Button variant="outline" size="sm" onClick={() => navigate(-1)}>
          {t('← Назад')}
        </Button>
        {me && REPORT_ROLES.includes(me.role) && (
          <Button variant="outline" size="sm" onClick={() => setReporting(true)}>
            {t('Отчёт родителям')}
          </Button>
        )}
        {me?.role === 'admin' && <PasswordLinkButton student={card.id} />}
      </div>
      {reporting && <BuildReportDialog student={card.id} studentName={card.full_name} onClose={() => setReporting(false)} />}

      <div className="card card-pad card__hero">
        <div className="card__who">
          <h1 className="card__name">{card.full_name}</h1>
          <p className="muted card__meta">
            {[`${t('группа')} ${card.group_code ?? t('нет')}`, card.email].filter(Boolean).join(' · ')}
          </p>
        </div>
        {readiness && (
          <Ring percent={readiness.score} size={84}>
            <div>
              <div className="num card__score">{readiness.score}%</div>
              <div className="card__scorelabel">{t('готовность')}</div>
            </div>
          </Ring>
        )}
      </div>

      <ScreenTabs
        value={tab}
        onChange={setTab}
        items={[
          { value: 'domains', label: t('Пять доменов') },
          ...(seesGrades ? [{ value: 'grades' as const, label: t('Успеваемость') }] : []),
          { value: 'history', label: t('История изменений') },
        ]}
      />

      {/* панель правок появляется только когда есть что сохранять:
          пустая полоса на её месте — это просто дыра под вкладками */}
      {Object.keys(edits).length > 0 && (
        <div className="toolbar">
          <Chip tone="warn" className="num">
            Не сохранено: {Object.keys(edits).length}
          </Chip>
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              setEdits({})
              setProblems([])
            }}
          >
            {t('Отменить')}
          </Button>
          <Button size="sm" onClick={() => void save()} disabled={batch.isPending}>
            {t('Сохранить')}
          </Button>
        </div>
      )}

      {problems.length > 0 && (
        <div className="card card-pad mb-3 border-(--bad)">
          <span className="eyebrow">{t('Не сохранилось')}</span>
          <ul className="bullets">
            {problems.map((text) => (
              <li key={text}>{text}</li>
            ))}
          </ul>
        </div>
      )}

      {tab === 'domains' && (
        <div className="grid grid--two card__domains">
          {/* порядок в разметке — порядок на телефоне; на ноутбуке карточки
              расставляет `card.css` по именованным областям (фаза 77).
              Реестровая карточка идёт первой: имя и группа —
              это ответ на вопрос «кто это», а не доменные данные */}
          <StudentRegistryCard card={card} canEdit={me?.role === 'admin'} className="card__slot--who" />
          {/* «Поступление» — тот же блок, что у куратора (фаза 70): состав
              и порядок строк равны колонкам таблицы Асем, и собран он
              на сервере одним местом. Реестровая раскладка домена его
              не рисует — иначе владелец видел бы меньше куратора */}
          {card.admission_block && (
            <AdmissionBlock block={card.admission_block} studentId={card.id} className="card__slot--admission" />
          )}
          {domains.flatMap((domain) => {
            const model = profileModelOf(domain)
            const editable = domain.is_mine
            if (!model) return []
            if (domain.code === 'admission') return []
            // у 8–10 нет поступления, экзаменов и документов — их блоков в карточке нет
            if (!domain.parallels.includes(card.parallel)) return []
            // блок домена показывает поля `card=main`; у поступления цели
            // ученика — отдельной карточкой, а служебные признаки в карточке
            // не показываются вовсе (фаза 68). Раскладку задаёт реестр
            const sections: { key: string; title: string; fields: DomainField[] }[] = [
              {
                key: domain.code,
                title: domain.title,
                fields: model.fields.filter((f) => f.card === 'main'),
              },
            ]
            return sections.map((section) => (
              <section
                key={section.key}
                className={`card card-pad domain${editable ? ' domain--mine' : ''} card__slot--${domain.code}`}
              >
                <div className="domain__head">
                  <span className="datacard__title">{section.title}</span>
                  <Chip tone={editable ? 'accent' : 'neutral'}>
                    {editable ? 'вы редактируете' : `ведёт: ${domain.owner_name}`}
                  </Chip>
                </div>
                <dl className="domain__fields">
                  {section.fields.map((field) => (
                    <div key={field.name} className="domain__row">
                      <dt className="muted">{field.title}</dt>
                      <dd>
                        {editable ? (
                          <Input
                            className="cell num domain__input"
                            value={
                              edits[`${domain.code}:${field.name}`] ??
                              (shown(card, domain, field) === t('нет') ? '' : shown(card, domain, field))
                            }
                            onChange={(e) =>
                              setEdits((prev) => ({
                                ...prev,
                                [`${domain.code}:${field.name}`]: e.target.value,
                              }))
                            }
                          />
                        ) : (
                          <span className="num domain__value">{shown(card, domain, field)}</span>
                        )}
                      </dd>
                    </div>
                  ))}
                </dl>
              </section>
            ))
          })}
        </div>
      )}

      {tab === 'grades' && seesGrades && <GradesTab studentId={card.id} />}

      {tab === 'history' && (
        <DataCard title={t('История изменений')} count={history.data?.length || undefined} empty={history.data?.length === 0 && t('изменений пока не было')}>
          {history.isLoading && <Loading />}
          <DataTable
            columns={[
              { key: 'when', title: t('Когда'), width: '16%', cell: (entry: HistoryEntry) => <span className="num">{new Date(entry.created_at).toLocaleString('ru', { dateStyle: 'short', timeStyle: 'short' })}</span>, sortBy: (entry: HistoryEntry) => entry.created_at },
              { key: 'field', title: t('Поле'), width: '22%', cell: (entry: HistoryEntry) => entry.field_title },
              {
                key: 'change',
                title: t('Было и стало'),
                width: '28%',
                cell: (entry: HistoryEntry) => (
                  <span className="num">
                    <span className="t-note">{entry.old_display || t('пусто')}</span> {'→'} <b>{entry.new_display || t('пусто')}</b>
                  </span>
                ),
              },
              { key: 'source', title: t('Источник'), width: '12%', cell: (entry: HistoryEntry) => <Chip size="sm">{entry.source_title}</Chip> },
              {
                // роль на момент действия и «за домен»: подтвердил куратор или
                // владелец, внёс администратор — видно и через год
                key: 'actor',
                title: t('Кто'),
                width: '22%',
                cell: (entry: HistoryEntry) => (
                  <>
                    {entry.actor_name}
                    {entry.actor_role_title && <span className="t-note"> · {entry.actor_role_title}</span>}
                    {entry.acting_for_title && <span className="t-note"> · {entry.acting_for_title}</span>}
                  </>
                ),
              },
            ]}
            rows={history.data ?? []}
            rowKey={(entry) => entry.id}
            limit={30}
          />
        </DataCard>
      )}

      {/* заметки куратора читают Кымбат и Салтанат (фаза 62); список ролей —
          на сервере (`students.notes.NOTE_READERS`), здесь только показ */}
      {(me?.role === 'director_exam' || me?.role === 'director_behavior') && (
        <CuratorNotesBlock student={card.id} />
      )}

      {/* Удаление стоит отдельным блоком внизу и не соседствует с «Сохранить»:
          перепутать кнопки не должно быть возможности */}
      {me?.role === 'admin' && (
        <section className="card card-pad danger">
          <div>
            <span className="datacard__title">
              {t('Удаление карточки')}
              <Hint
                text={t(
                  'Карточка уйдёт в архив вместе с задачами, эссе и списком вузов. Записи журнала изменений останутся, а вернуть ученика можно на экране архива.',
                )}
              />
            </span>
            <p className="muted danger__note">{t('Уходит в архив, откуда возвращается')}</p>
          </div>
          <DeleteButton
            model="students.Student"
            id={card.id}
            path="/students/"
            invalidate={[['students'], ['dashboard']]}
            label={t('Удалить ученика')}
            compact={false}
            onDeleted={() => navigate('/table')}
          />
        </section>
      )}
    </div>
  )
}
