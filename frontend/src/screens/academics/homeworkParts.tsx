/**
 * Общее для сдачи ДЗ на стороне учителя: срок словами по Алматы, опоздание
 * словами, файл работы с просмотром на месте.
 *
 * Файл отдаётся короткой подписанной ссылкой (`useFileLink`, живёт 5 минут):
 * аудио и видео играют по ней с перемоткой, картинка — как есть, PDF рисуется
 * постранично `pdfjs-dist` (грузится лениво, только когда PDF открыт).
 * Ссылка истекла — плеер или картинка падают с ошибкой, и экран берёт новую.
 */
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { toast } from 'sonner'
import type { PDFDocumentProxy, RenderTask } from 'pdfjs-dist'
import { fetchFileLink, useFileLink, type HomeworkFile } from '../../api/homework'
import { Button } from '../../components/ui/button'
import { t } from '../../i18n'
import { dayInSchoolZone, timeInSchoolZone } from '../../lib/dates'
import { dateWords } from './shared'
import './homework-review.css'

/** «1 октября, 08:00» — момент по времени школы. */
export function dueWords(iso: string | null | undefined): string {
  if (!iso) return ''
  const at = new Date(iso)
  return `${dateWords(dayInSchoolZone(at))}, ${timeInSchoolZone(at)}`
}

/** «40 мин», «2 ч 5 мин», «3 дн» — на сколько опоздала работа. */
export function lateSpan(minutes: number): string {
  if (minutes < 60) return `${minutes} ${t('мин')}`
  if (minutes < 24 * 60) {
    const hours = Math.floor(minutes / 60)
    const rest = minutes % 60
    return rest ? `${hours} ${t('ч')} ${rest} ${t('мин')}` : `${hours} ${t('ч')}`
  }
  return `${Math.floor(minutes / (24 * 60))} ${t('дн')}`
}

/** Первая строка текста задания — название в списках; пусто — запасное. */
export function firstLine(text: string, fallback: string): string {
  const line = text.split('\n').find((row) => row.trim())?.trim() ?? ''
  if (!line) return fallback
  return line.length > 80 ? `${line.slice(0, 78)}…` : line
}

