/**
 * Карточка одного материала: описание, файлы, «было полезно», вопросы.
 *
 * Файлы открываются через `/api/materials/files/<id>/` — прямой ссылки
 * на файл не существует, сервер каждый раз проверяет права (фаза 19).
 */
import { useState } from 'react'
import { useMaterial, useMaterialActions, useMaterialComments, useMaterialsState } from '../api/hooks'
import { ErrorNote, Loading } from './ui'
import { t } from '../i18n'
import { Input } from './ui/input'
import { Button } from './ui/button'
import { Badge } from './ui/badge'

export default function MaterialCard({ id, onBack }: { id: number; onBack: () => void }) {
  const material = useMaterial(id)
  const comments = useMaterialComments(id)
  const state = useMaterialsState()
  const actions = useMaterialActions()
  const [text, setText] = useState('')
  const [complaint, setComplaint] = useState('')
  const [flash, setFlash] = useState<string | null>(null)

  if (material.isLoading) return <Loading />
  if (material.isError) return <ErrorNote error={material.error} />
  if (!material.data) return null

  const row = material.data
  const rows = comments.data?.results ?? []

  return (
    <div>
      <Button variant="outline" size="sm" onClick={onBack}>
        {t('← К материалам')}
      </Button>

      {flash && (
        <Badge variant="ok" className="badge--line mat__flash">
          {flash}
        </Badge>
      )}

      <div className="card card-pad mat__single">
        <span className="eyebrow">
          {row.subject_name} · {row.topic}
        </span>
        <h1 className="mat__bigtitle">{row.title}</h1>
        <div className="mat__meta">
          <Badge variant="mute">{row.author_name}</Badge>
          <Badge variant="mute">{row.source_kind_title}</Badge>
          <Badge variant="mute">{new Date(row.created_at).toLocaleDateString('ru')}</Badge>
          {row.status !== 'approved' && <Badge variant="warn">{row.status_title}</Badge>}
        </div>

        {row.status === 'rejected' && row.reject_reason && (
          <Badge variant="risk" className="badge--line mat__reason">
            Не прошёл проверку: {row.reject_reason}
          </Badge>
        )}

        {row.description && <p className="mat__desc">{row.description}</p>}

        <h2 className="section">{t('Файлы')}</h2>
        {row.files.length === 0 ? (
          <p className="muted">{t('Файлов нет — материал только текстом.')}</p>
        ) : (
          <ul className="rows__list">
            {row.files.map((file) => (
              <li key={file.id} className="rows__item">
                <a className="link" href={file.url} target="_blank" rel="noreferrer">
                  {file.original_name}
                </a>
                <span className="muted rows__note">{file.size_human}</span>
              </li>
            ))}
          </ul>
        )}

        <div className="toolbar mat__actions">
          {row.status === 'approved' && (
            <Button
              variant={row.marked_helpful ? undefined : 'outline'}
              size="sm"
              onClick={() =>
                actions.helpful.mutate(row.id, {
                  onSuccess: (answer) => setFlash(answer.marked ? 'Спасибо, отметили' : 'Отметка снята'),
                })
              }
            >
              {row.marked_helpful ? '✓ Было полезно' : 'Было полезно'}
              {row.helpful_count > 0 && <span className="num"> · {row.helpful_count}</span>}
            </Button>
          )}
        </div>
      </div>

      <div className="card card-pad">
        <span className="eyebrow">{t('Вопросы и замечания')}</span>
        {rows.length === 0 && <p className="muted">{t('Пока никто ничего не спросил.')}</p>}
        <ul className="rows__list">
          {rows.map((comment) => (
            <li key={comment.id} className="rows__item">
              <div>
                <span className="rows__label">{comment.author_name}</span>
                <span className="muted rows__note">
                  {' '}
                  · {new Date(comment.created_at).toLocaleString('ru')}
                </span>
                <p className="mat__comment">{comment.text}</p>
              </div>
              {(comment.is_mine || row.can_moderate) && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() =>
                    actions.removeComment.mutate(comment.id, {
                      onSuccess: () => setFlash('Комментарий убран'),
                    })
                  }
                >
                  {t('Убрать')}
                </Button>
              )}
            </li>
          ))}
        </ul>

        <div className="toolbar mat__ask">
          <Input
            placeholder={t('Спросить автора')}
            aria-label={t('Вопрос автору')}
            value={text}
            onChange={(event) => setText(event.target.value)}
          />
          <Button
            size="sm"
            disabled={!text.trim()}
            onClick={() =>
              actions.comment.mutate(
                { material: row.id, text: text.trim() },
                {
                  onSuccess: () => {
                    setText('')
                    setFlash('Вопрос отправлен — автор и директор талантов его увидят')
                  },
                },
              )
            }
          >
            {t('Спросить')}
          </Button>
        </div>
      </div>

      {!state.data?.is_curator && (
        <div className="card card-pad mat__complain">
          <span className="eyebrow">{t('Пожаловаться')}</span>
          <p className="muted">
            {t(
              'Если материал выложен без права на публикацию или в нём что-то не то — напишите. Жалобу разбирает директор талантов.',
            )}
          </p>
          <div className="toolbar">
            <Input
              placeholder={t('В чём дело')}
              aria-label={t('Причина жалобы')}
              value={complaint}
              onChange={(event) => setComplaint(event.target.value)}
            />
            <Button
              variant="outline"
              size="sm"
              disabled={!complaint.trim()}
              onClick={() =>
                actions.report.mutate(
                  { material: row.id, reason: complaint.trim() },
                  {
                    onSuccess: () => {
                      setComplaint('')
                      setFlash('Жалоба ушла директору талантов')
                    },
                  },
                )
              }
            >
              {t('Отправить')}
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}
