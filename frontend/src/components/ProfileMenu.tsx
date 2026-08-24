/**
 * Меню по клику на аватар в правом верхнем углу.
 *
 * Сверху — кто вошёл, ниже — язык, тема и личные действия. Язык и тема
 * сохраняются в профиле на сервере и переживают смену устройства.
 */
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useUpdatePreferences } from '../api/hooks'
import { useAuth } from '../auth/AuthContext'
import { t } from '../i18n'
import { applyTheme, type ThemePref } from '../theme'

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

export default function ProfileMenu() {
  const { me, logout } = useAuth()
  const navigate = useNavigate()
  const prefs = useUpdatePreferences()
  const [open, setOpen] = useState(false)
  if (!me) return null

  const go = (path: string) => {
    setOpen(false)
    navigate(path)
  }

  const setTheme = (value: ThemePref) => {
    applyTheme(value)
    prefs.mutate({ theme: value })
  }

  return (
    <div className="pmenu">
      <button
        className="pmenu__avatar"
        aria-label={t('Меню профиля')}
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        {initials(me.full_name, me.email)}
      </button>

      {open && (
        <>
          <div className="pmenu__back" role="presentation" onClick={() => setOpen(false)} />
          <div className="pmenu__panel card">
            <div className="pmenu__head">
              <b className="pmenu__name">{me.full_name || me.email}</b>
              <span className="muted pmenu__mail">{me.email}</span>
              <span className="muted pmenu__role">{me.role_title}</span>
            </div>

            <button className="pmenu__item" onClick={() => go('/profile')}>
              {t('Профиль')}
            </button>
            <button className="pmenu__item" onClick={() => go('/profile#password')}>
              {t('Смена пароля')}
            </button>

            <div className="pmenu__group">
              <span className="muted pmenu__grouptitle">{t('Язык')}</span>
              <div className="pmenu__options">
                {LANGUAGES.map((item) => (
                  <button
                    key={item.value}
                    className={`pmenu__option${me.language === item.value ? ' pmenu__option--active' : ''}`}
                    onClick={() => prefs.mutate({ language: item.value })}
                  >
                    {item.label}
                  </button>
                ))}
              </div>
            </div>

            <div className="pmenu__group">
              <span className="muted pmenu__grouptitle">{t('Тема')}</span>
              <div className="pmenu__options">
                {THEMES.map((item) => (
                  <button
                    key={item.value}
                    className={`pmenu__option${me.theme === item.value ? ' pmenu__option--active' : ''}`}
                    onClick={() => setTheme(item.value)}
                  >
                    {t(item.label)}
                  </button>
                ))}
              </div>
            </div>

            <button className="pmenu__item" onClick={() => void logout()}>
              {t('Выход')}
            </button>
          </div>
        </>
      )}
    </div>
  )
}
