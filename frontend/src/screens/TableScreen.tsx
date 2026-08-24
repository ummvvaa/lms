/**
 * Табличный режим: плотный ввод по своему домену.
 *
 * Колонки берутся из /api/meta/domains/, а не хардкодятся — реестр доменов
 * остаётся единственным источником правды (инвариант №2). Изменения копятся
 * в локальном черновике и уходят одним батч-запросом: сами через две секунды
 * после последней правки или сразу по кнопке «Сохранить».
 *
 * Защита от гонки прежняя: батч несёт `expected`, и правку соседа сервер
 * не затирает молча, а возвращает конфликтом.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useBatchSave, useDomainMeta, useStudents, type BatchChange, type StudentCard } from '../api/hooks'
import type { DomainField } from '../api/types'
import { useAuth } from '../auth/AuthContext'
import Empty from '../components/Empty'
import StudentRegistry from '../components/StudentRegistry'
import { counted, ErrorNote, Loading, ScreenHead } from '../components/ui'
import './table.css'

/** Ключ ячейки в черновике. */
const cellKey = (studentId: number, field: string) => `${studentId}:${field}`

/** Столько учеников забираем за раз — это же потолок `StandardPagination`. */
const PAGE_SIZE = 500

/**
 * Через сколько после последней правки уходит батч.
 *
 * Две секунды — компромисс: человек успевает допечатать число целиком,
 * но не успевает уйти со страницы, думая, что всё сохранено.
 */
const AUTOSAVE_DELAY = 2000

/** Подписи состояния автосохранения — их читает человек, а не машина. */
const SYNC_TITLES: Record<string, { text: string; tone: string }> = {
  dirty: { text: 'есть несохранённые изменения', tone: 'chip-warn' },
  saving: { text: 'сохраняется…', tone: 'chip-mute' },
  saved: { text: 'сохранено', tone: 'chip-ok' },
  rejected: { text: 'сохранено не всё — посмотрите, что не прошло', tone: 'chip-risk' },
  offline: { text: 'нет связи — правки сохранены и уйдут сами', tone: 'chip-risk' },
}

interface Draft {
  [key: string]: { student: number; model: string; field: string; value: string; original: string }
}

function displayValue(student: StudentCard, domainKey: string, field: string): string {
  const profile = (student as unknown as Record<string, Record<string, unknown>>)[domainKey]
  const raw = profile?.[field]
  if (raw === null || raw === undefined) return ''
  if (typeof raw === 'boolean') return raw ? 'да' : 'нет'
  return String(raw)
}

/** Приводим введённое к тому, что ждёт API. */
function parseValue(field: DomainField, text: string): unknown {
  const trimmed = text.trim()
  if (trimmed === '') return field.type === 'boolean' ? false : null
  if (field.type === 'boolean') return ['да', 'yes', 'true', '1', '+'].includes(trimmed.toLowerCase())
  if (field.type === 'integer') {
    const n = Number(trimmed.replace(',', '.'))
    return Number.isFinite(n) ? Math.round(n) : trimmed
  }
  if (field.type === 'number') return trimmed.replace(',', '.')
  return trimmed
}

/** Числовые фильтры, которые умеет `StudentFilter` на бэке. */
const RANGE_FILTERS = ['ielts_min', 'ielts_max', 'sat_min', 'sat_max'] as const

const FILTER_TITLES: Record<string, string> = {
  ielts_min: 'IELTS от',
  ielts_max: 'IELTS до',
  sat_min: 'SAT от',
  sat_max: 'SAT до',
}

