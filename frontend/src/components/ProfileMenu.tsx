/**
 * Меню пользователя.
 *
 * На ноутбуке его открывает карточка внизу тёмного меню — аватар, имя,
 * роль и шеврон; на телефоне — аватар в тёмной полосе сверху. Внутри:
 * кто вошёл, профиль и пароль, уведомления и «Как начать», тема, выход.
 * Язык и тема сохраняются в профиле на сервере и переживают смену
 * устройства.
 *
 * Это `DropdownMenu` из shadcn, а выбор языка и темы — пункты с галочкой,
 * а не плашки-переключатели: набор из трёх взаимоисключающих значений
 * и есть меню, и с клавиатуры оно работает само.
 *
 * Список уведомлений живёт здесь же: его открывает пункт меню, а не
 * отдельный колокольчик. Непрочитанное видно и при закрытом меню —
 * точкой на аватаре.
 */
import { useState } from 'react'
import { useNavigate } from 'react-router'
import Icon from '../layout/icons'
import { useNotifications, useUpdatePreferences } from '../api/hooks'
import { useAuth } from '../auth/AuthContext'
import { deviceLanguage, t, tk } from '../i18n'
import { applyTheme, type ThemePref } from '../theme'
import type { Me } from '../api/types'
import Notifications from './Notifications'
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from './ui/dropdown-menu'

/** Слово целиком из букв — кириллица и латиница считаются одинаково. */
const LETTERS_ONLY = /^\p{L}+$/u

/**
 * Инициалы для плитки-аватара: только буквы, максимум две.
 *
 * Слово, в котором есть скобка, точка, дефис или цифра, пропускается
 * целиком: «Салтанат (тест)» даёт «СА», а не «С(». Без имени берём
 * буквы из почты — там тоже попадаются точки и цифры.
 */
export function initials(name: string, email: string): string {
  const words = name.split(/\s+/).filter((word) => LETTERS_ONLY.test(word))
  if (words.length >= 2) return (words[0][0] + words[1][0]).toUpperCase()
  if (words.length === 1) return words[0].slice(0, 2).toUpperCase()
  const letters = [...email].filter((char) => LETTERS_ONLY.test(char))
  return letters.slice(0, 2).join('').toUpperCase()
}

/**
 * Языки в переключателе — с сервера (`core.i18n.INTERFACE_LANGUAGES`): один
 * список на интерфейс и письма, и язык писем совпадает с языком интерфейса.
 * Подписи не переводятся: каждый язык подписан сам собой.
 */
export type Language = Me['languages'][number]

export function languagesOf(me: Pick<Me, 'languages'> | null | undefined): Language[] {
  // eslint-disable-next-line i18n-text -- язык подписан сам собой и не переводится
  return me?.languages?.length ? me.languages : [{ value: 'ru', label: 'Русский' }]
}

/** Язык из настроек человека, если он ещё предлагается; иначе русский.
 *  До входа — язык устройства (`deviceLanguage`). */
export function offeredLanguage(me: Pick<Me, 'language' | 'languages'> | null | undefined): Language['value'] {
  if (!me) return deviceLanguage()
  const saved = me.language
  return languagesOf(me).some((item) => item.value === saved) && saved ? saved : 'ru'
}

export const THEMES: { value: ThemePref; label: string }[] = [
  { value: 'light', label: tk('Светлая') },
  { value: 'dark', label: tk('Тёмная') },
  { value: 'system', label: tk('Как в системе') },
]

