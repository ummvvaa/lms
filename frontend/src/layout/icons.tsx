/**
 * Иконки интерфейса.
 *
 * Тонкий одноцветный контур, общая сетка 24×24, цвет — текущий цвет
 * текста: иконка живёт в строке меню и меняется вместе с ней (в том числе
 * на активном пункте и в тёмной теме). Эмодзи в интерфейсе не используются
 * вовсе: у каждого шрифта они свои, цвет у них собственный, и в подсказке
 * или в письме они читаются как сбой.
 */

const PATHS = {
  /* --- разделы --- */
  dashboard: (
    <>
      <path d="M4 18a8 8 0 1 1 16 0" />
      <path d="M12 18l3.5-4.5" />
    </>
  ),
  table: (
    <>
      <rect x="3" y="4.5" width="18" height="15" rx="2.5" />
      <path d="M3 10h18M9.5 10v9.5M15 10v9.5" />
    </>
  ),
  upload: (
    <>
      <path d="M12 15V4" />
      <path d="M8.5 7.5L12 4l3.5 3.5" />
      <path d="M4.5 15v3a2.5 2.5 0 0 0 2.5 2.5h10a2.5 2.5 0 0 0 2.5-2.5v-3" />
    </>
  ),
  sparkle: (
    <>
      <path d="M11 3.5l1.7 4.3 4.3 1.7-4.3 1.7L11 15.5 9.3 11.2 5 9.5l4.3-1.7z" />
      <path d="M17.5 14.5l.8 2 2 .8-2 .8-.8 2-.8-2-2-.8 2-.8z" />
    </>
  ),
  bulb: (
    <>
      <path d="M12 3.5a5.8 5.8 0 0 0-3.4 10.5c.4.3.6.7.6 1.2v.8h5.6v-.8c0-.5.2-.9.6-1.2A5.8 5.8 0 0 0 12 3.5z" />
      <path d="M9.8 19h4.4M10.6 21.2h2.8" />
    </>
  ),
  news: (
    <>
      <rect x="3" y="5" width="13.5" height="14" rx="2" />
      <path d="M16.5 9H20a1 1 0 0 1 1 1v7a2 2 0 0 1-2 2" />
      <path d="M6.5 9h6.5M6.5 12.2h6.5M6.5 15.4h4.5" />
    </>
  ),
  cap: (
    <>
      <path d="M12 4L2.5 8.6 12 13.2l9.5-4.6z" />
      <path d="M6.5 10.9v4.4c0 1.7 2.5 3 5.5 3s5.5-1.3 5.5-3v-4.4" />
    </>
  ),
  people: (
    <>
      <circle cx="9.5" cy="8.2" r="3.2" />
      <path d="M3.5 19.8a6 6 0 0 1 12 0" />
      <path d="M16.2 5.6a3 3 0 0 1 0 5.6" />
      <path d="M18 19.8a5.4 5.4 0 0 0-2.6-4.6" />
    </>
  ),
  alert: (
    <>
      <path d="M12 4.4L3 19.6h18z" />
      <path d="M12 10v4.2" />
      <path d="M12 17.3h.01" />
    </>
  ),
  building: (
    <>
      <path d="M4 20.5V9.2L12 4l8 5.2v11.3" />
      <path d="M9.2 20.5v-5.6h5.6v5.6" />
      <path d="M2.8 20.5h18.4" />
    </>
  ),
  clock: (
    <>
      <circle cx="12" cy="12" r="8.2" />
      <path d="M12 7.2V12l3.2 2" />
    </>
  ),
  star: <path d="M12 3.8l2.6 5.3 5.8.8-4.2 4.1 1 5.8L12 17.1l-5.2 2.7 1-5.8-4.2-4.1 5.8-.8z" />,
  target: (
    <>
      <circle cx="12" cy="12" r="8.2" />
      <circle cx="12" cy="12" r="3.8" />
      <circle cx="12" cy="12" r="0.9" />
    </>
  ),
  book: (
    <>
      <path d="M4.5 5.8A2.3 2.3 0 0 1 6.8 3.5H19v13.2H6.8a2.3 2.3 0 0 0-2.3 2.3z" />
      <path d="M4.5 18.8a2.3 2.3 0 0 0 2.3 2.3H19v-4.4" />
    </>
  ),
  branch: (
    <>
      <circle cx="6.2" cy="6" r="2.2" />
      <circle cx="6.2" cy="18" r="2.2" />
      <circle cx="17.8" cy="12" r="2.2" />
      <path d="M6.2 8.2v7.6" />
      <path d="M8.4 6h3.6a3.6 3.6 0 0 1 3.6 3.6v.4" />
      <path d="M8.4 18h3.6a3.6 3.6 0 0 0 3.6-3.6v-.4" />
    </>
  ),
  trophy: (
    <>
      <path d="M8 4h8v4.8a4 4 0 0 1-8 0z" />
      <path d="M8 5.6H5.6A2.4 2.4 0 0 0 8 9.6" />
      <path d="M16 5.6h2.4A2.4 2.4 0 0 1 16 9.6" />
      <path d="M12 12.8v4.4M9 20.2h6" />
    </>
  ),
  calendar: (
    <>
      <rect x="3.5" y="5.5" width="17" height="15" rx="2.5" />
      <path d="M3.5 10.2h17M8.2 3.4v4M15.8 3.4v4" />
    </>
  ),
  person: (
    <>
      <circle cx="12" cy="8" r="3.4" />
      <path d="M5 20.2a7 7 0 0 1 14 0" />
    </>
  ),
  box: (
    <>
      <rect x="3.2" y="4" width="17.6" height="4.6" rx="1.5" />
      <path d="M5 8.6v10.4A1.5 1.5 0 0 0 6.5 20.5h11a1.5 1.5 0 0 0 1.5-1.5V8.6" />
      <path d="M10 12.4h4" />
    </>
  ),
  card: (
    <>
      <rect x="3" y="5.5" width="18" height="13" rx="2.5" />
      <path d="M3 10h18" />
      <path d="M6.8 14.6h3.4" />
    </>
  ),
  layers: (
    <>
      <path d="M12 3.5L3 8.2l9 4.7 9-4.7z" />
      <path d="M3.4 13l8.6 4.5 8.6-4.5" />
    </>
  ),
  openbook: (
    <>
      <path d="M12 6.6C10.4 5.1 8.4 4.5 5 4.5v13c3.4 0 5.4.6 7 2.1 1.6-1.5 3.6-2.1 7-2.1v-13c-3.4 0-5.4.6-7 2.1z" />
      <path d="M12 6.6v13" />
    </>
  ),
  medal: (
    <>
      <circle cx="12" cy="14.6" r="5.4" />
      <path d="M8.2 9.4L5.6 3.6h4.9L12 6.4" />
      <path d="M15.8 9.4l2.6-5.8h-4.9" />
    </>
  ),
  search: (
    <>
      <circle cx="11" cy="11" r="6.4" />
      <path d="M20 20l-4.4-4.4" />
    </>
  ),
  bookmark: <path d="M6.5 3.6h11a1 1 0 0 1 1 1v16.1L12 16.6l-6.5 4.1V4.6a1 1 0 0 1 1-1z" />,
  pencil: (
    <>
      <path d="M4 20l1-4.4L16.2 4.4a1.9 1.9 0 0 1 2.7 0l.7.7a1.9 1.9 0 0 1 0 2.7L8.4 19 4 20z" />
      <path d="M14.8 5.8l3.4 3.4" />
    </>
  ),
  doc: (
    <>
      <path d="M13.8 3.5H7.4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2h9.2a2 2 0 0 0 2-2V8.3z" />
      <path d="M13.8 3.5v4.8h4.8" />
      <path d="M8.8 13h6.4M8.8 16.4h4.2" />
    </>
  ),
  checklist: (
    <>
      <rect x="4" y="4" width="16" height="16" rx="2.5" />
      <path d="M8 9.8l1.6 1.6L13 8" />
      <path d="M8 15.6h8" />
    </>
  ),

  /* --- служебные --- */
  bell: (
    <>
      <path d="M18 15.6V11a6 6 0 1 0-12 0v4.6L4.4 18.2h15.2z" />
      <path d="M9.9 20.6a2.3 2.3 0 0 0 4.2 0" />
    </>
  ),
  chevronLeft: <path d="M14.5 5.5L8 12l6.5 6.5" />,
  chevronRight: <path d="M9.5 5.5L16 12l-6.5 6.5" />,
} as const

export type IconName = keyof typeof PATHS

/** Одна иконка. Размер по умолчанию — под строку меню. */
export default function Icon({ name, size = 18 }: { name: IconName; size?: number }) {
  return (
    <svg
      className="icon"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      {PATHS[name]}
    </svg>
  )
}
