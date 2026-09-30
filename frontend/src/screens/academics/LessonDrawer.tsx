/**
 * Панель урока у Кымбат и администратора: факты и пять действий — изменить
 * (только этот / этот и все следующие), замена, перенос, отмена, удаление.
 *
 * Образец — `lessonDrawer`, `lessonForm`, `les-sub`, `les-move`, `les-cancel`,
 * `les-del` референса. Накладки проверяются на сервере до сохранения;
 * сохранить с накладкой можно только явным подтверждением.
 */
import { useEffect, useMemo, useState } from 'react'
import { toast } from 'sonner'
import {
  useAcadMeta,
  useAllCohorts,
  useCancelLesson,
  useCheckConflicts,
  useCreateLesson,
  useDeleteLesson,
  useDeletePreview,
  useEditLesson,
  useMoveLesson,
  useRestoreLesson,
  useSubstitute,
  useSubstitutes,
  useTeachers,
  type AcadConflict,
  type AcadLesson,
} from '../../api/academics'
import EditDrawer from '../../components/EditDrawer'
import Field from '../../components/Field'
import Modal from '../../components/Modal'
import { Row, Rows, Segmented } from '../../components/patterns'
import { Chip, counted } from '../../components/ui'
import { Button } from '../../components/ui/button'
import { t } from '../../i18n'
import { dateFull, dateWords } from './shared'

const WEEKDAYS_ACC = ['понедельник', 'вторник', 'среду', 'четверг', 'пятницу', 'субботу', 'воскресенье']

function weekdayAccusative(iso: string): string {
  const day = new Date(`${iso}T00:00:00`)
  return t(WEEKDAYS_ACC[(day.getDay() + 6) % 7])
}

function ConflictNote({ conflicts, checked }: { conflicts: AcadConflict[]; checked: boolean }) {
  if (!checked) return null
  if (conflicts.length === 0)
    return (
      <Chip tone="good">
        {t('Накладок нет: учитель, кабинет и ученики в это время свободны')}
      </Chip>
    )
  return (
    <Chip tone="bad">
      {`${t('Накладка:')} ${conflicts.map((c) => c.text).join('; ')}. ${t('Сохранить можно, накладка останется в списке у Кымбат и администратора.')}`}
    </Chip>
  )
}

