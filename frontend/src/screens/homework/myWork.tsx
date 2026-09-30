/**
 * Сдача ДЗ глазами ученика: сроки словами, файлы строками, склейка фото
 * в один PDF и запись звука — общее для списка и экрана задания.
 *
 * Время — по Алматы, а не по часам браузера: срок «до 20:00» у ученика
 * в поездке остаётся школьным. Сколько сдали одноклассники, здесь не
 * считается и не показывается нигде (решение владельца).
 */
import { useEffect, useRef, useState } from 'react'
import { toast } from 'sonner'
import { fetchFileLink, type HomeworkFile, type HomeworkLimits, type MyHomework } from '../../api/homework'
import { Row } from '../../components/patterns'
import { Chip, Kpi, plural, type Tone } from '../../components/ui'
import { Button } from '../../components/ui/button'
import Icon from '../../layout/icons'
import { t } from '../../i18n'
import { dayInSchoolZone, timeInSchoolZone } from '../../lib/dates'
import { dateWords } from '../academics/shared'
import { dueWords as teacherDueWords, sizeWords as teacherSizeWords } from '../academics/homeworkParts'

/* --- Время ------------------------------------------------------------------ */

const MINUTE = 60 * 1000

/** «30 сентября, 20:00» — то же слово, что у учителя (`homeworkParts.dueWords`). */
export function whenWords(iso: string): string {
  return teacherDueWords(iso)
}

/** День относительно сегодня по Алматы: 0 — сегодня, 1 — завтра. */
function dayShift(iso: string, now: Date): number {
  const day = Date.parse(dayInSchoolZone(new Date(iso)))
  const today = Date.parse(dayInSchoolZone(now))
  return Math.round((day - today) / (24 * 60 * MINUTE))
}

/** Срок словами: «сегодня, 30 сентября, 20:00», «завтра, …» или просто дата. */
export function dueWords(iso: string, now = new Date()): string {
  const shift = dayShift(iso, now)
  if (shift === 0) return `${t('сегодня')}, ${whenWords(iso)}`
  if (shift === 1) return `${t('завтра')}, ${whenWords(iso)}`
  return whenWords(iso)
}

/** До срока: «14:00» сегодня, иначе с датой. */
export function dueShort(iso: string, now = new Date()): string {
  return dayShift(iso, now) === 0 ? timeInSchoolZone(new Date(iso)) : whenWords(iso)
}

/** Отрезок времени словами: «40 мин», «5 ч», «2 дня». */
export function spanWords(minutes: number): string {
  if (minutes < 60) return `${Math.max(1, minutes)} ${t('мин')}`
  if (minutes < 24 * 60) {
    const hours = Math.floor(minutes / 60)
    const rest = minutes % 60
    return rest && hours < 3 ? `${hours} ${t('ч')} ${rest} ${t('мин')}` : `${hours} ${t('ч')}`
  }
  const days = Math.floor(minutes / (24 * 60))
  return `${days} ${t(plural(days, ['день', 'дня', 'дней']))}`
}

/** Сколько осталось до срока — чипом: «осталось 5 ч», «завтра до 8:00», «3 дня до 3 октября». */
export function leftChip(item: Pick<MyHomework, 'due_at'>, now = new Date()): { label: string; tone: Tone } {
  if (!item.due_at) return { label: t('без срока'), tone: 'neutral' }
  const due = new Date(item.due_at)
  const minutes = Math.floor((due.getTime() - now.getTime()) / MINUTE)
  if (minutes < 0) return { label: t('срок прошёл'), tone: 'bad' }
  const shift = dayShift(item.due_at, now)
  if (shift === 0) return { label: `${t('осталось')} ${spanWords(minutes)}`, tone: 'bad' }
  if (shift === 1) return { label: `${t('завтра до')} ${timeInSchoolZone(due)}`, tone: 'warn' }
  return {
    label: `${shift} ${t(plural(shift, ['день', 'дня', 'дней']))} ${t('до')} ${dateWords(dayInSchoolZone(due))}`,
    tone: 'neutral',
  }
}

/** Прошло после срока, минут. */
export function minutesPast(iso: string | null, now = new Date()): number {
  if (!iso) return 0
  return Math.max(0, Math.floor((now.getTime() - new Date(iso).getTime()) / MINUTE))
}