export default function ProfileMenu({
  user,
  onGuide,
  side = 'top',
  align = 'start',
}: {
  /** Кто вошёл — подпись и роль рядом с аватаром в карточке внизу меню.
   *  Без неё остаётся одна плитка с инициалами — так в полосе телефона. */
  user?: { name: string; role: string }
  /** «Как начать»: показать три шага первого входа ещё раз */
  onGuide?: () => void
  /** куда раскрывается меню: вверх от карточки внизу, вниз от аватара в полосе */
  side?: 'top' | 'bottom'
  align?: 'start' | 'end'
}) {
  const { me, logout } = useAuth()
  const navigate = useNavigate()
  const prefs = useUpdatePreferences()
  const notifications = useNotifications()
  const [notifOpen, setNotifOpen] = useState(false)
  if (!me) return null

  const unread = notifications.data?.unread ?? 0
  const languages = languagesOf(me)

  const setTheme = (value: ThemePref) => {
    applyTheme(value)
    prefs.mutate({ theme: value })
  }

  return (
    <>
      <DropdownMenu>
        {/* Карточка пользователя и есть кнопка меню: аватар, имя с обрезкой,
            роль под ним и шеврон. По одному входу на каждое действие —
            отдельных кнопок выхода и уведомлений рядом нет */}
        <DropdownMenuTrigger
          className={`pmenu__user${user ? '' : ' pmenu__user--avatar'}`}
          aria-label={t('Меню профиля')}
        >
          <span className="pmenu__avatar" aria-hidden="true">
            {initials(me.full_name, me.email ?? me.login ?? '')}
            {unread > 0 && <span className="pmenu__dot" />}
          </span>
          {user && (
            <span className="pmenu__usertext">
              <span className="pmenu__username">{user.name}</span>
              <span className="pmenu__userrole">{user.role}</span>
            </span>
          )}
          {user && <Icon name="chevronDown" size={15} />}
        </DropdownMenuTrigger>

        <DropdownMenuContent align={align} side={side} sideOffset={8} className="pmenu__panel profilemenu">
          <div className="pmenu__head">
            <span className="pmenu__headavatar" aria-hidden="true">
              {initials(me.full_name, me.email ?? me.login ?? '')}
            </span>
            <span className="pmenu__headtext">
              <b className="pmenu__name">{me.full_name || me.email || me.login}</b>
              <span className="muted pmenu__mail">{me.email || me.login}</span>
            </span>
          </div>

          <DropdownMenuSeparator />
          <DropdownMenuItem className="pmenu__item" onClick={() => navigate('/profile')}>
            <Icon name="person" size={15} />
            {t('Профиль')}
          </DropdownMenuItem>
          <DropdownMenuItem className="pmenu__item" onClick={() => navigate('/profile#password')}>
            <Icon name="lock" size={15} />
            {t('Смена пароля')}
          </DropdownMenuItem>
          {/* «Мои группы» — только у куратора: у остальных ролей групп нет */}
          {me.role === 'curator' && (
            <DropdownMenuItem className="pmenu__item" onClick={() => navigate('/my-groups')}>
              <Icon name="people" size={15} />
              {t('Мои группы')}
            </DropdownMenuItem>
          )}

          {/* Уведомления и подсказка первого входа: шапки на ноутбуке нет,
              и обе живут здесь — там же, где остальное личное */}
          <DropdownMenuSeparator />
          <DropdownMenuItem className="pmenu__item" onClick={() => setNotifOpen(true)}>
            <Icon name="bell" size={15} />
            { }
            {t('Уведомления')}
            {unread > 0 && <span className="pmenu__count num">{unread}</span>}
          </DropdownMenuItem>
          {onGuide && (
            <DropdownMenuItem className="pmenu__item" onClick={onGuide}>
              <Icon name="bulb" size={15} />
              {t('Как начать')}
            </DropdownMenuItem>
          )}

          {/* Подпись группы живёт только внутри группы: `Menu.GroupLabel`
              без `Menu.Group` бросает исключение при рендере, и от этого
              белел весь экран. Выбор из одного языка не показывается —
              переключать нечего */}
          {languages.length > 1 && (
            <>
              <DropdownMenuSeparator />
              <DropdownMenuGroup>
                <DropdownMenuLabel className="pmenu__grouptitle">{t('Язык')}</DropdownMenuLabel>
                {languages.map((item) => (
                  <DropdownMenuCheckboxItem
                    key={item.value}
                    className="pmenu__item"
                    checked={offeredLanguage(me) === item.value}
                    closeOnClick={false}
                    onClick={() => prefs.mutate({ language: item.value })}
                  >
                    {item.label}
                  </DropdownMenuCheckboxItem>
                ))}
              </DropdownMenuGroup>
            </>
          )}

          <DropdownMenuSeparator />
          <DropdownMenuGroup>
            <DropdownMenuLabel className="pmenu__grouptitle">{t('Тема')}</DropdownMenuLabel>
            {THEMES.map((item) => (
              <DropdownMenuCheckboxItem
                key={item.value}
                className="pmenu__item"
                checked={me.theme === item.value}
                closeOnClick={false}
                onClick={() => setTheme(item.value)}
              >
                {t(item.label)}
              </DropdownMenuCheckboxItem>
            ))}
          </DropdownMenuGroup>

          <DropdownMenuSeparator />
          <DropdownMenuItem className="pmenu__item" onClick={() => void logout()}>
            <Icon name="logout" size={15} />
            {t('Выйти')}
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      <Notifications open={notifOpen} onOpenChange={setNotifOpen} />
    </>
  )
}
