/**
 * QR-код ссылки отметки — рисуется в браузере пакетом `qrcode`, без внешних
 * сервисов: токен занятия никуда, кроме LMS, не уходит. Пакет грузится
 * отдельным куском только на экране занятия.
 *
 * Модули кода — цветом `--qr-ink` на подложке `--qr-paper`: камера телефона
 * читает тёмное на светлом, поэтому подложка светлая и в тёмной теме.
 */
import { useEffect, useState } from 'react'
import { t } from '../../i18n'

export default function QrCode({ value }: { value: string }) {
  const [svg, setSvg] = useState('')
  useEffect(() => {
    let alive = true
    void import('qrcode')
      .then((QRCode) =>
        QRCode.toString(value, {
          type: 'svg',
          errorCorrectionLevel: 'M',
          margin: 1,
          // цвета пакета по умолчанию перекрашивает CSS токенами `--qr-ink` и `--qr-paper`
        }),
      )
      .then((markup) => {
        if (alive) setSvg(markup)
      })
    return () => {
      alive = false
    }
  }, [value])
  return (
    <div
      className="sport-qr__code"
      role="img"
      aria-label={t('QR-код отметки на занятии')}
      // разметка — SVG, собранный пакетом из ссылки LMS; текста пользователя в нём нет
      dangerouslySetInnerHTML={{ __html: svg }}
    />
  )
}
