/**
 * Фон кораллового языка: три размытые сферы и точечная сетка под содержимым.
 * Неподвижный слой, мышь не ловит; при «уменьшить движение» сферы стоят.
 * Стоит в каркасе и на экранах без каркаса (вход).
 */
export default function Backdrop() {
  return (
    <div className="backdrop" aria-hidden="true">
      <div className="backdrop__orb backdrop__orb--a" />
      <div className="backdrop__orb backdrop__orb--b" />
      <div className="backdrop__orb backdrop__orb--c" />
      <div className="backdrop__dots" />
    </div>
  )
}