/** «240 КБ», «1,2 МБ». */
export function sizeWords(bytes: number): string {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} ${t('КБ')}`
  return `${(bytes / (1024 * 1024)).toFixed(1).replace('.', ',')} ${t('МБ')}`
}

/** Метка вида файла: расширение из имени, иначе вид словом. */
function kindTag(file: HomeworkFile): string {
  const ext = file.name.includes('.') ? file.name.split('.').pop() ?? '' : ''
  if (ext && ext.length <= 5) return ext.toUpperCase()
  return { pdf: 'PDF', image: t('фото'), audio: t('аудио'), video: t('видео'), other: t('файл') }[file.kind]
}

/** Строка файла: метка вида, имя, размер. Кнопки — у вызывающего. */
export function FileLine({ file, children }: { file: HomeworkFile; children?: ReactNode }) {
  return (
    <div className="hwfile__head">
      <span className={`hwfile__tag hwfile__tag--${file.kind}`}>{kindTag(file)}</span>
      <span className="hwfile__name">{file.name}</span>
      <span className="hwfile__meta t-note">
        {sizeWords(file.size)}
        {file.photos ? ` · ${t('из')} ${file.photos} ${t('фото')}` : ''}
      </span>
      {children}
    </div>
  )
}

/** Скачать файл: свежая ссылка «как вложение» — старая могла истечь. */
export async function downloadHomeworkFile(id: number): Promise<void> {
  try {
    const fresh = await fetchFileLink(id, true)
    window.location.assign(fresh.url)
  } catch (error) {
    toast.error(error instanceof Error ? error.message : t('Файл не скачался — попробуйте ещё раз'))
  }
}

/** Страница PDF: рисуется, когда доезжает до экрана. */
function PdfPage({ doc, number }: { doc: PDFDocumentProxy; number: number }) {
  const box = useRef<HTMLDivElement>(null)
  const canvas = useRef<HTMLCanvasElement>(null)
  const [visible, setVisible] = useState(number <= 2)
  const [drawn, setDrawn] = useState(false)

  useEffect(() => {
    if (visible || !box.current) return
    const observer = new IntersectionObserver((entries) => {
      if (entries.some((entry) => entry.isIntersecting)) {
        setVisible(true)
        observer.disconnect()
      }
    })
    observer.observe(box.current)
    return () => observer.disconnect()
  }, [visible])

  useEffect(() => {
    if (!visible) return
    let alive = true
    let task: RenderTask | null = null
    void doc.getPage(number).then((page) => {
      const target = canvas.current
      if (!alive || !target || !box.current) return
      const base = page.getViewport({ scale: 1 })
      const width = box.current.clientWidth || base.width
      const ratio = window.devicePixelRatio || 1
      const viewport = page.getViewport({ scale: (width / base.width) * ratio })
      target.width = Math.floor(viewport.width)
      target.height = Math.floor(viewport.height)
      task = page.render({ canvas: target, viewport })
      task.promise.then(() => alive && setDrawn(true)).catch(() => undefined)
    })
    return () => {
      alive = false
      task?.cancel()
    }
  }, [doc, number, visible])

  return (
    <div ref={box} className={`hwpdf__page${drawn ? ' hwpdf__page--drawn' : ''}`}>
      <canvas ref={canvas} className="hwpdf__canvas" aria-label={`${t('Страница')} ${number}`} />
      <span className="hwpdf__num num">{number}</span>
    </div>
  )
}

/** PDF постранично. `pdfjs-dist` и его воркер грузятся только здесь. */
function PdfPages({ url, onBroken }: { url: string; onBroken: () => void }) {
  const [doc, setDoc] = useState<PDFDocumentProxy | null>(null)
  const [failed, setFailed] = useState(false)
  const broken = useRef(onBroken)
  broken.current = onBroken

  useEffect(() => {
    let alive = true
    let destroy: (() => Promise<void>) | null = null
    setDoc(null)
    setFailed(false)
    void (async () => {
      try {
        const [pdfjs, worker] = await Promise.all([import('pdfjs-dist'), import('pdfjs-dist/build/pdf.worker.min.mjs?url')])
        pdfjs.GlobalWorkerOptions.workerSrc = worker.default
        // файл целиком одним запросом: частичные запросы к бакету
        // упираются в CORS и в срок подписи
        const task = pdfjs.getDocument({ url, disableRange: true, disableStream: true })
        destroy = () => task.destroy()
        const loaded = await task.promise
        if (alive) setDoc(loaded)
      } catch {
        if (!alive) return
        setFailed(true)
        broken.current()
      }
    })()
    return () => {
      alive = false
      void destroy?.()
    }
  }, [url])

  if (failed) return <span className="t-note">{t('PDF не открылся — скачайте файл')}</span>
  if (!doc) return <span className="t-note">{t('Открываем PDF…')}</span>
  return (
    <div className="hwpdf">
      {Array.from({ length: doc.numPages }, (_, i) => (
        <PdfPage key={i + 1} doc={doc} number={i + 1} />
      ))}
    </div>
  )
}

/** Файл работы: строка с «Скачать» и просмотр на месте по виду файла. */
export function FileView({ file }: { file: HomeworkFile }) {
  const link = useFileLink(file.id)
  const url = link.data?.url
  // истёкшая ссылка — берём новую, но не бесконечно
  const [renewed, setRenewed] = useState(0)
  const renew = () => {
    if (renewed >= 2) return
    setRenewed((n) => n + 1)
    void link.refetch()
  }
  let body: ReactNode = null
  if (link.error) body = <span className="t-note">{t('Файл не открылся — скачайте его')}</span>
  else if (!url) body = <span className="t-note">{t('Загрузка…')}</span>
  else if (file.kind === 'pdf') body = <PdfPages url={url} onBroken={renew} />
  else if (file.kind === 'image') body = <img className="hwfile__img" src={url} alt={file.name} loading="lazy" onError={renew} />
  else if (file.kind === 'audio') body = <audio className="hwfile__audio" controls preload="metadata" src={url} onError={renew} />
  else if (file.kind === 'video') body = <video className="hwfile__video" controls preload="metadata" src={url} onError={renew} />
  return (
    <div className="hwfile">
      <FileLine file={file}>
        <Button variant="link" size="sm" onClick={() => void downloadHomeworkFile(file.id)}>
          {t('Скачать')}
        </Button>
      </FileLine>
      {body}
    </div>
  )
}
