/**
 * Поиск по системе — в шапке, с любого экрана.
 *
 * Находит только то, что роли положено видеть: список фильтрует сервер,
 * а не интерфейс. Результаты сгруппированы по типу — вперемешку люди
 * и вузы не читаются.
 *
 * Горячая клавиша: Ctrl+K (Cmd+K на макбуке), Escape закрывает.
 */
import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useSearch } from '../api/hooks'
import { t } from '../i18n'

export default function SearchBox() {
  const navigate = useNavigate()
  const [query, setQuery] = useState('')
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(0)
  const inputRef = useRef<HTMLInputElement>(null)
  const boxRef = useRef<HTMLDivElement>(null)
  const { data, isFetching } = useSearch(query)

  // все найденные строки подряд — по ним ходят стрелками
  const flat = (data?.groups ?? []).flatMap((group) => group.rows)

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault()
        inputRef.current?.focus()
        inputRef.current?.select()
        setOpen(true)
      }
      if (event.key === 'Escape') setOpen(false)
    }
    const onClick = (event: MouseEvent) => {
      if (boxRef.current && !boxRef.current.contains(event.target as Node)) setOpen(false)
    }
    window.addEventListener('keydown', onKey)
    document.addEventListener('mousedown', onClick)
    return () => {
      window.removeEventListener('keydown', onKey)
      document.removeEventListener('mousedown', onClick)
    }
  }, [])

  const go = (path: string) => {
    setOpen(false)
    setQuery('')
    navigate(path)
  }

  return (
    <div className="search" ref={boxRef}>
      <input
        ref={inputRef}
        className="input search__input"
        type="search"
        value={query}
        placeholder={t('Поиск: ученик, вуз, программа')}
        aria-label={t('Поиск по системе')}
        onChange={(event) => {
          setQuery(event.target.value)
          setActive(0)
          setOpen(true)
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={(event) => {
          if (event.key === 'ArrowDown') {
            event.preventDefault()
            setActive((n) => Math.min(n + 1, flat.length - 1))
          }
          if (event.key === 'ArrowUp') {
            event.preventDefault()
            setActive((n) => Math.max(n - 1, 0))
          }
          if (event.key === 'Enter' && flat[active]) go(flat[active].path)
        }}
      />
      <span className="search__hint" aria-hidden="true">
        Ctrl+K
      </span>

      {open && query.trim().length > 0 && (
        <div className="search__drop" role="listbox" aria-label={t('Результаты поиска')}>
          {data && data.total === 0 && !isFetching && (
            <p className="muted search__empty">
              {data.detail || 'Ничего не нашлось'}
              {data.query.length >= 2 && ' — попробуйте другое слово или часть названия'}
            </p>
          )}
          {isFetching && !data && <p className="muted search__empty">{t('Ищем…')}</p>}

          {(data?.groups ?? []).map((group) => (
            <div key={group.code} className="search__group">
              <span className="eyebrow search__grouptitle">{group.title}</span>
              {group.rows.map((row) => {
                const index = flat.findIndex((item) => item.path === row.path && item.title === row.title)
                return (
                  <button
                    key={`${group.code}-${row.id}`}
                    className={`search__row${index === active ? ' search__row--active' : ''}`}
                    role="option"
                    aria-selected={index === active}
                    onMouseEnter={() => setActive(index)}
                    onClick={() => go(row.path)}
                  >
                    <span className="search__title">{row.title}</span>
                    <span className="muted search__note">{row.note}</span>
                  </button>
                )
              })}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