/** «сдано 28 сентября, 21:14» или «сдано с опозданием на 2 ч». */
export function handedWords(submission: { submitted_at: string | null; late_minutes: number | null }): {
  chip: string
  tone: Tone
  when: string
} {
  const when = submission.submitted_at ? `${t('сдано')} ${whenWords(submission.submitted_at)}` : ''
  if (submission.late_minutes)
    return { chip: `${t('сдано с опозданием на')} ${spanWords(submission.late_minutes)}`, tone: 'warn', when }
  return { chip: t('на проверке'), tone: 'accent', when }
}

/** Кто задал и к какому уроку: «Сұлтан Н. · урок 29 сентября · подгруппа EEP-9-2». */
export function whoWords(item: MyHomework): string {
  const lesson = item.lesson
  const cohort =
    lesson.cohort_kind === 'subgroup'
      ? `${t('подгруппа')} ${lesson.cohort}`
      : lesson.cohort_kind === 'stream'
        ? `${t('поток')} ${lesson.cohort}`
        : ''
  return [lesson.teacher?.short ?? '', `${t('урок')} ${dateWords(lesson.date)}`, cohort]
    .filter(Boolean)
    .join(' · ')
}

/** Правило после срока короткой пометкой. */
export function policyChip(item: Pick<MyHomework, 'late_policy'>): { label: string; tone: Tone } {
  return item.late_policy === 'accept'
    ? { label: t('можно сдать позже, с пометкой'), tone: 'info' }
    : { label: t('после срока закрыто'), tone: 'neutral' }
}

/* --- Файлы ------------------------------------------------------------------ */

/** «1,2 МБ», «240 КБ» — один счёт размера с экранами учителя. */
export const sizeWords = teacherSizeWords

/** Ярлык типа: расширение имени, для фото и звука без расширения — вид файла. */
export function fileTag(file: Pick<HomeworkFile, 'name' | 'kind'>): string {
  const dot = file.name.lastIndexOf('.')
  const ext = dot > 0 ? file.name.slice(dot + 1) : ''
  if (ext && ext.length <= 5) return ext.toUpperCase()
  return file.kind.toUpperCase()
}

const KIND_TONE: Record<string, Tone> = {
  pdf: 'bad',
  image: 'info',
  audio: 'accent',
  video: 'neutral',
  other: 'neutral',
}

/**
 * Открыть файл короткой ссылкой. Окно открывается сразу по нажатию:
 * открытое после ответа сервера браузер телефона сочтёт всплывающим.
 */
export async function openFile(id: number) {
  const tab = window.open('', '_blank')
  try {
    const link = await fetchFileLink(id)
    if (tab) {
      tab.opener = null
      tab.location.href = link.url
    } else window.location.assign(link.url)
  } catch (error) {
    tab?.close()
    toast.error(error instanceof Error ? error.message : t('Файл не открылся — попробуйте ещё раз'))
  }
}

/** Файл строкой: ярлык типа, имя, размер; «Открыть» и, пока можно, «Убрать». */
export function FileRow({ file, onDrop, busy }: { file: HomeworkFile; onDrop?: () => void; busy?: boolean }) {
  return (
    <Row
      lead={
        <Chip tone={KIND_TONE[file.kind] ?? 'neutral'} size="sm">
          {fileTag(file)}
        </Chip>
      }
      title={<span className="mywork__name">{file.name}</span>}
      note={file.photos ? `${file.photos} ${t('фото')} · ${sizeWords(file.size)}` : sizeWords(file.size)}
      acts={
        <>
          <Button variant="secondary" size="sm" onClick={() => void openFile(file.id)}>
            {t('Открыть')}
          </Button>
          {onDrop && (
            <Button
              variant="ghost"
              size="icon-sm"
              aria-label={`${t('Убрать файл')} ${file.name}`}
              disabled={busy}
              onClick={onDrop}
            >
              <Icon name="close" size={15} />
            </Button>
          )}
        </>
      }
    />
  )
}

