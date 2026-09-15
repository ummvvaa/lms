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
 *
 * Действия строки на ноутбуке — значки (фаза 77): карандаш, копия, глаз.
 * Подпись остаётся при наведении и в доступном имени, поле касания —
 * 44 px, колонка действий одной ширины у всех строк. На телефоне кнопки
 * остаются словами, разметка и вид прежние: телефонная версия не задета.
 * «Записать» у отсутствующего пароля — словом на обеих ширинах: карандаш
 * значит «поправить существующее», а тут значения ещё нет.
 */
import { useState, type ReactNode } from 'react'
import { toast } from 'sonner'
import { CheckIcon, CopyIcon, EyeIcon, EyeOffIcon, PencilIcon } from 'lucide-react'
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
import { Tooltip, TooltipContent, TooltipTrigger } from './ui/tooltip'
import { usePhone } from '../phone'
import { t } from '../i18n'

const MASK = '••••••'

/**
 * Действие строки: на ноутбуке — значок с подписью при наведении
 * и доступным именем, на телефоне — прежняя текстовая кнопка.
 *
 * `name` — доступное имя (не меняется), `label` — что показывается:
 * у «Скопировать» подпись на полторы секунды становится «Скопировано».
 */
function Action({
  phone,
  icon,
  label,
  name = label,
  variant = 'ghost',
  disabled,
  onClick,
}: {
  phone: boolean
  icon: ReactNode
  label: string
  name?: string
  /** вид текстовой кнопки на телефоне — как было до фазы 77 */
  variant?: 'ghost' | 'outline'
  disabled?: boolean
  onClick: () => void
}) {
  if (phone)
    return (
      <Button size="sm" variant={variant} aria-label={t(name)} disabled={disabled} onClick={onClick}>
        {t(label)}
      </Button>
    )
  return (
    <Tooltip>
      <TooltipTrigger
        render={<Button variant="ghost" size="icon" className="cadm__ibtn" disabled={disabled} />}
        aria-label={t(name)}
        onClick={onClick}
      >
        {icon}
      </TooltipTrigger>
      <TooltipContent>{t(label)}</TooltipContent>
    </Tooltip>
  )
}

/** Строка блока: название слева, значение одной строкой, кнопки справа.
 *  В режиме правки (`edit`) поле ввода занимает всю колонку значения,
 *  а «Сохранить» и «Отмена» стоят по своей ширине. */
function Line({
  label,
  value,
  actions,
  mono,
  edit,
}: {
  label: string
  value: ReactNode
  actions?: ReactNode
  mono?: boolean
  edit?: boolean
}) {
  return (
    <div className={`cadm__pair${edit ? ' cadm__pair--edit' : ''}`}>
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

/** «Скопировать» — для почты, телефона и показанного пароля: длинное
 *  читают не глазами, а буфером. У пустого и скрытого значения кнопки нет —
 *  копировать нечего. */
function CopyButton({ phone, value }: { phone: boolean; value: string }) {
  const [done, setDone] = useState(false)
  return (
    <Action
      phone={phone}
      icon={done ? <CheckIcon /> : <CopyIcon />}
      label={done ? 'Скопировано' : 'Скопировать'}
      name="Скопировать"
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(value)
          setDone(true)
          window.setTimeout(() => setDone(false), 1500)
        } catch {
          toast.error(t('Буфер обмена недоступен — скопируйте руками'))
        }
      }}
    />
  )
}

/** Ссылка — словом, в новой вкладке; длинный адрес никому не нужен. */
const LinkValue = ({ href, word }: { href: string; word: string }) => (
  <a className="cadm__link" href={href} target="_blank" rel="noreferrer" title={href}>
    {t(word)}
  </a>
)

function CredentialRow({
  phone,
  studentId,
  kind,
  title,
  present,
  mayReveal,
  mayEdit,
}: {
  phone: boolean
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
        edit
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
            <Action
              phone={phone}
              icon={<EyeIcon />}
              label="Показать"
              variant="outline"
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
            />
          )}
          {shown && <CopyButton phone={phone} value={shown} />}
          {shown && <Action phone={phone} icon={<EyeOffIcon />} label="Скрыть" onClick={() => setShown('')} />}
          {mayEdit && <Action phone={phone} icon={<PencilIcon />} label="Изменить" onClick={() => setDraft('')} />}
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
  phone,
  label,
  value,
  field,
  studentId,
  mayEdit,
  linkWord,
  copy,
}: {
  phone: boolean
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
        edit
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
          {copy && value !== '' && <CopyButton phone={phone} value={value} />}
          {mayEdit && <Action phone={phone} icon={<PencilIcon />} label="Изменить" onClick={() => setDraft(value)} />}
        </>
      }
    />
  )
}

/**
 * GPA в блоке «Поступление» (фаза 71): показывается только здесь, а поле
 * и право остаются у домена экзаменов — правят Кымбат и администратор.
 */
function GpaRow({
  phone,
  value,
  studentId,
  mayEdit,
}: {
  phone: boolean
  value: number | null
  studentId: number
  mayEdit: boolean
}) {
  const save = useSaveExamField(studentId)
  const [draft, setDraft] = useState<string | null>(null)

  if (draft !== null)
    return (
      <Line
        label="Средний GPA"
        edit
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
          <Action
            phone={phone}
            icon={<PencilIcon />}
            label="Изменить"
            onClick={() => setDraft(value === null ? '' : String(value))}
          />
        )
      }
    />
  )
}

const asDate = (value: string) => new Date(value).toLocaleDateString('ru')

export default function AdmissionBlock({
  block,
  studentId,
  className,
}: {
  block: Block
  studentId: number
  /** место карточки в раскладке экрана (фаза 77) */
  className?: string
}) {
  const phone = usePhone()
  const credential = (kind: string, label: string) => {
    const row = block.credentials.find((c) => c.kind === kind)
    if (!row) return null
    return (
      <CredentialRow
        key={row.kind}
        phone={phone}
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
    <DataCard
      title={t('Поступление')}
      note={`${t('Ведёт директор по поступлению —')} ${block.owner}`}
      className={className}
    >
      {/* порядок и названия строк — колонки таблицы Асем (фаза 73);
          ФИО здесь нет: оно в шапке карточки */}
      <div className="cadm">
        <ProfileRow
          phone={phone}
          label="Номер телефона"
          value={block.student_phone}
          field="student_phone"
          studentId={studentId}
          mayEdit={block.may_edit}
          copy
        />
        <ProfileRow
          phone={phone}
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
          phone={phone}
          label="Электронный адрес Common App"
          value={block.common_app_email}
          field="common_app_email"
          studentId={studentId}
          mayEdit={block.may_edit}
          copy
        />
        <ProfileRow
          phone={phone}
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
        <GpaRow phone={phone} value={block.gpa} studentId={studentId} mayEdit={block.may_edit_gpa} />
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
