/**
 * Поиск по системе — в шапке, с любого экрана.
 *
 * Находит только то, что роли положено видеть: список фильтрует сервер,
 * а не интерфейс. Результаты сгруппированы по типу — вперемешку люди
 * и вузы не читаются.
 *
 * Горячая клавиша: Ctrl+K (Cmd+K на макбуке), Escape закрывает.
 *
 * С фазы 32 подсказки рисует `Command` из shadcn: ходьба стрелками,
 * подсветка текущей строки и выбор по Enter — его, а не наши тридцать
 * строк с индексом активного элемента. Отбор он не делает (`shouldFilter`
 * выключен): что показывать, решает сервер по роли, и фильтровать выдачу
 * второй раз на клиенте нельзя — так ученик увидел бы одноклассников.
 */
import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useSearch } from '../api/hooks'
import { t } from '../i18n'
import { Command, CommandGroup, CommandInput, CommandItem, CommandList } from './ui/command'

export default function SearchBox() {
  const navigate = useNavigate()
  const [query, setQuery] = useState('')
  const [open, setOpen] = useState(false)
  const boxRef = useRef<HTMLDivElement>(null)
  const { data, isFetching } = useSearch(query)

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault()
        boxRef.current?.querySelector('input')?.focus()
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

  const groups = data?.groups ?? []
  const dropped = open && query.trim().length > 0

  return (
    <div className="search" ref={boxRef}>
      {/* `label` — скрытая подпись, на которую cmdk ссылается через aria-labelledby;
          без неё ссылка ведёт в пустоту, и у поля нет имени для читалки экрана */}
      <Command shouldFilter={false} loop className="search__cmd" label={t('Поиск по системе')}>
        <CommandInput
          value={query}
          placeholder={t('Поиск: ученик, вуз, программа')}
          aria-label={t('Поиск по системе')}
          onValueChange={(value) => {
            setQuery(value)
            setOpen(true)
          }}
          onFocus={() => setOpen(true)}
        />
        <span className="search__hint" aria-hidden="true">
          Ctrl+K
        </span>

        {dropped && (
          <div className="search__drop">
            <CommandList className="search__list">
              {data && data.total === 0 && !isFetching && (
                <p className="muted search__empty">
                  {data.detail || 'Ничего не нашлось'}
                  {data.query.length >= 2 && ' — попробуйте другое слово или часть названия'}
                </p>
              )}
              {isFetching && !data && <p className="muted search__empty">{t('Ищем…')}</p>}

              {groups.map((group) => (
                <CommandGroup key={group.code} heading={group.title} className="search__group">
                  {group.rows.map((row) => (
                    <CommandItem
                      key={`${group.code}-${row.id}`}
                      value={`${group.code}-${row.id}`}
                      className="search__row"
                      onSelect={() => go(row.path)}
                    >
                      <span className="search__title">{row.title}</span>
                      <span className="muted search__note">{row.note}</span>
                    </CommandItem>
                  ))}
                </CommandGroup>
              ))}
            </CommandList>
          </div>
        )}
      </Command>
    </div>
  )
}
