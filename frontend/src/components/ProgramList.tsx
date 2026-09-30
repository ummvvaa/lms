/**
 * Программы одного вуза таблицей: программа, требования, раунды, действия
 * (решение владельца, 27.09.2026). Формы программы, требований и раунда —
 * окнами; удаление — в меню строки.
 *
 * Правка руками от директора по поступлению снимает плашку
 * «не подтверждено»: он владелец домена и сверяет данные по сайту —
 * второй кнопки «подтвердить» после каждой правки быть не должно.
 */
import { useState } from 'react'
import { Chip, DataCard, ErrorNote, Loading } from './ui'
import {
  useCreateProgram,
  useCreateRequirement,
  useCreateRound,
  useProgramsOf,
  useUpdateProgram,
  useUpdateRequirement,
  useUpdateRound,
  type DirectoryProgram,
} from '../api/hooks'
import DataTable, { type Column } from './DataTable'
import DeleteButton from './DeleteButton'
import Field from './Field'
import Modal from './Modal'
import RowMenu, { RowMenuItem, RowMenuSeparator } from './RowMenu'
import { t, tk } from '../i18n'
import { Button } from './ui/button'
import { formatDate } from '../lib/format'

const INVALIDATE = [['programs'], ['universities'], ['catalog']]

const LEVELS = [
  { value: 'bachelor', title: tk('Бакалавриат') },
  { value: 'master', title: tk('Магистратура') },
]

const ROUND_TYPES = ['ED', 'EA', 'RD', 'RO']

/** Правка требований: пустое поле значит «требования нет», а не ноль. */
function RequirementDialog({ program, onClose }: { program: DirectoryProgram; onClose: () => void }) {
  const update = useUpdateRequirement()
  const create = useCreateRequirement()
  const current = program.requirement
  const [draft, setDraft] = useState({
    min_gpa: current?.min_gpa?.toString() ?? '',
    min_ielts: current?.min_ielts?.toString() ?? '',
    min_toefl: current?.min_toefl?.toString() ?? '',
    min_sat: current?.min_sat?.toString() ?? '',
    min_act: current?.min_act?.toString() ?? '',
    required_subjects: current?.required_subjects ?? '',
    portfolio_note: current?.portfolio_note ?? '',
  })
  const [portfolio, setPortfolio] = useState(current?.portfolio_required ?? false)
  const [problem, setProblem] = useState<string | null>(null)
  const set = (key: keyof typeof draft) => (value: string) => setDraft({ ...draft, [key]: value })

  const save = () => {
    // пустая строка — это «требования нет» (решение фазы 4), поэтому
    // она уходит как null, а не как ноль: иначе все проходили бы порог
    const body = {
      program: program.id,
      min_gpa: draft.min_gpa.trim() || null,
      min_ielts: draft.min_ielts.trim() || null,
      min_toefl: draft.min_toefl.trim() || null,
      min_sat: draft.min_sat.trim() || null,
      min_act: draft.min_act.trim() || null,
      required_subjects: draft.required_subjects.trim(),
      portfolio_required: portfolio,
      portfolio_note: draft.portfolio_note.trim(),
    }
    const done = { onSuccess: onClose, onError: (e: unknown) => setProblem(String((e as Error).message)) }
    if (current) update.mutate({ id: current.id, ...body }, done)
    else create.mutate(body, done)
  }

  return (
    <Modal title={`${t('Требования')} · ${program.name}`} onClose={onClose}>
      <Field.Row>
        <Field name="min_gpa" label="GPA" value={draft.min_gpa} onChange={set('min_gpa')} />
        <Field name="min_ielts" label="IELTS" value={draft.min_ielts} onChange={set('min_ielts')} />
        <Field name="min_toefl" label="TOEFL" value={draft.min_toefl} onChange={set('min_toefl')} />
      </Field.Row>
      <Field.Row>
        <Field name="min_sat" label="SAT" value={draft.min_sat} onChange={set('min_sat')} />
        <Field name="min_act" label="ACT" value={draft.min_act} onChange={set('min_act')} />
      </Field.Row>
      <Field name="required_subjects" label={t('Требуемые предметы')} value={draft.required_subjects} onChange={set('required_subjects')} placeholder={t('через запятую')} />
      <Field kind="checkbox" name="portfolio" label={t('Нужно портфолио')} checked={portfolio} onChange={setPortfolio} />
      <Field name="portfolio_note" label={t('Требования к портфолио')} value={draft.portfolio_note} onChange={set('portfolio_note')} error={problem ?? undefined} />
      <div className="acad__actions">
        <Button onClick={save} disabled={update.isPending || create.isPending}>
          {t('Сохранить')}
        </Button>
        <Button variant="outline" onClick={onClose}>
          {t('Отмена')}
        </Button>
      </div>
    </Modal>
  )
}

