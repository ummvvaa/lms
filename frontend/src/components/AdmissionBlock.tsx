/**
 * Блок «Поступление» в карточке ученика (фаза 65, состав — 70, вёрстка — 73).
 *
 * Один и тот же блок у куратора, Асем и администратора — один компонент,
 * одни стили (`ui.css`, грузится приложением целиком). До 73-й стили лежали
 * в `curator.css`, который карточка Асем не грузит: у владельца домена блок
 * стоял без раскладки — тот же класс ошибки, что на «Пользователях» в 69-й.
 *
 * Строки — ровно колонки таблицы Асем, её словами и в её порядке. Значение
 * никогда не ломается посреди себя: телефон, почта, пароль, ссылка идут одной
 * строкой, длинное обрезается многоточием с подсказкой и кнопкой
 * «Скопировать». Кнопки стоят справа и ширину у значения не отнимают.
 *
 * Пароли показаны как «••••••» и кнопка «Показать»: пароль приходит только
 * по нажатию, в кэш не кладётся, а на сервере каждый показ пишется
 * в журнал ученика (фаза 65).
 */
import { useState, type ReactNode } from 'react'
import { toast } from 'sonner'
import {
  useRevealCredential,
  useSaveAdmissionField,
  useSaveExamField,
  useSetCredential,
  type AdmissionBlock as Block,
} from '../api/hooks'
import { DataCard } from './ui'
import { Badge } from './ui/badge'
import { Button } from './ui/button'
import { Input } from './ui/input'
import { t } from '../i18n'

const MASK = '••••••'

/** Строка блока: название слева, значение одной строкой, кнопки справа. */
function Line({ label, value, actions, mono }: { label: string; value: ReactNode; actions?: ReactNode; mono?: boolean }) {
  return (
    <div className="cadm__pair">
      <span className="cadm__k">{t(label)}</span>
      <span className={`cadm__v${mono ? ' cadm__v--mono' : ''}`}>{value}</span>
      {actions && <span className="cadm__acts">{actions}</span>}
    </div>
  )
}

const Empty = () => <span className="cadm__empty">{'—'}</span>

/** Текст, который обрезается многоточием, а не переносится; подсказка — целиком. */
const Text = ({ children }: { children: string }) => (
  <span className="cadm__text" title={children}>
    {children}
  </span>
)

/** «Скопировать» — для почты и телефона: длинный адрес читают не глазами, а буфером. */
function CopyButton({ value }: { value: string }) {
  const [done, setDone] = useState(false)
  return (
    <Button
      size="sm"
      variant="ghost"
      aria-label={t('Скопировать')}
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(value)
          setDone(true)
          window.setTimeout(() => setDone(false), 1500)
        } catch {
          toast.error(t('Буфер обмена недоступен — скопируйте руками'))
        }
      }}
    >
      {done ? t('Скопировано') : t('Скопировать')}
    </Button>
  )
}

/** Ссылка — словом, в новой вкладке; длинный адрес никому не нужен. */
const LinkValue = ({ href, word }: { href: string; word: string }) => (
  <a className="cadm__link" href={href} target="_blank" rel="noreferrer" title={href}>
    {t(word)}
  </a>
)

