/**
 * Обсуждение под задачей или эссе.
 *
 * Комментарии были в API с четвёртой фазы, а написать их было негде:
 * директор ставил задачу и не мог к ней ничего добавить, куратор читал
 * эссе и не мог оставить замечание иначе как в разговоре.
 *
 * Правило одно на оба вида: пишет любой, кому запись видна, а убирает
 * только автор — чужую реплику не переписывают и не стирают.
 */
import { useState } from 'react'
import { useRowComments } from '../api/hooks'
import { useAuth } from '../auth/AuthContext'
import { t } from '../i18n'
import { Input } from './ui/input'
import { Button } from './ui/button'

export default function RowComments({ kind, id }: { kind: 'task' | 'essay'; id: number }) {
  const { me } = useAuth()
  const { list, add, remove } = useRowComments(kind, id)
  const [text, setText] = useState('')

  const rows = list.data?.results ?? []
  const myName = me?.full_name || me?.email || ''

  return (
    <div className="comments">
      {rows.map((row) => (
        <div key={row.id} className="comments__item">
          <div>
            <b className="comments__who">{row.author_name}</b>
            <span className="muted comments__when"> {new Date(row.created_at).toLocaleDateString('ru')}</span>
            <p className="comments__text">{row.text}</p>
          </div>
          {row.author_name === myName && (
            <Button
              variant="outline"
              size="sm"
              disabled={remove.isPending}
              onClick={() => remove.mutate(row.id)}
            >
              {t('Убрать')}
            </Button>
          )}
        </div>
      ))}

      <div className="comments__form">
        <Input
          placeholder={t('Написать комментарий')}
          aria-label={t('Написать комментарий')}
          value={text}
          onChange={(event) => setText(event.target.value)}
        />
        <Button
          variant="outline"
          size="sm"
          disabled={add.isPending || text.trim() === ''}
          onClick={() =>
            add.mutate(text.trim(), {
              onSuccess: () => setText(''),
            })
          }
        >
          {t('Добавить')}
        </Button>
      </div>
    </div>
  )
}
