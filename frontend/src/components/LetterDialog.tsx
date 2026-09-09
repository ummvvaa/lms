/**
 * Письмо ученику или родителям (фаза 66).
 *
 * Система писем не отправляет. Она собирает заготовку — тему и текст
 * из школьного шаблона на языке группы — и открывает почтовый клиент
 * того, кто нажал кнопку. Письмо уходит от живого человека, с его
 * адреса и подписи, и остаётся у него в «отправленных»: родителю есть
 * кому ответить.
 *
 * Отсюда две вещи, которые видно на экране. Текст правится руками —
 * шаблон это заготовка, а не бланк. И подпись под кнопкой говорит
 * правду: система знает, что письмо открыли, и не знает, что его
 * отправили.
 *
 * Адресов больше полусотни — режем на несколько писем: длинный список
 * почтовые клиенты обрезают молча, и половина родителей не получит
 * ничего, а отправитель об этом не узнает.
 */
import { useEffect, useState } from 'react'
import { toast } from 'sonner'
import { useComposeLetter, useOpenLetter } from '../api/hooks'
import Modal from './Modal'
import { Badge } from './ui/badge'
import { Button } from './ui/button'
import { Input } from './ui/input'
import { Textarea } from './ui/textarea'
import { t } from '../i18n'

export type LetterKind = 'document' | 'goal' | 'mock' | 'task' | 'free'

export interface LetterTarget {
  /** кому пишем: ученики, чьи адреса или адреса родителей возьмёт сервер */
  students: number[]
  kind: LetterKind
  /** «что просим» — подставляется в шаблон */
  ask?: string
  due?: string
  title?: string
}

export default function LetterDialog({ target, onClose }: { target: LetterTarget; onClose: () => void }) {
  const compose = useComposeLetter()
  const open = useOpenLetter()
  const [audience, setAudience] = useState<'student' | 'parent'>('student')
  const [subject, setSubject] = useState('')
  const [body, setBody] = useState('')
  const [links, setLinks] = useState<string[]>([])
  const [sent, setSent] = useState(0)

  // заготовку берём с сервера: шаблоны школьные, и язык — группы
  useEffect(() => {
    compose.mutate(
      {
        students: target.students,
        kind: target.kind,
        audience,
        ask: target.ask ?? '',
        due: target.due ?? '',
      },
      {
        onSuccess: (data) => {
          setSubject(data.subject)
          setBody(data.body)
          setLinks([])
          setSent(0)
        },
        onError: (error) => toast.error(error.message),
      },
    )
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [audience, target.students.join(','), target.kind])

  const draft = compose.data
  const without = draft?.without_email ?? []

  const openInMail = () => {
    open.mutate(
      { students: target.students, audience, subject, body },
      {
        onSuccess: (data) => {
          setLinks(data.links)
          setSent(1)
          window.location.href = data.links[0]
          toast.info(t('Письмо открыто в почте. Отправку система не видит'))
        },
        onError: (error) => toast.error(error.message),
      },
    )
  }

  const next = () => {
    window.location.href = links[sent]
    setSent(sent + 1)
  }

  return (
    <Modal title={target.title ?? t('Письмо')} onClose={onClose} wide>
      <div className="letter">
        <div className="letter__who">
          <Button
            size="sm"
            variant={audience === 'student' ? 'default' : 'outline'}
            onClick={() => setAudience('student')}
          >
            {t('Ученику')}
          </Button>
          <Button
            size="sm"
            variant={audience === 'parent' ? 'default' : 'outline'}
            onClick={() => setAudience('parent')}
          >
            {t('Родителям')}
          </Button>
          <span className="cfilters__spacer" />
          <Badge variant="mute" className="num">
            {t('Получателей:')} {draft?.recipients.length ?? 0}
          </Badge>
          {without.length > 0 && (
            <Badge variant="warn" className="num">
              {t('без почты:')} {without.length}
            </Badge>
          )}
        </div>

        {compose.isPending && <p className="muted">{t('Собираю письмо…')}</p>}

        <label className="letter__field">
          <span className="eyebrow">{t('Тема')}</span>
          <Input
            value={subject}
            aria-label={t('Тема')}
            onChange={(event) => setSubject(event.target.value)}
          />
        </label>
        <label className="letter__field">
          <span className="eyebrow">{t('Текст')}</span>
          <Textarea
            rows={10}
            value={body}
            aria-label={t('Текст')}
            onChange={(event) => setBody(event.target.value)}
          />
        </label>

        {without.length > 0 && (
          <div className="letter__without">
            <span className="eyebrow">{t('Без почты — им письмо не уйдёт')}</span>
            <ul>
              {without.map((row) => (
                <li key={row.student}>
                  <a href={`/students/${row.student}`}>{row.full_name}</a>
                </li>
              ))}
            </ul>
          </div>
        )}

        {(draft?.batches.length ?? 0) > 1 && (
          <p className="muted">
            {t('Адресов больше, чем помещается в одно письмо. Оно разбито на части:')}{' '}
            {draft?.batches.join(' + ')}
          </p>
        )}

        <div className="ctask__actions">
          <span className="muted">
            {t('Система откроет почту. Отправку она не видит и подтвердить не может')}
          </span>
          <span className="cfilters__spacer" />
          {links.length === 0 && (
            <Button disabled={open.isPending || !subject.trim()} onClick={openInMail}>
              {t('Открыть в почте')}
            </Button>
          )}
          {links.length > 0 && sent < links.length && (
            <Button onClick={next}>
              {t('Следующие')} ({sent + 1}/{links.length})
            </Button>
          )}
          {links.length > 0 && sent >= links.length && <Badge variant="ok">{t('Все письма открыты')}</Badge>}
        </div>
      </div>
    </Modal>
  )
}
