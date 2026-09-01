/**
 * Меню по клику на блок пользователя внизу бокового меню.
 *
 * Сверху — кто вошёл, ниже — язык, тема и личные действия. Язык и тема
 * сохраняются в профиле на сервере и переживают смену устройства.
 *
 * С фазы 32 это `DropdownMenu` из shadcn, а выбор языка и темы —
 * пункты с галочкой, а не плашки-переключатели: набор из трёх
 * взаимоисключающих значений и есть меню, и с клавиатуры оно теперь
 * работает само.
 */
import { useNavigate } from 'react-router-dom'
import Icon from '../layout/icons'
import { useUpdatePreferences } from '../api/hooks'
import { useAuth } from '../auth/AuthContext'
import { t } from '../i18n'
import { applyTheme, type ThemePref } from '../theme'
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
 * Инициалы для кружка-аватара: только буквы, максимум две.
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
 * Языки в переключателе. Подписи не переводятся: каждый язык подписан сам собой.
 *
 * Казахский словарь в коде остался целиком, но из выбора убран до вычитки
 * носителем: машинный черновик, выданный за перевод, хуже его отсутствия.
 * Как вернуть — в `docs/I18N.md`.
 */
export const LANGUAGES: { value: 'ru' | 'en'; label: string }[] = [
  { value: 'ru', label: 'Русский' },
  { value: 'en', label: 'English' },
]

export const THEMES: { value: ThemePref; label: string }[] = [
  { value: 'light', label: 'Светлая' },
  { value: 'dark', label: 'Тёмная' },
  { value: 'system', label: 'Как в системе' },
]

export default function ProfileMenu({
  user,
}: {
  /** Кто вошёл — подпись и роль рядом с аватаром внизу меню.
   *  Без неё остаётся один кружок с инициалами. */
  user?: { name: string; role: string }
}) {
  const { me, logout } = useAuth()
  const navigate = useNavigate()
  const prefs = useUpdatePreferences()
  if (!me) return null

  const setTheme = (value: ThemePref) => {
    applyTheme(value)
    prefs.mutate({ theme: value })
  }

  return (
    <DropdownMenu>
      {/* Блок пользователя и есть кнопка меню: аватар, имя с обрезкой,
          роль под ним и стрелка вверх. Отдельной кнопки «выход» рядом
          больше нет — по одному входу на каждое действие (фаза 48) */}
      <DropdownMenuTrigger className="pmenu__user" aria-label={t('Меню профиля')}>
        <span className="pmenu__avatar" aria-hidden="true">
          {initials(me.full_name, me.email)}
        </span>
        {user && (
          <span className="pmenu__usertext">
            <span className="pmenu__username">{user.name}</span>
            <span className="pmenu__userrole">{user.role}</span>
          </span>
        )}
        {user && <Icon name="chevronUp" size={14} />}
      </DropdownMenuTrigger>

      <DropdownMenuContent align="start" side="top" sideOffset={8} className="pmenu__panel">
        <div className="pmenu__head">
          <span className="pmenu__headavatar" aria-hidden="true">
            {initials(me.full_name, me.email)}
          </span>
          <span className="pmenu__headtext">
            <b className="pmenu__name">{me.full_name || me.email}</b>
            <span className="muted pmenu__mail">{me.email}</span>
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

        <DropdownMenuSeparator />
        {/* Подпись группы живёт только внутри группы: `Menu.GroupLabel`
            без `Menu.Group` бросает исключение при рендере, и до фазы 33
            от этого белел весь экран (ошибка прошлой фазы) */}
        <DropdownMenuGroup>
          <DropdownMenuLabel className="pmenu__grouptitle">{t('Язык')}</DropdownMenuLabel>
          {LANGUAGES.map((item) => (
            <DropdownMenuCheckboxItem
              key={item.value}
              className="pmenu__item"
              checked={me.language === item.value}
              closeOnClick={false}
              onClick={() => prefs.mutate({ language: item.value })}
            >
              {item.label}
            </DropdownMenuCheckboxItem>
          ))}
        </DropdownMenuGroup>

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
          {t('Выход')}
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