/** Правка или заведение раунда: тип и дедлайн. Дедлайн принадлежит вузу. */
function RoundDialog({ program, round, onClose }: { program: DirectoryProgram; round?: { id: number; round_type: string; deadline: string }; onClose: () => void }) {
  const update = useUpdateRound()
  const create = useCreateRound()
  const [type, setType] = useState(round?.round_type ?? 'RD')
  const [deadline, setDeadline] = useState(round?.deadline ?? '')
  const [problem, setProblem] = useState<string | null>(null)

  const save = () => {
    if (!deadline) {
      setProblem(t('Без даты раунд не имеет смысла: по ней считаются задачи учеников'))
      return
    }
    const body = { program: program.id, round_type: type, deadline }
    const done = { onSuccess: onClose, onError: (e: unknown) => setProblem(String((e as Error).message)) }
    if (round) update.mutate({ id: round.id, ...body }, done)
    else create.mutate(body, done)
  }

  return (
    <Modal title={`${round ? t('Раунд') : t('Новый раунд')} · ${program.name}`} onClose={onClose}>
      <Field.Row>
        <Field kind="select" name="round_type" label={t('Тип раунда')} value={type} onChange={setType} options={ROUND_TYPES.map((value) => ({ value, title: value }))} />
        <Field kind="date" name="deadline" label={t('Дедлайн')} value={deadline} onChange={setDeadline} error={problem ?? undefined} />
      </Field.Row>
      <div className="acad__actions">
        <Button onClick={save} disabled={update.isPending || create.isPending}>
          {t('Сохранить')}
        </Button>
        <Button variant="outline" onClick={onClose}>
          {t('Отмена')}
        </Button>
        {round && (
          <DeleteButton model="universities.AdmissionRound" id={round.id} path="/rounds/" invalidate={INVALIDATE} label={t('Убрать раунд')} onDeleted={onClose} />
        )}
      </div>
    </Modal>
  )
}

/** Правка или заведение программы. */
function ProgramDialog({ universityId, program, onClose }: { universityId: number; program?: DirectoryProgram; onClose: () => void }) {
  const update = useUpdateProgram()
  const create = useCreateProgram()
  const [name, setName] = useState(program?.name ?? '')
  const [level, setLevel] = useState(program?.level ?? 'bachelor')
  const [problem, setProblem] = useState<string | null>(null)

  const save = () => {
    if (!name.trim()) {
      setProblem(t('Название — обязательное поле'))
      return
    }
    const body = { university: universityId, name: name.trim(), level }
    const done = { onSuccess: onClose, onError: (e: unknown) => setProblem(String((e as Error).message)) }
    if (program) update.mutate({ id: program.id, ...body }, done)
    else create.mutate(body, done)
  }

  return (
    <Modal title={program ? program.name : t('Новая программа')} onClose={onClose}>
      <Field name="name" label={t('Название программы')} value={name} onChange={setName} autoFocus error={problem ?? undefined} />
      <Field kind="select" name="level" label={t('Уровень')} value={level} onChange={setLevel} options={LEVELS.map((row) => ({ value: row.value, title: t(row.title) }))} />
      <div className="acad__actions">
        <Button onClick={save} disabled={update.isPending || create.isPending}>
          {t('Сохранить')}
        </Button>
        <Button variant="outline" onClick={onClose}>
          {t('Отмена')}
        </Button>
      </div>
    </Modal>
  )
}

function requirementWords(program: DirectoryProgram): string {
  const req = program.requirement
  if (!req) return ''
  const parts = [
    req.min_gpa ? `GPA ${req.min_gpa}` : '',
    req.min_ielts ? `IELTS ${req.min_ielts}` : '',
    req.min_toefl ? `TOEFL ${req.min_toefl}` : '',
    req.min_sat ? `SAT ${req.min_sat}` : '',
    req.min_act ? `ACT ${req.min_act}` : '',
    req.portfolio_required ? t('портфолио') : '',
  ].filter(Boolean)
  return parts.join(' · ')
}

type Dialog = { kind: 'program'; program?: DirectoryProgram } | { kind: 'requirement'; program: DirectoryProgram } | { kind: 'round'; program: DirectoryProgram; round?: { id: number; round_type: string; deadline: string } } | null

