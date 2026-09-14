/**
 * Блок «Поступление» в карточке ученика (фаза 65, переработан в 70).
 *
 * Один и тот же блок у куратора, Асем и администратора: до 70-й он
 * собирался в двух местах и потому был разным — у куратора одиннадцать
 * строк, у владельца домена три. Порядок строк — порядок колонок
 * таблицы Асем, и ничего сверх них в блоке нет.
 *
 * Пароли от почты и Common App показаны как «••••••» и кнопка
 * «Показать». Показ — отдельный запрос: пароль приходит только по
 * нажатию, в кэш не кладётся, а на сервере каждый показ пишется
 * в журнал ученика. Это единственные данные в системе, которые
 * открывают чужие аккаунты, и открываются они по одному, руками.
 *
 * Попытка из импорта показана с подписью «дата уточняется»: в таблице
 * даты не было, и придумывать её мы не стали.
 */
import { useState } from 'react'
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

/** Строка пароля: маска, кнопка показа и сам пароль после нажатия. */
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

  const editor = draft !== null && (
    <>
      <Input value={draft} aria-label={t(title)} onChange={(event) => setDraft(event.target.value)} />
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
  )

  if (!present) {
    return (
      <div className="cadm__pair">
        <span className="cadm__k">{t(title)}</span>
        {draft === null && <span className="cadm__v cadm__v--empty">{t('не записан')}</span>}
        {editor}
        {mayEdit && draft === null && (
          <Button size="sm" variant="ghost" onClick={() => setDraft('')}>
            {t('Записать')}
          </Button>
        )}
      </div>
    )
  }

  return (
    <div className="cadm__pair">
      <span className="cadm__k">{t(title)}</span>
      {draft === null && <span className="cadm__v">{shown || MASK}</span>}
      {editor}
      {mayReveal && !shown && draft === null && (
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
      {shown && (
        <Button variant="ghost" size="sm" onClick={() => setShown('')}>
          {t('Скрыть')}
        </Button>
      )}
      {mayEdit && draft === null && (
        <Button size="sm" variant="ghost" onClick={() => setDraft('')}>
          {t('Изменить')}
        </Button>
      )}
    </div>
  )
}

export default function AdmissionBlock({ block, studentId }: { block: Block; studentId: number }) {
  const credential = (kind: string) => {
    const row = block.credentials.find((c) => c.kind === kind)
    if (!row) return null
    return (
      <CredentialRow
        key={row.kind}
        studentId={studentId}
        kind={row.kind}
        title={row.title}
        present={row.present}
        mayReveal={block.may_reveal}
        mayEdit={block.may_edit_credentials}
      />
    )
  }

  const document = (code: string) => {
    const doc = block.documents.find((d) => d.code === code)
    if (!doc) return null
    return (
      <div key={doc.code} className="cadm__pair">
        <span className="cadm__k">{t(doc.title)}</span>
        {doc.document === null ? (
          <span className="cadm__v cadm__v--empty">{'—'}</span>
        ) : (
          <a className="cadm__v" href={`/api/documents/${doc.document}/file/`} target="_blank" rel="noreferrer">
            {doc.is_link ? t('открыть ссылку') : t('открыть файл')}
          </a>
        )}
        {/* срок годности — рядом с паспортом, одной строкой (фаза 70); берётся
            из поля профиля, поэтому виден и без ссылки на паспорт (фаза 71) */}
        {doc.code === 'passport' && (
          <Badge
            variant={block.passport_expires_at === null ? 'mute' : doc.state === 'expiring' ? 'warn' : 'ok'}
          >
            {block.passport_expires_at === null
              ? t('срок не указан')
              : `${t('до')} ${new Date(block.passport_expires_at).toLocaleDateString('ru')}`}
          </Badge>
        )}
      </div>
    )
  }

  return (
    <DataCard title={t('Поступление')} note={`${t('Ведёт директор по поступлению —')} ${block.owner}`}>
      {/* порядок строк — порядок колонок таблицы Асем. ФИО здесь нет:
          оно в шапке карточки. Почта ученика — показом: правится она
          там же, где и раньше, в реестровой части карточки (фаза 70) */}
      <div className="cadm">
        <ProfileRow
          label="Телефон ученика"
          value={block.student_phone}
          field="student_phone"
          studentId={studentId}
          mayEdit={block.may_edit}
        />
        {/* личная почта из таблицы (фаза 71): текст, с логином не связана */}
        <ProfileRow
          label="Электронный адрес"
          value={block.email}
          field="personal_email"
          studentId={studentId}
          mayEdit={block.may_edit}
        />
        {credential('email')}
        {credential('common_app')}
        <ProfileRow
          label="Почта Common App"
          value={block.common_app_email}
          field="common_app_email"
          studentId={studentId}
          mayEdit={block.may_edit}
        />
        <ProfileRow
          label="Папка студента"
          value={block.drive_folder_url}
          field="drive_folder_url"
          studentId={studentId}
          mayEdit={block.may_edit}
          linkText="открыть папку"
        />
        {document('passport')}
        <GpaRow value={block.gpa} studentId={studentId} mayEdit={block.may_edit_gpa} />
      </div>

      {/* попытки из таблицы: по три колонки на экзамен, пустые прочерком */}
      <p className="muted cadm__note">
        {t('Результаты из таблицы поступления. Дата в таблице не указана — её уточняет ученик.')}
      </p>
      <div className="cadm">
        {block.attempts.map((slot) =>
          Array.from({ length: slot.slots }, (_, index) => {
            const row = slot.rows[index]
            return (
              <div key={`${slot.exam}-${index}`} className="cadm__pair">
                <span className="cadm__k">{`${slot.exam}-${index + 1}`}</span>
                {row ? (
                  <>
                    <span className="cadm__v num">{row.score ?? '—'}</span>
                    <Badge variant={row.date_unknown ? 'mute' : 'ok'}>
                      {row.date_unknown ? t('дата уточняется') : new Date(row.date).toLocaleDateString('ru')}
                    </Badge>
                  </>
                ) : (
                  <span className="cadm__v cadm__v--empty">{'—'}</span>
                )}
              </div>
            )
          }),
        )}
      </div>

      <div className="cadm">
        {document('transcript')}
        {document('recommendation')}
      </div>
    </DataCard>
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
  linkText,
}: {
  label: string
  value: string
  field: 'student_phone' | 'common_app_email' | 'drive_folder_url' | 'personal_email'
  studentId: number
  mayEdit: boolean
  linkText?: string
}) {
  const save = useSaveAdmissionField(studentId)
  const [draft, setDraft] = useState<string | null>(null)

  if (draft !== null)
    return (
      <div className="cadm__pair">
        <span className="cadm__k">{t(label)}</span>
        <Input value={draft} aria-label={t(label)} onChange={(event) => setDraft(event.target.value)} />
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
      </div>
    )

  return (
    <div className="cadm__pair">
      <span className="cadm__k">{t(label)}</span>
      {value === '' ? (
        <span className="cadm__v cadm__v--empty">{'—'}</span>
      ) : linkText ? (
        <a className="cadm__v" href={value} target="_blank" rel="noreferrer">
          {t(linkText)}
        </a>
      ) : (
        <span className="cadm__v">{value}</span>
      )}
      {mayEdit && (
        <Button size="sm" variant="ghost" onClick={() => setDraft(value)}>
          {t('Изменить')}
        </Button>
      )}
    </div>
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
      <div className="cadm__pair">
        <span className="cadm__k">{t('Средний GPA')}</span>
        <Input
          value={draft}
          inputMode="decimal"
          aria-label={t('Средний GPA')}
          onChange={(event) => setDraft(event.target.value)}
        />
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
      </div>
    )

  return (
    <div className="cadm__pair">
      <span className="cadm__k">{t('Средний GPA')}</span>
      {value === null ? (
        <span className="cadm__v cadm__v--empty">{'—'}</span>
      ) : (
        <span className="cadm__v num">{value}</span>
      )}
      {mayEdit && (
        <Button size="sm" variant="ghost" onClick={() => setDraft(value === null ? '' : String(value))}>
          {t('Изменить')}
        </Button>
      )}
    </div>
  )
}
