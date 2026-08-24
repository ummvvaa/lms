/**
 * Эссе: версии, статусы, комментарии куратора.
 * Редактор без ИИ-генерации — на этой фазе ИИ к эссе не подключается вообще.
 */
import { useState } from 'react'
import { useAddEssayVersion, useMyEssays, type Essay } from '../api/hooks'
import Empty from '../components/Empty'
import { ErrorNote, Loading, ScreenHead } from '../components/ui'
import { t } from '../i18n'

const STATUS_TONE: Record<string, string> = {
  draft: 'chip-mute',
  review: 'chip-warn',
  revision: 'chip-risk',
  done: 'chip-ok',
}
const STATUS_TITLE: Record<string, string> = {
  draft: 'черновик',
  review: 'на проверке',
  revision: 'правки',
  done: 'готово',
}

function Editor({ essay }: { essay: Essay }) {
  const current = essay.versions[0]
  const [text, setText] = useState(current?.text ?? '')
  const addVersion = useAddEssayVersion()
  const words = text.trim() ? text.trim().split(/\s+/).length : 0

  return (
    <div className="card card-pad" style={{ marginTop: 12 }}>
      <textarea
        className="essay__editor"
        value={text}
        onChange={(e) => setText(e.target.value)}
        rows={14}
        placeholder={t('Пишите здесь. Текст сохраняется отдельной версией — прежние остаются в истории.')}
      />
      <div className="toolbar" style={{ marginTop: 12, marginBottom: 0 }}>
        <span className="chip chip-mute num">{words} слов</span>
        {essay.versions.length > 0 && (
          <span className="muted" style={{ fontSize: 12.5 }}>
            версий: {essay.versions.length}, последняя от{' '}
            {new Date(essay.versions[0].created_at).toLocaleDateString('ru')}
          </span>
        )}
        <span className="toolbar__spacer" />
        <button
          className="btn btn-primary btn-sm"
          onClick={() => addVersion.mutate({ id: essay.id, text })}
          disabled={addVersion.isPending || text.trim() === ''}
        >
          {t('Сохранить версию')}
        </button>
      </div>

      {essay.comments.length > 0 && (
        <div style={{ marginTop: 18, paddingTop: 16, borderTop: '1px solid var(--line)' }}>
          <span className="eyebrow">{t('Комментарии куратора')}</span>
          {essay.comments.map((comment) => (
            <div key={comment.id} style={{ marginTop: 12, fontSize: 13 }}>
              <b>{comment.author_name}</b>{' '}
              <span className="muted" style={{ fontSize: 12 }}>
                {new Date(comment.created_at).toLocaleDateString('ru')}
              </span>
              <p style={{ margin: '4px 0 0' }}>{comment.text}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export default function Essays() {
  const { data, isLoading, error } = useMyEssays()
  const [openId, setOpenId] = useState<number | null>(null)

  if (isLoading) return <Loading />
  if (error) return <ErrorNote error={error} />

  const essays = data?.results ?? []

  return (
    <div>
      <ScreenHead title={t('Эссе')} subtitle={t('Черновики, версии и замечания куратора.')} />

      {essays.length === 0 && (
        <Empty
          title={t('Эссе ещё не заведены')}
          what={t(
            'Эссе создаёт куратор — под конкретную программу или общее. Дальше вы пишете версии здесь: каждая сохраняется отдельно, и к ней остаются замечания куратора.',
          )}
        />
      )}

      {essays.map((essay) => (
        <section key={essay.id} style={{ marginBottom: 16 }}>
          <button
            className="card card-pad essay__head"
            onClick={() => setOpenId(openId === essay.id ? null : essay.id)}
          >
            <div>
              <b style={{ fontSize: 15 }}>{essay.title}</b>
              <p className="muted" style={{ margin: '4px 0 0', fontSize: 12.5 }}>
                {essay.program_name ?? 'Общее эссе'} · {essay.versions.length} версий
              </p>
            </div>
            <span className={`chip ${STATUS_TONE[essay.status]}`}>{STATUS_TITLE[essay.status]}</span>
          </button>
          {openId === essay.id && <Editor essay={essay} />}
        </section>
      ))}
    </div>
  )
}