function CredentialRow({
  studentId,
  kind,
  title,
  present,
  mayReveal,
  mayEdit,
}: {
  studentId: number
  kind: string
  title: string
  present: boolean
  mayReveal: boolean
  mayEdit: boolean
}) {
  const reveal = useRevealCredential(studentId)
  const save = useSetCredential(studentId)
  const [shown, setShown] = useState('')
  const [draft, setDraft] = useState<string | null>(null)

  if (draft !== null)
    return (
      <Line
        label={title}
        value={<Input value={draft} aria-label={t(title)} onChange={(event) => setDraft(event.target.value)} />}
        actions={
          <>
            <Button
              size="sm"
              disabled={save.isPending}
              onClick={() =>
                save.mutate(
                  { kind, password: draft },
                  {
                    onSuccess: () => {
                      setDraft(null)
                      setShown('')
                      toast.success(t('Пароль сохранён'))
                    },
                    onError: (error) => toast.error(error.message),
                  },
                )
              }
            >
              {t('Сохранить')}
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setDraft(null)}>
              {t('Отмена')}
            </Button>
          </>
        }
      />
    )

  if (!present)
    return (
      <Line
        label={title}
        value={<span className="cadm__empty">{t('не записан')}</span>}
        actions={
          mayEdit && (
            <Button size="sm" variant="ghost" onClick={() => setDraft('')}>
              {t('Записать')}
            </Button>
          )
        }
      />
    )

  return (
    <Line
      label={title}
      mono
      value={shown ? <Text>{shown}</Text> : <span aria-label={t('пароль скрыт')}>{MASK}</span>}
      actions={
        <>
          {mayReveal && !shown && (
            <Button
              variant="outline"
              size="sm"
              disabled={reveal.isPending}
              onClick={() =>
                reveal.mutate(kind, {
                  onSuccess: (data) => {
                    setShown(data.password)
                    toast.info(t('Показ пароля записан в журнал ученика'))
                  },
                  onError: (error) => toast.error(error.message),
                })
              }
            >
              {t('Показать')}
            </Button>
          )}
          {shown && <CopyButton value={shown} />}
          {shown && (
            <Button variant="ghost" size="sm" onClick={() => setShown('')}>
              {t('Скрыть')}
            </Button>
          )}
          {mayEdit && (
            <Button size="sm" variant="ghost" onClick={() => setDraft('')}>
              {t('Изменить')}
            </Button>
          )}
        </>
      }
    />
  )
}

/**
 * Строка профиля поступления: показ и правка на месте.
 *
 * Правят Асем, администратор и куратор своей группы (фаза 70) — право
 * приходит с сервера полем `may_edit`, здесь его не вычисляют.
 */
function ProfileRow({
  label,
  value,
  field,
  studentId,
  mayEdit,
  linkWord,
  copy,
}: {
  label: string
  value: string
  field: 'student_phone' | 'common_app_email' | 'drive_folder_url' | 'personal_email'
  studentId: number
  mayEdit: boolean
  /** ссылка — словом вместо адреса */
  linkWord?: string
  /** телефон и почта — с кнопкой «Скопировать» */
  copy?: boolean
}) {
  const save = useSaveAdmissionField(studentId)
  const [draft, setDraft] = useState<string | null>(null)

  if (draft !== null)
    return (
      <Line
        label={label}
        value={<Input value={draft} aria-label={t(label)} onChange={(event) => setDraft(event.target.value)} />}
        actions={
          <>
            <Button
              size="sm"
              disabled={save.isPending}
              onClick={() =>
                save.mutate(
                  { [field]: draft },
                  {
                    onSuccess: () => {
                      setDraft(null)
                      toast.success(t('Сохранено'))
                    },
                    onError: (error) => toast.error(error.message),
                  },
                )
              }
            >
              {t('Сохранить')}
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setDraft(null)}>
              {t('Отмена')}
            </Button>
          </>
        }
      />
    )

  return (
    <Line
      label={label}
      value={value === '' ? <Empty /> : linkWord ? <LinkValue href={value} word={linkWord} /> : <Text>{value}</Text>}
      actions={
        <>
          {copy && value !== '' && <CopyButton value={value} />}
          {mayEdit && (
            <Button size="sm" variant="ghost" onClick={() => setDraft(value)}>
              {t('Изменить')}
            </Button>
          )}
        </>
      }
    />
  )
}

/**
 * GPA в блоке «Поступление» (фаза 71): показывается только здесь, а поле
 * и право остаются у домена экзаменов — правят Кымбат и администратор.
 */
function GpaRow({ value, studentId, mayEdit }: { value: number | null; studentId: number; mayEdit: boolean }) {
  const save = useSaveExamField(studentId)
  const [draft, setDraft] = useState<string | null>(null)

  if (draft !== null)
    return (
      <Line
        label="Средний GPA"
        value={
          <Input
            value={draft}
            inputMode="decimal"
            aria-label={t('Средний GPA')}
            onChange={(event) => setDraft(event.target.value)}
          />
        }
        actions={
          <>
            <Button
              size="sm"
              disabled={save.isPending}
              onClick={() =>
                save.mutate(
                  { gpa: draft.trim().replace(',', '.') },
                  {
                    onSuccess: () => {
                      setDraft(null)
                      toast.success(t('Сохранено'))
                    },
                    onError: (error) => toast.error(error.message),
                  },
                )
              }
            >
              {t('Сохранить')}
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setDraft(null)}>
              {t('Отмена')}
            </Button>
          </>
        }
      />
    )

  return (
    <Line
      label="Средний GPA"
      value={value === null ? <Empty /> : <span className="num">{value}</span>}
      actions={
        mayEdit && (
          <Button size="sm" variant="ghost" onClick={() => setDraft(value === null ? '' : String(value))}>
            {t('Изменить')}
          </Button>
        )
      }
    />
  )
}

