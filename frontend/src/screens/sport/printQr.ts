/**
 * «Скачать QR для печати»: лист A4 с постоянным кодом секции. Одна кнопка
 * на «Секциях» и на «Занятие и QR» — один и тот же файл. У секции без места
 * сервер отвечает, к кому идти; текст отказа показывает тост.
 */
import { toast } from 'sonner'
import { downloadFile } from '../../api/client'
import { t } from '../../i18n'

export function downloadQrSheet(section: number, title: string): Promise<void> {
  return downloadFile(`/sport/sections/${section}/print/`, t('QR {title}.pdf', { title }))
    .then(() => {
      toast.success(t('Лист с QR скачан · распечатайте и повесьте на месте занятия'))
    })
    .catch((reason: unknown) => {
      toast.error(reason instanceof Error ? reason.message : String(reason))
    })
}