/** Форма урока: новый (повтор или разовый) или правка (только этот / этот и следующие). */
export function LessonForm({
  lesson,
  date: initialDate,
  slot: initialSlot,
  onClose,
}: {
  lesson?: AcadLesson
  date?: string
  slot?: number
  onClose: () => void
}) {
  const meta = useAcadMeta()
  const cohorts = useAllCohorts()
  const teachers = useTeachers()
  const check = useCheckConflicts()
  const create = useCreateLesson()
  const edit = useEditLesson()
  const [scope, setScope] = useState<'this' | 'next'>('this')
  const [repeat, setRepeat] = useState<'weekly' | 'once'>('weekly')
  const [subject, setSubject] = useState(String(lesson?.subject.id ?? ''))
  const [teacher, setTeacher] = useState(String(lesson?.actual_teacher?.id ?? ''))
  const [kind, setKind] = useState<'group' | 'subgroup' | 'stream'>(lesson?.cohort.kind ?? 'group')
  const [cohort, setCohort] = useState(String(lesson?.cohort.id ?? ''))
  const [date, setDate] = useState(lesson?.date ?? initialDate ?? meta.data?.today ?? '')
  const [slot, setSlot] = useState(String(lesson?.slot ?? initialSlot ?? 1))
  const [room, setRoom] = useState(lesson?.room ?? '')
  const [force, setForce] = useState(false)
  const [error, setError] = useState('')
  const [conflicts, setConflicts] = useState<AcadConflict[]>([])
  const [checked, setChecked] = useState(false)

  const subjects = useMemo(() => meta.data?.subjects ?? [], [meta.data])
  const staff = useMemo(() => {
    const all = teachers.data?.rows ?? []
    const pool = all.filter((row) => !subject || row.subjects.some((s) => String(s.id) === subject) || row.subjects.length === 0)
    return pool.length ? pool : all
  }, [teachers.data, subject])
  const options = useMemo(() => (cohorts.data?.rows ?? []).filter((row) => row.kind === kind), [cohorts.data, kind])
  const onlyThis = Boolean(lesson) && scope === 'this' && !lesson?.is_one_off

  useEffect(() => {
    if (!subject && subjects.length) setSubject(String(subjects[0].id))
  }, [subject, subjects])
  // новому уроку учитель подставляется; у заведённого пустое значение —
  // «учитель не назначен», и молча подставлять туда первого нельзя
  useEffect(() => {
    if (!lesson && !teacher && staff.length) setTeacher(String(staff[0].id))
  }, [lesson, teacher, staff])
  useEffect(() => {
    if (!options.some((row) => String(row.id) === cohort)) setCohort(String(options[0]?.id ?? ''))
  }, [options, cohort])
  useEffect(() => {
    if (!cohort || !date || !slot) return
    const timer = window.setTimeout(() => {
      check.mutate(
        { teacher: teacher ? Number(teacher) : null, cohort: Number(cohort), date, slot: Number(slot), room, exclude: lesson?.id },
        {
          onSuccess: (result) => {
            setConflicts(result.conflicts)
            setChecked(true)
          },
        },
      )
    }, 250)
    return () => window.clearTimeout(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [teacher, cohort, date, slot, room])

  const submit = () => {
    setError('')
    const fail = (e: Error) => setError(e.message)
    if (!cohort) {
      setError(t('Выберите, кто учится'))
      return
    }
    if (conflicts.length && !force) {
      setError(t('Есть накладка: отметьте «Всё равно сохранить» или выберите другое время'))
      return
    }
    if (lesson) {
      edit.mutate(
        { id: lesson.id, scope, date, slot: Number(slot), room, teacher: teacher ? Number(teacher) : null, cohort: Number(cohort), subject: Number(subject), force },
        {
          onSuccess: () => {
            toast.success(scope === 'next' ? `${t('Изменено с')} ${dateWords(date)} ${t('и дальше. Прошедшие уроки не тронуты')}` : t('Изменён только этот урок'))
            onClose()
          },
          onError: fail,
        },
      )
      return
    }
    create.mutate(
      { subject: Number(subject), teacher: teacher ? Number(teacher) : null, cohort: Number(cohort), date, slot: Number(slot), room, repeat, force },
      {
        onSuccess: () => {
          toast.success(repeat === 'weekly' ? `${t('Урок добавлен: каждый')} ${weekdayAccusative(date)}, ${slot} ${t('урок')}` : `${t('Разовый урок добавлен на')} ${dateWords(date)}`)
          onClose()
        },
        onError: fail,
      },
    )
  }

  return (
    <Modal title={lesson ? t('Изменить урок') : t('Новый урок')} note={lesson ? `${lesson.subject.title} · ${lesson.cohort.name} · ${lesson.weekday}, ${dateWords(lesson.date)}` : t('Урок заводится один раз и повторяется по неделям')} onClose={onClose} wide>
      {lesson && !lesson.is_one_off && (
        <Segmented
          value={scope}
          onChange={setScope}
          label={t('Что меняем')}
          items={[
            { value: 'this', label: t('Только этот урок') },
            { value: 'next', label: t('Этот и все следующие') },
          ]}
        />
      )}
      <Field.Row>
        <Field kind="select" name="subject" label={t('Предмет')} value={subject} onChange={setSubject} options={subjects.map((s) => ({ value: String(s.id), title: s.title }))} disabled={onlyThis} />
        <Field kind="select" name="teacher" label={t('Учитель')} value={teacher} onChange={setTeacher} options={[{ value: '', title: t('Учитель не назначен') }, ...staff.map((row) => ({ value: String(row.id), title: row.full_name }))]} />
      </Field.Row>
      <Segmented
        value={kind}
        onChange={(next) => !onlyThis && setKind(next)}
        label={t('Кто учится')}
        items={[
          { value: 'group', label: t('Вся группа') },
          { value: 'subgroup', label: t('Подгруппа') },
          { value: 'stream', label: t('Поток: группы вместе') },
        ]}
      />
      <Field
        kind="select"
        name="cohort"
        label={kind === 'group' ? t('Группа') : kind === 'subgroup' ? t('Подгруппа') : t('Поток')}
        value={cohort}
        onChange={setCohort}
        options={options.map((row) => ({ value: String(row.id), title: `${row.name}${row.subject ? ` · ${row.subject.short_title.toLowerCase()}` : ''} · ${counted(row.students, ['ученик', 'ученика', 'учеников'])}` }))}
        placeholder={options.length ? undefined : kind === 'subgroup' ? t('подгрупп нет — разделите группу на «Подгруппы и потоки»') : t('потоков нет — соберите на «Подгруппы и потоки»')}
        disabled={onlyThis}
      />
      {!lesson && (
        <Segmented
          value={repeat}
          onChange={setRepeat}
          label={t('Повтор')}
          items={[
            { value: 'weekly', label: t('Каждую неделю') },
            { value: 'once', label: t('Один раз') },
          ]}
        />
      )}
      <Field.Row>
        <Field kind="date" name="date" label={repeat === 'weekly' && !lesson ? t('Начиная с') : t('Дата')} value={date} onChange={setDate} />
        <Field kind="select" name="slot" label={t('Урок')} value={slot} onChange={setSlot} options={(meta.data?.bells ?? []).map((b) => ({ value: String(b.number), title: `${b.number} ${t('урок')} · ${b.starts.slice(0, 5)}–${b.ends.slice(0, 5)}` }))} />
        <Field kind="text" name="room" label={t('Кабинет')} value={room} onChange={setRoom} placeholder={(meta.data?.rooms ?? []).slice(0, 3).join(', ')} />
      </Field.Row>
      {repeat === 'weekly' && !lesson && date && (
        <p className="acad__note">
          {t('Повтор: каждый')} {weekdayAccusative(date)} {t('до конца учебного года')}
          {meta.data?.year ? `, ${dateFull(meta.data.year.ends)}` : ''} · {t('каникулы и праздники пропускаются')}
        </p>
      )}
      {onlyThis && <p className="acad__note">{t('Для одного урока меняются дата, урок, кабинет и учитель. Предмет и состав — через «Этот и все следующие».')}</p>}
      <ConflictNote conflicts={conflicts} checked={checked} />
      {conflicts.length > 0 && <Field kind="checkbox" name="force" label={t('Всё равно сохранить с накладкой')} checked={force} onChange={setForce} />}
      {error && (
        <Chip tone="bad">
          {error}
        </Chip>
      )}
      <div className="acad__actions">
        <Button onClick={submit} disabled={create.isPending || edit.isPending}>
          {lesson ? t('Сохранить') : t('Добавить урок')}
        </Button>
        <Button variant="outline" onClick={onClose}>
          {t('Отмена')}
        </Button>
      </div>
    </Modal>
  )
}

function SubstituteDialog({ lesson, onClose }: { lesson: AcadLesson; onClose: () => void }) {
  const teachers = useTeachers()
  const candidates = useSubstitutes(lesson.id)
  const substitute = useSubstitute()
  // занятый в это время по звонкам урока в выбор не попадает: сервер его не примет
  const { state, pool, busy } = useMemo(() => {
    const state = new Map((candidates.data?.rows ?? []).map((row) => [row.id, row]))
    const others = (teachers.data?.rows ?? []).filter((row) => row.id !== lesson.teacher?.id)
    return {
      state,
      pool: candidates.data ? others.filter((row) => state.get(row.id)?.free !== false) : [],
      busy: others.filter((row) => state.get(row.id)?.free === false),
    }
  }, [candidates.data, teachers.data, lesson.teacher?.id])
  const [teacher, setTeacher] = useState('')
  const [reason, setReason] = useState(t('Учитель на больничном'))
  const [error, setError] = useState('')
  useEffect(() => {
    if (!teacher && pool.length) setTeacher(String((pool.find((row) => row.subjects.some((s) => s.id === lesson.subject.id)) ?? pool[0]).id))
  }, [teacher, pool, lesson.subject.id])
  return (
    <Modal title={lesson.teacher ? t('Замена учителя') : t('Кто ведёт этот урок')} note={`${lesson.subject.title} · ${lesson.cohort.name} · ${lesson.weekday}, ${dateWords(lesson.date)}, ${lesson.slot} ${t('урок')}`} onClose={onClose}>
      <Field kind="select" name="teacher" label={t('Кто заменяет')} value={teacher} onChange={setTeacher} options={pool.map((row) => ({ value: String(row.id), title: `${row.full_name}${row.subjects.some((s) => s.id === lesson.subject.id) ? ` · ${t('этот предмет')}` : ''}` }))} />
      {busy.length > 0 && (
        <p className="acad__note">
          {t('Заняты в это время:')} {busy.map((row) => `${row.full_name} (${state.get(row.id)?.busy_with ?? ''})`).join(', ')}
        </p>
      )}
      <Field kind="text" name="reason" label={t('Причина')} value={reason} onChange={setReason} error={error || undefined} />
      <p className="acad__note">{t('Заменяющий увидит урок у себя и сможет отметить посещаемость и поставить оценки в журнал основного учителя.')}</p>
      <div className="acad__actions">
        <Button
          onClick={() =>
            substitute.mutate(
              { id: lesson.id, teacher: Number(teacher), reason },
              {
                onSuccess: () => {
                  toast.success(t('Замена назначена'))
                  onClose()
                },
                onError: (e) => setError(e.message),
              },
            )
          }
          disabled={!teacher || substitute.isPending}
        >
          {t('Назначить замену')}
        </Button>
        <Button variant="outline" onClick={onClose}>
          {t('Отмена')}
        </Button>
      </div>
    </Modal>
  )
}

function MoveDialog({ lesson, onClose }: { lesson: AcadLesson; onClose: () => void }) {
  const meta = useAcadMeta()
  const move = useMoveLesson()
  const check = useCheckConflicts()
  const [date, setDate] = useState(lesson.date)
  const [slot, setSlot] = useState(String(lesson.slot === 8 ? 7 : lesson.slot + 1))
  const [reason, setReason] = useState('')
  const [force, setForce] = useState(false)
  const [error, setError] = useState('')
  const [conflicts, setConflicts] = useState<AcadConflict[]>([])
  const [checked, setChecked] = useState(false)
  useEffect(() => {
    const timer = window.setTimeout(() => {
      check.mutate(
        { teacher: lesson.actual_teacher?.id ?? null, cohort: lesson.cohort.id, date, slot: Number(slot), room: lesson.room, exclude: lesson.id },
        {
          onSuccess: (result) => {
            setConflicts(result.conflicts)
            setChecked(true)
          },
        },
      )
    }, 250)
    return () => window.clearTimeout(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [date, slot])
  return (
    <Modal title={t('Перенести урок')} note={`${lesson.subject.title} · ${lesson.cohort.name} · ${lesson.weekday}, ${dateWords(lesson.date)}, ${lesson.slot} ${t('урок')}`} onClose={onClose}>
      <Field.Row>
        <Field kind="date" name="date" label={t('Новая дата')} value={date} onChange={setDate} />
        <Field kind="select" name="slot" label={t('Урок')} value={slot} onChange={setSlot} options={(meta.data?.bells ?? []).map((b) => ({ value: String(b.number), title: `${b.number} ${t('урок')} · ${b.starts.slice(0, 5)}–${b.ends.slice(0, 5)}` }))} />
      </Field.Row>
      <Field kind="text" name="reason" label={t('Причина')} value={reason} onChange={setReason} error={error || undefined} />
      <ConflictNote conflicts={conflicts} checked={checked} />
      {conflicts.length > 0 && <Field kind="checkbox" name="force" label={t('Всё равно перенести с накладкой')} checked={force} onChange={setForce} />}
      <div className="acad__actions">
        <Button
          onClick={() =>
            move.mutate(
              { id: lesson.id, date, slot: Number(slot), reason, force },
              {
                onSuccess: () => {
                  toast.success(`${t('Перенесено на')} ${dateWords(date)}, ${slot} ${t('урок')}`)
                  onClose()
                },
                onError: (e) => setError(e.message),
              },
            )
          }
          disabled={move.isPending}
        >
          {t('Перенести')}
        </Button>
        <Button variant="outline" onClick={onClose}>
          {t('Отмена')}
        </Button>
      </div>
    </Modal>
  )
}

function CancelDialog({ lesson, onClose }: { lesson: AcadLesson; onClose: () => void }) {
  const cancel = useCancelLesson()
  const [reason, setReason] = useState('')
  const [error, setError] = useState('')
  return (
    <Modal title={t('Отменить урок')} note={`${lesson.subject.title} · ${lesson.cohort.name} · ${lesson.weekday}, ${dateWords(lesson.date)}`} onClose={onClose}>
      <Field kind="text" name="reason" label={t('Причина — её увидят ученики')} value={reason} onChange={setReason} placeholder={t('Например: учитель на семинаре')} autoFocus error={error || undefined} />
      <p className="acad__note">{t('Урок останется в расписании зачёркнутым. Учителю и ученикам придёт уведомление.')}</p>
      <div className="acad__actions">
        <Button
          variant="destructive"
          onClick={() =>
            cancel.mutate(
              { id: lesson.id, reason },
              {
                onSuccess: () => {
                  toast.success(t('Урок отменён'))
                  onClose()
                },
                onError: (e) => setError(e.message),
              },
            )
          }
          disabled={cancel.isPending}
        >
          {t('Отменить урок')}
        </Button>
        <Button variant="outline" onClick={onClose}>
          {t('Не отменять')}
        </Button>
      </div>
    </Modal>
  )
}

function DeleteDialog({ lesson, onClose }: { lesson: AcadLesson; onClose: () => void }) {
  const [scope, setScope] = useState<'this' | 'next'>('this')
  const preview = useDeletePreview(lesson.id, scope)
  const remove = useDeleteLesson()
  const [error, setError] = useState('')
  const info = preview.data
  return (
    <Modal title={t('Удалить урок')} note={`${lesson.subject.title} · ${lesson.cohort.name} · ${lesson.weekday}, ${dateWords(lesson.date)}, ${lesson.slot} ${t('урок')}`} onClose={onClose}>
      {!lesson.is_one_off && (
        <Segmented
          value={scope}
          onChange={setScope}
          label={t('Что удаляем')}
          items={[
            { value: 'this', label: t('Только этот урок') },
            { value: 'next', label: t('Этот и все следующие') },
          ]}
        />
      )}
      {info && (
        <p className="acad__note">
          {t('Будет удалено:')} <b>{counted(info.count, ['урок', 'урока', 'уроков'])}</b>
          {scope === 'next' ? `, ${t('с')} ${dateWords(info.from)} ${t('до')} ${dateWords(info.to)}` : ''}.{' '}
          {info.marked
            ? `${t('У')} ${counted(info.marked, ['урока', 'уроков', 'уроков'])} ${t('уже есть отметки и оценки — они уйдут в архив администратора вместе с уроком, их можно вернуть.')}`
            : t('Отметок и оценок в них нет.')}{' '}
          {t('Прошедшие уроки до этой даты не трогаются.')}
        </p>
      )}
      {error && (
        <Chip tone="bad">
          {error}
        </Chip>
      )}
      <div className="acad__actions">
        <Button
          variant="destructive"
          onClick={() =>
            remove.mutate(
              { id: lesson.id, scope },
              {
                onSuccess: (result) => {
                  toast.success(`${t('Удалено')} ${counted(result.deleted, ['урок', 'урока', 'уроков'])}`)
                  onClose()
                },
                onError: (e) => setError(e.message),
              },
            )
          }
          disabled={remove.isPending}
        >
          {t('Удалить')}
        </Button>
        <Button variant="outline" onClick={onClose}>
          {t('Отмена')}
        </Button>
      </div>
    </Modal>
  )
}

export default function LessonDrawer({ lesson, conflicts, onClose }: { lesson: AcadLesson; conflicts: AcadConflict[]; onClose: () => void }) {
  const restore = useRestoreLesson()
  const [dialog, setDialog] = useState<'edit' | 'sub' | 'move' | 'cancel' | 'delete' | null>(null)
  const changed = lesson.status !== 'planned' || Boolean(lesson.substitute)
  const past = lesson.state === 'past' && lesson.date < new Date().toISOString().slice(0, 10)
  return (
    <>
      <EditDrawer
        open={dialog === null}
        onClose={onClose}
        title={lesson.subject.title}
        sub={`${lesson.cohort.name} · ${lesson.weekday}, ${dateWords(lesson.date)}, ${lesson.slot} ${t('урок')}`}
        footer={
          changed ? (
            <Button variant="outline" onClick={() => restore.mutate(lesson.id, { onSuccess: () => { toast.success(t('Урок возвращён как было')); onClose() }, onError: (e) => toast.error(e.message) })}>
              {t('Вернуть как было')}
            </Button>
          ) : undefined
        }
      >
        {conflicts.length > 0 && (
          <Chip tone="bad">
            {`${t('Накладка.')} ${conflicts.map((c) => c.text).join('; ')}`}
          </Chip>
        )}
        <Rows>
          <Row title={t('Когда')} value={`${lesson.weekday}, ${dateWords(lesson.date)} · ${lesson.slot} ${t('урок')}, ${lesson.bell}`} />
          <Row title={t('Кабинет')} value={lesson.room || null} none={t('не указан')} />
          <Row title={t('Учитель')} value={lesson.actual_teacher?.full_name ?? ''} none={t('не назначен')} note={lesson.substitute ? t('замена') : undefined} />
          <Row title={t('Состав')} value={`${lesson.cohort.name} · ${counted(lesson.cohort.students, ['ученик', 'ученика', 'учеников'])}`} note={lesson.cohort.kind !== 'group' ? lesson.cohort.kind_title : undefined} />
          <Row title={t('Отметки')} value={lesson.marked ? (lesson.marked_by?.short ?? t('отмечен')) : null} none={lesson.state === 'future' ? t('урок ещё впереди') : t('учитель не отметил')} />
          {lesson.reason && <Row title={t('Причина')} value={lesson.reason} />}
        </Rows>
        {past ? (
          <p className="acad__note">{t('Прошедший урок не меняется: это уже история журнала.')}</p>
        ) : (
          <Rows>
            <Row icon="pencil" tone="neutral" title={t('Изменить')} note={t('этот урок или этот и все следующие')} onOpen={() => setDialog('edit')} />
            <Row icon="people" tone="neutral" title={t('Замена учителя')} note={t('только на эту дату')} onOpen={() => setDialog('sub')} />
            <Row icon="calendar" tone="neutral" title={t('Перенести')} note={t('на другой день или урок')} onOpen={() => setDialog('move')} />
            <Row icon="close" tone="neutral" title={t('Отменить урок')} note={t('останется в расписании зачёркнутым')} onOpen={() => setDialog('cancel')} />
            <Row icon="box" tone="bad" title={t('Удалить')} note={t('если урок заведён по ошибке')} onOpen={() => setDialog('delete')} />
          </Rows>
        )}
      </EditDrawer>
      {dialog === 'edit' && <LessonForm lesson={lesson} onClose={onClose} />}
      {dialog === 'sub' && <SubstituteDialog lesson={lesson} onClose={onClose} />}
      {dialog === 'move' && <MoveDialog lesson={lesson} onClose={onClose} />}
      {dialog === 'cancel' && <CancelDialog lesson={lesson} onClose={onClose} />}
      {dialog === 'delete' && <DeleteDialog lesson={lesson} onClose={onClose} />}
    </>
  )
}