const asDate = (value: string) => new Date(value).toLocaleDateString('ru')

export default function AdmissionBlock({ block, studentId }: { block: Block; studentId: number }) {
  const credential = (kind: string, label: string) => {
    const row = block.credentials.find((c) => c.kind === kind)
    if (!row) return null
    return (
      <CredentialRow
        key={row.kind}
        studentId={studentId}
        kind={row.kind}
        title={label}
        present={row.present}
        mayReveal={block.may_reveal}
        mayEdit={block.may_edit_credentials}
      />
    )
  }

  // документ-ссылка из таблицы: словом, в новой вкладке; пустое — прочерк
  const document = (code: string, label: string, word: string) => {
    const doc = block.documents.find((d) => d.code === code)
    return (
      <Line
        key={code}
        label={label}
        value={
          !doc || doc.document === null ? (
            <Empty />
          ) : (
            <LinkValue href={`/api/documents/${doc.document}/file/`} word={word} />
          )
        }
      />
    )
  }

  return (
    <DataCard title={t('Поступление')} note={`${t('Ведёт директор по поступлению —')} ${block.owner}`}>
      {/* порядок и названия строк — колонки таблицы Асем (фаза 73);
          ФИО здесь нет: оно в шапке карточки */}
      <div className="cadm">
        <ProfileRow
          label="Номер телефона"
          value={block.student_phone}
          field="student_phone"
          studentId={studentId}
          mayEdit={block.may_edit}
          copy
        />
        <ProfileRow
          label="Электронный адрес"
          value={block.email}
          field="personal_email"
          studentId={studentId}
          mayEdit={block.may_edit}
          copy
        />
        {credential('email', 'Пароль от эл. адреса')}
        {credential('common_app', 'Пароль от Common App')}
        <ProfileRow
          label="Электронный адрес Common App"
          value={block.common_app_email}
          field="common_app_email"
          studentId={studentId}
          mayEdit={block.may_edit}
          copy
        />
        <ProfileRow
          label="Ссылка на папку студента"
          value={block.drive_folder_url}
          field="drive_folder_url"
          studentId={studentId}
          mayEdit={block.may_edit}
          linkWord="Открыть папку"
        />
        {document('passport', 'Ссылка на паспорт', 'Открыть паспорт')}
        {/* срок — своя строка (фаза 71): виден и когда ссылки на паспорт нет */}
        <Line
          label="Срок годности паспорта"
          value={block.passport_expires_at === null ? <Empty /> : <span className="num">{asDate(block.passport_expires_at)}</span>}
        />
        <GpaRow value={block.gpa} studentId={studentId} mayEdit={block.may_edit_gpa} />
        {/* шесть попыток всегда: балл с датой или «дата уточняется», пустая — прочерк */}
        {block.attempts.map((slot) =>
          Array.from({ length: slot.slots }, (_, index) => {
            const row = slot.rows[index]
            return (
              <Line
                key={`${slot.exam}-${index}`}
                label={`${slot.exam}-${index + 1}`}
                value={
                  row ? (
                    <>
                      <span className="num">{row.score ?? '—'}</span>{' '}
                      <Badge variant={row.date_unknown ? 'mute' : 'ok'}>
                        {row.date_unknown ? t('дата уточняется') : asDate(row.date)}
                      </Badge>
                    </>
                  ) : (
                    <Empty />
                  )
                }
              />
            )
          }),
        )}
        {document('transcript', 'Ссылка на табель', 'Открыть табель')}
        {document('recommendation', 'Ссылка на рек. письмо', 'Открыть письмо')}
      </div>
    </DataCard>
  )
}
