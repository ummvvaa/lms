/**
 * Блок «Поступление» в карточке ученика (фаза 65).
 *
 * Данные из таблицы Асем: телефон ученика, почта Common App, папка
 * на Диске, GPA и результаты, попавшие импортом. Ведёт их домен
 * поступления, поэтому у блока стоит имя владельца.
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
import { useRevealCredential, useSetCredential, type AdmissionBlock as Block } from '../../api/hooks'
import { DataCard } from '../../components/ui'
import { Badge } from '../../components/ui/badge'
import { Button } from '../../components/ui/button'
import { Input } from '../../components/ui/input'
import { t } from '../../i18n'

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
  const pair = (label: string, value: string | number | null, link?: boolean) => (
    <div className="cadm__pair">
      <span className="cadm__k">{t(label)}</span>
      {value === null || value === '' ? (
        <span className="cadm__v cadm__v--empty">{'—'}</span>
      ) : link ? (
        <a className="cadm__v" href={String(value)} target="_blank" rel="noreferrer">
          {t('открыть папку')}
        </a>
      ) : (
        <span className="cadm__v">{value}</span>
      )}
    </div>
  )

  return (
    <DataCard title={t('Поступление')} note={`${t('Ведёт директор по поступлению —')} ${block.owner}`}>
      <div className="cadm">
        {pair('Телефон ученика', block.student_phone)}
        {pair('Почта', block.email)}
        {pair('Почта Common App', block.common_app_email)}
        {pair('Папка на Диске', block.drive_folder_url, true)}
        {pair('GPA', block.gpa)}
        {block.credentials.map((row) => (
          <CredentialRow
            key={row.kind}
            studentId={studentId}
            kind={row.kind}
            title={row.title}
            present={row.present}
            mayReveal={block.may_reveal}
            mayEdit={block.may_edit_credentials}
          />
        ))}
      </div>

      {block.imported_attempts.length > 0 && (
        <>
          <p className="muted cadm__note">
            {t('Результаты из таблицы поступления. Дата в таблице не указана — её уточняет ученик.')}
          </p>
          <div className="cadm">
            {block.imported_attempts.map((attempt) => (
              <div key={attempt.id} className="cadm__pair">
                <span className="cadm__k">{attempt.exam}</span>
                <span className="cadm__v num">{attempt.score ?? '—'}</span>
                <Badge variant={attempt.date_unknown ? 'mute' : 'ok'}>
                  {attempt.date_unknown
                    ? t('дата уточняется')
                    : new Date(attempt.date).toLocaleDateString('ru')}
                </Badge>
              </div>
            ))}
          </div>
        </>
      )}
    </DataCard>
  )
}