/** Файл учителя пилюлей в карточке задания: нажатие открывает. */
export function FilePill({ file }: { file: HomeworkFile }) {
  return (
    <Button variant="outline" size="sm" className="mywork__pill" onClick={() => void openFile(file.id)}>
      <Chip tone={KIND_TONE[file.kind] ?? 'neutral'} size="sm">
        {fileTag(file)}
      </Chip>
      <span className="mywork__name">{file.name}</span>
    </Button>
  )
}

/** Подсказка о пределах школы: те же числа, что проверяет сервер. */
export function limitsWords(limits: HomeworkLimits): string {
  return `${t('файл до')} ${limits.file_mb} ${t('МБ')}, ${t('видео до')} ${limits.video_mb} ${t('МБ')} · ${t('не больше')} ${limits.max_files} ${t(plural(limits.max_files, ['файла', 'файлов', 'файлов']))}`
}

/** Проверка до загрузки — теми же пределами, что и на сервере. Ответ — отказ словами или пусто. */
export function refuseFile(file: Blob & { name?: string }, limits: HomeworkLimits): string {
  const video = file.type.startsWith('video/')
  const cap = video ? limits.video_mb : limits.file_mb
  if (file.size <= 0) return `${t('Файл пустой')}: ${file.name ?? ''}`
  if (file.size > cap * 1024 * 1024)
    return `${video ? t('Видео') : t('Файл')} «${file.name ?? ''}» ${t('весит')} ${sizeWords(file.size)}, ${t('а можно до')} ${cap} ${t('МБ')}`
  return ''
}

/* --- Фото тетради одним PDF ---------------------------------------------------- */

/** Длинная сторона снимка после сжатия: страница тетради читается, файл не весит десятки мегабайт. */
const PHOTO_SIDE = 2000
const PHOTO_QUALITY = 0.8
/** Ширина страницы PDF — A4 в пунктах; высота — по пропорциям снимка. */
const PAGE_WIDTH = 595.28

/** Снимок, развёрнутый по EXIF: сначала `createImageBitmap`, где его нет — через картинку. */
async function decode(
  file: Blob,
): Promise<{ source: CanvasImageSource; width: number; height: number; done: () => void }> {
  try {
    const bitmap = await createImageBitmap(file, { imageOrientation: 'from-image' })
    return { source: bitmap, width: bitmap.width, height: bitmap.height, done: () => bitmap.close() }
  } catch {
    const url = URL.createObjectURL(file)
    const image = new Image()
    image.src = url
    await image.decode()
    return {
      source: image,
      width: image.naturalWidth,
      height: image.naturalHeight,
      done: () => URL.revokeObjectURL(url),
    }
  }
}

async function compress(file: Blob): Promise<{ bytes: Uint8Array; width: number; height: number }> {
  const picture = await decode(file)
  try {
    const scale = Math.min(1, PHOTO_SIDE / Math.max(picture.width, picture.height))
    const width = Math.max(1, Math.round(picture.width * scale))
    const height = Math.max(1, Math.round(picture.height * scale))
    const canvas = document.createElement('canvas')
    canvas.width = width
    canvas.height = height
    const context = canvas.getContext('2d')
    if (!context) throw new Error(t('Браузер не смог обработать фото — сдайте его файлом'))
    context.drawImage(picture.source, 0, 0, width, height)
    const blob = await new Promise<Blob | null>((resolve) =>
      canvas.toBlob(resolve, 'image/jpeg', PHOTO_QUALITY),
    )
    if (!blob) throw new Error(t('Браузер не смог обработать фото — сдайте его файлом'))
    return { bytes: new Uint8Array(await blob.arrayBuffer()), width, height }
  } finally {
    picture.done()
  }
}

/** Несколько снимков тетради — один PDF, страница на снимок. Библиотека грузится только здесь. */
export async function photosToPdf(files: Blob[]): Promise<Blob> {
  const { PDFDocument } = await import('@cantoo/pdf-lib')
  const doc = await PDFDocument.create()
  for (const file of files) {
    const photo = await compress(file)
    const image = await doc.embedJpg(photo.bytes)
    const height = (PAGE_WIDTH * photo.height) / photo.width
    const page = doc.addPage([PAGE_WIDTH, height])
    page.drawImage(image, { x: 0, y: 0, width: PAGE_WIDTH, height })
  }
  const bytes = await doc.save()
  return new Blob([bytes], { type: 'application/pdf' })
}