export default function ProgramList({ universityId, canEdit }: { universityId: number; canEdit: boolean }) {
  const list = useProgramsOf(universityId)
  const [dialog, setDialog] = useState<Dialog>(null)

  if (list.isLoading) return <Loading kind="table" />
  if (list.isError) return <ErrorNote error={list.error} />
  const rows = list.data?.results ?? []

  const columns: Column<DirectoryProgram>[] = [
    {
      key: 'name',
      title: t('Программа'),
      width: '30%',
      cell: (program) => (
        <>
          <b>{program.name}</b>
          {!program.is_verified && (
            <>
              {' '}
              <Chip tone="warn" size="sm">
                {t('не подтверждено')}
              </Chip>
            </>
          )}
        </>
      ),
      sortBy: (program) => program.name,
    },
    {
      key: 'requirements',
      title: t('Требования'),
      width: '28%',
      cell: (program) =>
        program.requirement ? (
          <span className="num acad__wrapline">{requirementWords(program) || t('без порогов')}</span>
        ) : canEdit ? (
          <Button variant="link" size="sm" onClick={() => setDialog({ kind: 'requirement', program })}>
            {t('Завести требования')}
          </Button>
        ) : (
          <span className="t-note">{t('не заведены')}</span>
        ),
    },
    {
      key: 'rounds',
      title: t('Раунды'),
      width: '28%',
      cell: (program) => (
        <span className="acad__wrapline">
          {program.rounds.map((round) =>
            canEdit ? (
              <Button key={round.id} variant="link" size="sm" className="num" onClick={() => setDialog({ kind: 'round', program, round })}>
                {round.round_type} · {formatDate(round.deadline)}
              </Button>
            ) : (
              <Chip key={round.id} tone="neutral" size="sm" className="num">
                {round.round_type} · {formatDate(round.deadline)}
              </Chip>
            ),
          )}
          {program.rounds.length === 0 && !canEdit && <span className="t-note">{t('не заведены')}</span>}
          {canEdit && (
            <Button variant="link" size="sm" onClick={() => setDialog({ kind: 'round', program })}>
              {t('Добавить раунд')}
            </Button>
          )}
        </span>
      ),
    },
    {
      key: 'acts',
      title: '',
      width: '14%',
      align: 'right',
      cell: (program) =>
        canEdit ? (
          <span className="acad__inline">
            <Button variant="secondary" size="sm" onClick={() => setDialog({ kind: 'program', program })}>
              {t('Изменить')}
            </Button>
            <RowMenu>
              <RowMenuItem onClick={() => setDialog({ kind: 'requirement', program })}>
                {program.requirement ? t('Изменить требования') : t('Завести требования')}
              </RowMenuItem>
              <RowMenuItem onClick={() => setDialog({ kind: 'round', program })}>{t('Добавить раунд')}</RowMenuItem>
              {program.requirement && (
                <RowMenuItem risk keepOpen>
                  <DeleteButton model="universities.AdmissionRequirement" id={program.requirement.id} path="/requirements/" invalidate={INVALIDATE} label={t('Убрать требования')} inMenu />
                </RowMenuItem>
              )}
              <RowMenuSeparator />
              <RowMenuItem risk keepOpen>
                <DeleteButton model="universities.Program" id={program.id} path="/programs/" invalidate={INVALIDATE} label={t('Удалить программу')} inMenu />
              </RowMenuItem>
            </RowMenu>
          </span>
        ) : null,
    },
  ]

  return (
    <>
      <DataCard
        title={t('Программы')}
        count={rows.length || undefined}
        empty={rows.length === 0 && t('программ у вуза пока нет')}
        emptyAction={
          canEdit ? (
            <Button variant="secondary" size="sm" onClick={() => setDialog({ kind: 'program' })}>
              {t('Добавить программу')}
            </Button>
          ) : undefined
        }
        right={
          canEdit ? (
            <Button variant="link" size="sm" onClick={() => setDialog({ kind: 'program' })}>
              {t('Добавить программу')}
            </Button>
          ) : undefined
        }
      >
        <DataTable columns={columns} rows={rows} rowKey={(program) => program.id} minWidth="840px" />
      </DataCard>
      {dialog?.kind === 'program' && <ProgramDialog universityId={universityId} program={dialog.program} onClose={() => setDialog(null)} />}
      {dialog?.kind === 'requirement' && <RequirementDialog program={dialog.program} onClose={() => setDialog(null)} />}
      {dialog?.kind === 'round' && <RoundDialog program={dialog.program} round={dialog.round} onClose={() => setDialog(null)} />}
    </>
  )
}
