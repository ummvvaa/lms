/**
 * Личная почта в профиле ученика.
 *
 * У 8–10 почты школы нет: без личной почты «Забыли пароль» им не поможет —
 * ссылку выдаёт только куратор. Подтверждённая личная почта — второй способ
 * войти и адрес для сброса пароля. До подтверждения она не работает никак.
 */
import { useState } from 'react'
import { toast } from 'sonner'
import { useLinkIdentity } from '../api/hooks'
import type { Identity } from '../api/types'
import { t } from '../i18n'
import { Row } from './patterns'
import { Chip } from './ui'
import { Button } from './ui/button'
import { Input } from './ui/input'

export default function PersonalEmail({ identities }: { identities: Identity[] }) {
  const link = useLinkIdentity()
  const [open, setOpen] = useState(false)
  const [email, setEmail] = useState('')
  const personal = identities.filter((identity) => identity.provider === 'email_link')

  return (
    <>
      {personal.map((identity) => (
        <Row
          key={identity.id}
          title={t('Личная почта')}
          value={identity.email}
          acts={
            identity.confirmed_at ? (
              <Chip tone="good" size="sm">
                {t('подтверждена')}
              </Chip>
            ) : (
              <span className="acad__inline">
                <Chip tone="warn" size="sm">
                  {t('ждёт подтверждения')}
                </Chip>
                <Button
                  variant="link"
                  size="sm"
                  disabled={link.isPending}
                  onClick={() =>
                    link.mutate(identity.email, {
                      onSuccess: (result) => toast.success(result.detail),
                      onError: (error) => toast.error(error.message),
                    })
                  }
                >
                  {t('Выслать письмо заново')}
                </Button>
              </span>
            )
          }
        />
      ))}
      {!open ? (
        <Row
          title={personal.length ? t('Другая личная почта') : t('Личная почта')}
          value={personal.length ? null : t('не привязана')}
          acts={
            <Button variant="outline" size="sm" onClick={() => setOpen(true)}>
              {t('Добавить')}
            </Button>
          }
        />
      ) : (
        <form
          className="acad__actions"
          onSubmit={(event) => {
            event.preventDefault()
            link.mutate(email, {
              onSuccess: (result) => {
                toast.success(result.detail)
                setEmail('')
                setOpen(false)
              },
              onError: (error) => toast.error(error.message),
            })
          }}
        >
          <Input
            type="email"
            required
            value={email}
            aria-label={t('Личная почта')}
            placeholder="you@gmail.com"
            onChange={(event) => setEmail(event.target.value)}
          />
          <Button size="sm" type="submit" disabled={link.isPending}>
            {t('Прислать письмо')}
          </Button>
          <Button variant="ghost" size="sm" type="button" onClick={() => setOpen(false)}>
            {t('Отмена')}
          </Button>
        </form>
      )}
    </>
  )
}
