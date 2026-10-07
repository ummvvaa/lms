/**
 * Стили экранов — одним списком и в одном порядке.
 *
 * Экраны грузятся по маршруту (`lazy` в `App.tsx`), а их стили — сразу,
 * этим списком. Порядок здесь — порядок каскада: при равном весе правило
 * ниже переигрывает правило выше. До разбиения сборки его задавали импорты
 * экранов в `App.tsx`; список повторяет тот порядок, и CSS сборки вышел
 * тот же правило в правило. Иначе стиль экрана, приехавший с экраном,
 * вставал бы после общих `screens.css`, `ui.css` и `base.css` — и, например,
 * обычная ячейка таблицы кабинета перебивала свой же телефонный вид.
 *
 * Новый файл стилей экрана — строка сюда; страж
 * `test_every_style_loads_with_the_first_page` не пустит забытый.
 */
import './screens/academics/academics.css'
import './screens/curator/curator.css'
import './screens/academics/homework-review.css'
import './screens/attendance.css'
import './screens/mocks/mocks.css'
import './components/queue.css'
import './screens/dashboards/cabinet.css'
import './screens/dashboards/student.css'
import './components/calendar-card.css'
// строка инструментов — на прежнем месте, перед таблицей: модификаторы экранов
// (`toolbar mat__ask`) переигрывают её отступы, только если идут после
import './components/toolbar.css'
import './screens/table.css'
import './screens/universities.css'
import './screens/catalog.css'
import './screens/directory.css'
import './screens/onboarding.css'
import './components/badges.css'
import './screens/prep.css'
import './screens/roadmap.css'
import './screens/assistant.css'
import './screens/directory-list.css'
import './screens/materials.css'
import './screens/school-settings.css'
import './screens/portfolio.css'
import './screens/scholarships.css'
import './screens/resources.css'
import './screens/career.css'
import './screens/homework/myWork.css'
import './screens/card.css'

import './screens/usage.css'
