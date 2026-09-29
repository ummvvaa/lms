/**
 * «Ссылка на пароль» кнопкой — в карточке ученика у администратора.
 * Сама выдача и окно — `usePasswordLink`.
 */
import { t } from '../i18n'
import { Button } from './ui/button'
import { usePasswordLink } from './usePasswordLink'

export default function PasswordLinkButton({ student }: { student: number }) {
  const link = usePasswordLink(student)
  return (
    <>
      <Button variant="outline" size="sm" disabled={link.pending} onClick={link.open}>
        {t('Ссылка на пароль')}
      </Button>
      {link.dialog}
    </>
  )
}