export default function TableScreen() {
  const navigate = useNavigate()
  const { me } = useAuth()
  const [params, setParams] = useSearchParams()
  const meta = useDomainMeta()
  const [group, setGroup] = useState('')
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const [draft, setDraft] = useState<Draft>({})
  const [flash, setFlash] = useState<string | null>(null)
  const [problems, setProblems] = useState<string[]>([])
  // состояние автосохранения: черновик → сохраняется → сохранено.
  // «offline» значит, что правки копятся и уйдут, когда связь вернётся
  const [sync, setSync] = useState<'idle' | 'dirty' | 'saving' | 'saved' | 'rejected' | 'offline'>('idle')
  const gridRef = useRef<HTMLTableElement>(null)
  const saveRef = useRef<() => Promise<void>>(async () => {})

  // 500 — потолок сервера. Школа помещается в одну страницу, но если
  // учеников больше, переключатель ниже показывает это явно: молча
  // обрезанный список хуже, чем список с постраничной навигацией.
  // плитки дашборда приводят сюда с фильтром в адресе — иначе клик по
  // «12 IELTS < 6.0» некуда девать
  const range: Record<string, string> = Object.fromEntries(
    RANGE_FILTERS.map((name) => [name, params.get(name) ?? '']).filter(([, value]) => value !== ''),
  )
  const students = useStudents({ group, search, page, page_size: PAGE_SIZE, ...range })
  const batch = useBatchSave()

  const myDomain = meta.data?.domains.find((d) => d.is_mine)
  // профиль домена всегда первая модель — она один-к-одному со Student
  const profileModel = myDomain?.models[0]
  const columns = useMemo(() => profileModel?.fields ?? [], [profileModel])
  const dirtyCount = Object.keys(draft).length

  // --- автосохранение --------------------------------------------------
  // Правки уходят батчем через две секунды после последней. Кнопка
  // «Сохранить» остаётся: явное действие должно быть доступно всегда.
  useEffect(() => {
    if (dirtyCount === 0) return
    // то, что сервер уже отклонил, само себя не отправляет по кругу:
    // ждём, пока человек поправит значение
    if (sync === 'rejected') return
    if (sync !== 'saving') setSync((prev) => (prev === 'offline' ? prev : 'dirty'))
    if (!navigator.onLine) {
      setSync('offline')
      return
    }
    const timer = window.setTimeout(() => void saveRef.current(), AUTOSAVE_DELAY)
    return () => window.clearTimeout(timer)
    // `sync` намеренно не в зависимостях: иначе смена состояния сама
    // перезапускала бы таймер и сохранение не наступало бы никогда
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draft, dirtyCount])

  // связь вернулась — отправляем накопленное и говорим об этом
  useEffect(() => {
    const onOnline = () => {
      if (Object.keys(draft).length === 0) return
      setFlash('Связь вернулась — отправляем накопленные правки')
      void saveRef.current()
    }
    const onOffline = () => setSync('offline')
    window.addEventListener('online', onOnline)
    window.addEventListener('offline', onOffline)
    return () => {
      window.removeEventListener('online', onOnline)
      window.removeEventListener('offline', onOffline)
    }
  }, [draft])

  // предупреждение при уходе со страницы с несохранёнными правками
  useEffect(() => {
    if (dirtyCount === 0) return
    const handler = (event: BeforeUnloadEvent) => {
      event.preventDefault()
      event.returnValue = ''
    }
    window.addEventListener('beforeunload', handler)
    return () => window.removeEventListener('beforeunload', handler)
  }, [dirtyCount])

  const setCell = useCallback(
    (student: StudentCard, field: DomainField, text: string) => {
      if (!myDomain || !profileModel) return
      const original = displayValue(student, myDomain.code, field.name)
      const key = cellKey(student.id, field.name)
      setSync((prev) => (prev === 'rejected' ? 'dirty' : prev))
      setDraft((prev) => {
        const next = { ...prev }
        if (text === original) delete next[key]
        else
          next[key] = {
            student: student.id,
            model: profileModel.label,
            field: field.name,
            value: text,
            original,
          }
        return next
      })
    },
    [myDomain, profileModel],
  )

  /** Вставка из буфера: TSV из Excel раскладывается по ячейкам вправо и вниз. */
  const onPaste = useCallback(
    (event: React.ClipboardEvent<HTMLInputElement>, rowIndex: number, colIndex: number) => {
      const text = event.clipboardData.getData('text/plain')
      if (!text.includes('\t') && !text.includes('\n')) return // обычная вставка в одну ячейку
      event.preventDefault()

      const rows = text.replace(/\r/g, '').replace(/\n$/, '').split('\n')
      const list = students.data?.results ?? []
      rows.forEach((line, r) => {
        const student = list[rowIndex + r]
        if (!student) return
        line.split('\t').forEach((cell, c) => {
          const field = columns[colIndex + c]
          if (field) setCell(student, field, cell.trim())
        })
      })
      setFlash(`Вставлено ${rows.length} строк`)
    },
    [columns, setCell, students.data],
  )

  /** Tab и стрелки водят по сетке, как в таблице. */
  const onKeyDown = (event: React.KeyboardEvent<HTMLInputElement>, row: number, col: number) => {
    const move = (dr: number, dc: number) => {
      const target = gridRef.current?.querySelector<HTMLInputElement>(
        `input[data-row="${row + dr}"][data-col="${col + dc}"]`,
      )
      if (target) {
        event.preventDefault()
        target.focus()
        target.select()
      }
    }
    if (event.key === 'ArrowDown' || event.key === 'Enter') move(1, 0)
    else if (event.key === 'ArrowUp') move(-1, 0)
    else if (event.key === 'Escape') (event.target as HTMLInputElement).blur()
  }

  async function save() {
    // снимок черновика на момент отправки: пока запрос летит, человек
    // продолжает печатать, и очистка целиком стирала бы новые правки
    const sending = { ...draft }
    const keys = Object.keys(sending)
    if (keys.length === 0) return

    const changes: BatchChange[] = Object.values(sending).map((cell) => {
      const field = columns.find((f) => f.name === cell.field)!
      return {
        student: cell.student,
        model: cell.model,
        field: cell.field,
        value: parseValue(field, cell.value),
        // сервер сверит прежнее значение и не затрёт чужую правку
        expected: cell.original,
      }
    })

    setSync('saving')
    let result
    try {
      result = await batch.mutateAsync(changes)
    } catch (error) {
      // связь пропала — правки остаются в черновике и уйдут сами,
      // когда сеть вернётся. Терять набранное нельзя
      setSync('offline')
      setFlash(null)
      setProblems([
        error instanceof Error ? error.message : 'Не удалось сохранить — правки сохранены в черновике',
      ])
      return
    }

    // отклонённые и конфликтные ячейки остаются в черновике: человек
    // должен видеть, что именно не прошло, и поправить это на месте
    const kept = new Set(
      [...result.rejected, ...result.conflicts]
        .filter((row) => row.student !== undefined && row.field !== undefined)
        .map((row) => cellKey(row.student as number, row.field as string)),
    )
    setDraft((prev) => {
      const next = { ...prev }
      for (const key of keys) {
        if (kept.has(key)) continue
        // ячейку, изменённую заново уже после отправки, не трогаем
        if (next[key] && next[key].value === sending[key].value) delete next[key]
      }
      return next
    })
    // «сохранено» только если действительно сохранилось: молчаливая
    // галочка над отклонённой правкой — худший вид обмана
    setSync(kept.size > 0 ? 'rejected' : 'saved')
    const parts = [`Сохранено: ${result.applied}`]
    if (result.conflicts.length) parts.push(`конфликтов: ${result.conflicts.length}`)
    if (result.rejected.length) parts.push(`отклонено: ${result.rejected.length}`)
    setFlash(parts.join(' · '))
    // причина отказа важнее числа: «7,5» вместо «7.5» человек исправит сам,
    // если ему сказать, что именно не подошло
    setProblems([
      ...result.conflicts.map(
        (c) =>
          `${c.field_title}: кто-то уже поставил «${c.actual_display}», ваше «${c.expected_display}» не применено`,
      ),
      ...result.rejected.map((r) => r.reason),
    ])
  }
  saveRef.current = save

  /** Сбросить черновик. Без этого передумать можно только перезагрузкой. */
  function cancel() {
    setDraft({})
    setFlash(null)
    setProblems([])
    setSync('idle')
  }

  if (meta.isLoading || students.isLoading) return <Loading />
  if (meta.error) return <ErrorNote error={meta.error} />
  if (!myDomain || !profileModel) {
    // у администратора домена нет, но реестр школы ведёт именно он:
    // пункт меню, упирающийся в «у вашей роли нет домена», — тупик
    if (me?.role === 'admin') return <StudentRegistry />
    return (
      <div>
        <ScreenHead emoji="⌗" title="Таблица" subtitle="Быстрый ввод по своему домену." />
        <Empty
          emoji="⌗"
          title="У вашей роли нет своего домена"
          what="Табличный ввод работает по полям одного домена: у каждого директора он свой. Ваша роль домена не ведёт, поэтому править здесь нечего."
        />
      </div>
    )
  }

  const rows = students.data?.results ?? []
  const total = students.data?.count ?? rows.length
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE))
  const groups = [...new Set(rows.map((s) => s.group_code).filter(Boolean))].sort()

  return (
    <div>
      <ScreenHead
        emoji="⌗"
        title="Быстрый ввод"
        subtitle={`Только поля домена «${myDomain.title}». Tab — следующая ячейка, вставка из Excel работает.`}
      />

      <div className="toolbar">
        <input
          className="input"
          placeholder="Поиск по имени"
          value={search}
          onChange={(e) => {
            setSearch(e.target.value)
            setPage(1)
          }}
        />
        <select
          className="input"
          value={group}
          onChange={(e) => {
            setGroup(e.target.value)
            setPage(1)
          }}
        >
          <option value="">Все группы</option>
          {groups.map((code) => (
            <option key={code} value={code!}>
              {code}
            </option>
          ))}
        </select>
        <span className="chip chip-mute num">
          {total > rows.length
            ? `${rows.length} из ${counted(total, ['ученика', 'учеников', 'учеников'])}`
            : counted(rows.length, ['ученик', 'ученика', 'учеников'])}
        </span>

        <span className="toolbar__spacer" />
        {flash && <span className="chip chip-ok">{flash}</span>}
        {SYNC_TITLES[sync] && (
          <span className={`chip ${SYNC_TITLES[sync].tone}`} data-sync={sync}>
            {SYNC_TITLES[sync].text}
            {dirtyCount > 0 && sync !== 'saved' && <span className="num"> · {dirtyCount}</span>}
          </span>
        )}
        <button className="btn btn-ghost btn-sm" onClick={() => navigate('/import')}>
          Импорт из файла
        </button>
        <button className="btn btn-ghost btn-sm" onClick={cancel} disabled={dirtyCount === 0}>
          Отменить правки
        </button>
        <button
          className="btn btn-primary btn-sm"
          onClick={() => void save()}
          disabled={dirtyCount === 0 || batch.isPending}
        >
          {batch.isPending ? 'Сохраняю…' : 'Сохранить'}
        </button>
      </div>

      {Object.keys(range).length > 0 && (
        <div className="toolbar">
          <span className="muted">Фильтр из дашборда:</span>
          {Object.entries(range).map(([name, value]) => (
            <span key={name} className="chip chip-brand num">
              {FILTER_TITLES[name] ?? name} {value}
            </span>
          ))}
          <button
            className="btn btn-ghost btn-sm"
            onClick={() => {
              setParams(new URLSearchParams())
              setPage(1)
            }}
          >
            Снять фильтр
          </button>
        </div>
      )}

      {problems.length > 0 && (
        <div className="card card-pad" style={{ marginBottom: 12, borderColor: 'var(--risk)' }}>
          <span className="eyebrow">Не сохранилось</span>
          <ul style={{ margin: '10px 0 0', paddingLeft: 18 }}>
            {problems.map((text) => (
              <li key={text} style={{ fontSize: 13, padding: '3px 0' }}>
                {text}
              </li>
            ))}
          </ul>
        </div>
      )}

      {rows.length === 0 && (
        <Empty
          emoji="⌗"
          title={search || group ? 'По этому фильтру никого нет' : 'Учеников пока нет'}
          what={
            search || group
              ? 'Ни один ученик не подошёл под поиск и выбранную группу. Снимите фильтры, чтобы увидеть всех.'
              : `В этой таблице вы правите поля домена «${myDomain.title}» у всех учеников школы. Как только ученики появятся в базе, здесь будет строка на каждого — со вставкой из Excel и переходом по Tab.`
          }
          action={search || group ? 'Снять фильтры' : 'Загрузить файл с учениками'}
          onAction={
            search || group
              ? () => {
                  setSearch('')
                  setGroup('')
                }
              : () => navigate('/import')
          }
        />
      )}

      <div className="card grid-wrap" hidden={rows.length === 0}>
        <table className="grid-tbl" ref={gridRef}>
          <thead>
            <tr>
              <th className="sticky-col">Ученик</th>
              <th className="col-narrow">Гр.</th>
              {columns.map((field) => (
                <th key={field.name} title={field.title}>
                  {field.short}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((student, rowIndex) => (
              <tr key={student.id}>
                <td className="sticky-col">
                  <button className="cell cell-link" onClick={() => navigate(`/students/${student.id}`)}>
                    {student.full_name}
                  </button>
                </td>
                <td>
                  <span className="cell cell-ro num">{student.group_code ?? '—'}</span>
                </td>
                {columns.map((field, colIndex) => {
                  const key = cellKey(student.id, field.name)
                  const dirty = draft[key]
                  const value = dirty ? dirty.value : displayValue(student, myDomain.code, field.name)
                  return (
                    <td key={field.name}>
                      <input
                        className={`cell num${dirty ? ' cell-dirty' : ''}`}
                        data-row={rowIndex}
                        data-col={colIndex}
                        value={value}
                        list={field.choices ? `choices-${field.name}` : undefined}
                        onChange={(e) => setCell(student, field, e.target.value)}
                        onPaste={(e) => onPaste(e, rowIndex, colIndex)}
                        onKeyDown={(e) => onKeyDown(e, rowIndex, colIndex)}
                      />
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {pages > 1 && (
        <div className="toolbar" style={{ marginTop: 12 }}>
          <button
            className="btn btn-ghost btn-sm"
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={page === 1 || dirtyCount > 0}
          >
            ← Предыдущие
          </button>
          <span className="chip chip-mute num">
            страница {page} из {pages}
          </span>
          <button
            className="btn btn-ghost btn-sm"
            onClick={() => setPage((p) => Math.min(pages, p + 1))}
            disabled={page === pages || dirtyCount > 0}
          >
            Следующие →
          </button>
          {dirtyCount > 0 && <span className="muted">Сначала сохраните правки</span>}
        </div>
      )}

      {columns
        .filter((f) => f.choices)
        .map((field) => (
          <datalist key={field.name} id={`choices-${field.name}`}>
            {field.choices!.map((choice) => (
              <option key={choice.value} value={choice.value}>
                {choice.title}
              </option>
            ))}
          </datalist>
        ))}
    </div>
  )
}