/* --- Запись звука --------------------------------------------------------------- */

/** Форматы по порядку: Chrome и Firefox пишут webm или ogg, Safari — mp4. */
const AUDIO_TYPES = ['audio/webm;codecs=opus', 'audio/mp4', 'audio/ogg;codecs=opus']

function audioExtension(type: string): string {
  if (type.includes('mp4')) return 'm4a'
  if (type.includes('ogg')) return 'ogg'
  return 'webm'
}

/** «audio-2026-09-30-1542.webm»: имя со словом audio сервер читает как звук, а не как видео webm. */
function audioName(type: string): string {
  const now = new Date()
  const time = timeInSchoolZone(now).replace(':', '')
  return `audio-${dayInSchoolZone(now)}-${time}.${audioExtension(type)}`
}

export function audioSupported(): boolean {
  return (
    typeof window !== 'undefined' &&
    typeof window.MediaRecorder !== 'undefined' &&
    Boolean(navigator.mediaDevices?.getUserMedia)
  )
}

/** Запись с микрофона: старт, стоп, отмена и секунды на таймере. Готовая запись уходит в `onDone`. */
export function useRecorder(onDone: (file: File) => void) {
  const [seconds, setSeconds] = useState(0)
  const [recording, setRecording] = useState(false)
  const recorder = useRef<MediaRecorder | null>(null)
  const stream = useRef<MediaStream | null>(null)
  const discard = useRef(false)
  const done = useRef(onDone)
  useEffect(() => {
    done.current = onDone
  }, [onDone])

  useEffect(() => {
    if (!recording) return
    const started = Date.now()
    const timer = window.setInterval(() => setSeconds(Math.floor((Date.now() - started) / 1000)), 500)
    return () => window.clearInterval(timer)
  }, [recording])

  // ушли с экрана посреди записи — микрофон отпускается, запись не сохраняется
  useEffect(
    () => () => {
      discard.current = true
      if (recorder.current?.state === 'recording') recorder.current.stop()
      stream.current?.getTracks().forEach((track) => track.stop())
    },
    [],
  )

  const start = async () => {
    let media: MediaStream
    try {
      media = await navigator.mediaDevices.getUserMedia({ audio: true })
    } catch {
      toast.error(t('Нет доступа к микрофону — разрешите его в настройках браузера'))
      return
    }
    const type = AUDIO_TYPES.find((candidate) => MediaRecorder.isTypeSupported(candidate)) ?? ''
    const next = type ? new MediaRecorder(media, { mimeType: type }) : new MediaRecorder(media)
    const chunks: Blob[] = []
    next.ondataavailable = (event) => {
      if (event.data.size) chunks.push(event.data)
    }
    next.onstop = () => {
      media.getTracks().forEach((track) => track.stop())
      setRecording(false)
      if (discard.current || chunks.length === 0) return
      const kind = (next.mimeType || type || 'audio/webm').split(';')[0]
      const blob = new Blob(chunks, { type: kind })
      done.current(new File([blob], audioName(kind), { type: kind }))
    }
    discard.current = false
    stream.current = media
    recorder.current = next
    setSeconds(0)
    next.start(1000)
    setRecording(true)
  }

  const stop = (keep: boolean) => {
    discard.current = !keep
    if (recorder.current?.state === 'recording') recorder.current.stop()
  }

  return { recording, seconds, start, stop }
}

/** «1:58». */
export function clockWords(seconds: number): string {
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`
}

/* --- Выполнение ДЗ показателем -------------------------------------------------- */

/** «ДЗ вовремя» в оценках ученика и во вкладке «Успеваемость» карточки: доля сданных в срок. */
export function HomeworkKpi({
  homework,
}: {
  homework?: { total: number; on_time: number; late: number; pct: number | null }
}) {
  const value = homework && homework.total > 0 && homework.pct !== null ? `${homework.pct} %` : null
  const note =
    homework && homework.total > 0
      ? `${t('сдано вовремя')} ${homework.on_time} ${t('из')} ${homework.total}${homework.late ? ` · ${t('с опозданием')} ${homework.late}` : ''}`
      : undefined
  return <Kpi label={t('ДЗ вовремя')} value={value} none={t('заданий со сдачей не было')} note={note} />
}
