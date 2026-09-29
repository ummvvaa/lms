/**
 * «Ссылка на пароль» в карточке ученика — у куратора и администратора.
 *
 * У 8–10 почты нет: ссылку показывают на экране, и куратор передаёт её
 * лично. Живёт 48 часов и гаснет после первого использования; письмо
 * уходит, только если у ученика есть почта. Выдача — в журнале ученика.
 */
import { useState } from 'react'
import { toast } from 'sonner'
import { useStudentPasswordLink, type PasswordLink } from '../api/hooks'
import { t } from '../i18n'
import Modal from './Modal'
import { Button } from './ui/button'
import { Input } from './ui/input'

export default function PasswordLinkButton({ student }: { student: number }) {
  const issue = useStudentPasswordLink()
  const [shown, setShown] = useState<PasswordLink | null>(null)
  const [copied, setCopied] = useState(false)

  return (
    <>
      <Button
        variant="outline"
        size="sm"
        disabled={issue.isPending}
        onClick={() =>
          issue.mutate(student, {
            onSuccess: (result) => {
              setCopied(false)
              setShown(result)
            },
            onError: (error) => toast.error(error.message),
          })
        }
      >
        {t('Ссылка на пароль')}
      </Button>
      {shown && (
        <Modal title={t('Ссылка на пароль')} onClose={() => setShown(null)}>
          <p className="t-note">{shown.detail}</p>
          <div className="acad__actions">
            <Input className="users__linkfield" readOnly value={shown.link} onFocus={(e) => e.target.select()} />
            <Button
              size="sm"
              onClick={async () => {
                try {
                  await navigator.clipboard.writeText(shown.link)
                  setCopied(true)
                } catch {
                  // буфер может быть закрыт настройками браузера — ссылка и так видна
                  setCopied(false)
                }
              }}
            >
              {copied ? t('Скопировано') : t('Скопировать')}
            </Button>
          </div>
          <p className="t-note">
            {t('Вход')}: <b>{shown.login}</b>
          </p>
        </Modal>
      )}
    </>
  )
}
