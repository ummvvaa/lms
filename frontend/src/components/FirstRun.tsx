/**
 * Первый вход: три коротких шага под роль вошедшего.
 *
 * Не обучение и не тур по интерфейсу — три предложения о том, с чего
 * начать именно этому человеку. Пропускается одной кнопкой и вызывается
 * повторно из шапки: «Как начать».
 */
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import type { Role } from '../api/types'
import { t, tk } from '../i18n'
import { Button } from './ui/button'

const SEEN_KEY = 'first-run-seen'

interface Guide {
  title: string
  steps: { title: string; text: string }[]
  action: { label: string; path: string }
}

// файлы грузит администратор (фаза 35): директор начинает с таблицы,
// а кусок своей таблицы вставляет из буфера или через «Вставить как есть»
const DIRECTOR: Guide = {
  title: tk('Три шага, чтобы начать'),
  steps: [
    {
      title: tk('Откройте таблицу быстрого ввода'),
      text: tk('Строка на каждого ученика, только поля вашего домена. Tab и стрелки водят по ячейкам.'),
    },
    {
      title: tk('Вставьте кусок своей таблицы'),
      text: tk('Скопируйте диапазон из Excel и вставьте в ячейку — значения лягут вправо и вниз. Чужие поля не тронутся.'),
    },
    {
      title: tk('Готово — данные на дашборде'),
      text: tk('Файл целиком отдайте администратору: его загрузку вы увидите в истории и сможете отменить.'),
    },
  ],
  action: { label: tk('Открыть таблицу'), path: '/table' },
}

const GUIDES: Record<Role, Guide> = {
  student: {
    title: tk('С чего начать'),
    steps: [
      {
        title: tk('Заполните профиль'),
        text: tk('Несколько коротких вопросов о себе — кабинет наполнится вашими данными.'),
      },
      { title: tk('Выберите вузы'), text: tk('В каталоге видно, куда вы проходите уже сейчас и чего не хватает.') },
      { title: tk('Посмотрите план'), text: tk('Задачи соберутся из ваших вузов и их дедлайнов.') },
    ],
    action: { label: tk('Заполнить профиль'), path: '/onboarding' },
  },
  director_behavior: DIRECTOR,
  director_admission: {
    title: tk('Три шага, чтобы начать'),
    steps: [
      {
        title: tk('Заведите справочник вузов'),
        text: tk('Заполните стартовый справочник одной кнопкой или заведите вузы руками; файл требований загрузит администратор.'),
      },
      {
        title: tk('Проверьте данные и снимите плашки'),
        text: tk('Записи заготовки помечены «не подтверждено». Сверьте их с сайтами вузов.'),
      },
      {
        title: tk('Загрузите данные учеников'),
        text: tk('После этого процент соответствия посчитается сам, а дедлайны превратятся в задачи.'),
      },
    ],
    action: { label: tk('Открыть справочник'), path: '/directory' },
  },
  director_exam: DIRECTOR,
  director_talent: DIRECTOR,
  director_sport: DIRECTOR,
  // куратор (фаза 60): пока один экран — свои группы; очередь придёт в 61
  // учитель: три шага — открыть «Сегодня», отметить урок, поставить оценки в журнале
  teacher: {
    title: tk('С чего начать'),
    steps: [
      {
        title: tk('Откройте «Сегодня»'),
        text: tk('Там уроки по звонкам и то, что ещё не отмечено.'),
      },
      {
        title: tk('Отметьте урок'),
        text: tk('Нажмите «Отметить» и выберите только тех, кого нет. Остальные считаются присутствующими.'),
      },
      {
        title: tk('Ставьте оценки в журнале'),
        text: tk('Клетка рядом с отметкой; можно печатать цифрами. Итог четверти считается сам.'),
      },
    ],
    action: { label: tk('Открыть «Сегодня»'), path: '/dashboard' },
  },
  curator: {
    title: tk('С чего начать'),
    steps: [
      {
        title: tk('Проверьте свои группы'),
        text: tk('Группы назначает администратор. Если группы нет в списке — напишите ему.'),
      },
      {
        title: tk('Откройте карточку ученика'),
        text: tk('Карточка целиком: все домены, история правок. Данные за ученика вы не вносите — подтверждаете.'),
      },
      {
        title: tk('Дальше — очередь'),
        text: tk('Подтверждения баллов и документов ваших групп — в очереди; переданное владельцу домена видно под ней.'),
      },
    ],
    action: { label: tk('Открыть кабинет'), path: '/dashboard' },
  },
  admin: {
    title: tk('Три шага, чтобы начать'),
    steps: [
      {
        title: tk('Заведите директоров'),
        text: tk('Каждому — своя учётная запись. Пароль человек задаёт себе сам по ссылке.'),
      },
      { title: tk('Заведите учебные группы'), text: tk('По ним раскладываются ученики и считаются дашборды.') },
      {
        title: tk('Заведите учеников'),
        text: tk('Списком на экране «Пользователи». Файлы с данными по доменам тоже грузите вы — на экране «Импорт».'),
      },
    ],
    action: { label: tk('Открыть пользователей'), path: '/users' },
  },
}

/** Ученик 8–10: учёба, олимпиады и спорт — поступления у него нет. */
const JUNIOR_GUIDE: Guide = {
  title: tk('С чего начать'),
  steps: [
    { title: tk('Откройте расписание'), text: tk('Уроки недели по звонкам, СОР и СОЧ отмечены прямо в клетке урока.') },
    { title: tk('Следите за оценками'), text: tk('По каждому предмету видно, что выходит за четверть сейчас.') },
    { title: tk('Внесите олимпиады и спорт'), text: tk('Участие и результат вносите сами — директор подтвердит.') },
  ],
  action: { label: tk('Открыть расписание'), path: '/schedule' },
}

export function markFirstRunSeen(): void {
  localStorage.setItem(SEEN_KEY, '1')
}

export default function FirstRun({
  role,
  forced = false,
  junior = false,
  onClose,
}: {
  role: Role
  /** вызван из меню, а не сам при первом входе */
  forced?: boolean
  /** ученик 8–10: подсказка про учёбу, без анкеты и вузов */
  junior?: boolean
  onClose?: () => void
}) {
  const navigate = useNavigate()
  const [hidden, setHidden] = useState(() => !forced && localStorage.getItem(SEEN_KEY) === '1')
  const guide = role === 'student' && junior ? JUNIOR_GUIDE : GUIDES[role]

  if (hidden || !guide) return null

  const close = () => {
    markFirstRunSeen()
    setHidden(true)
    onClose?.()
  }

  return (
    <section className="card card-pad firstrun">
      <div className="row-between firstrun__head">
        <span className="eyebrow">{t(guide.title)}</span>
        <Button variant="outline" size="sm" onClick={close}>
          {t('Пропустить')}
        </Button>
      </div>

      <ol className="firstrun__list">
        {guide.steps.map((step, index) => (
          <li key={step.title} className="firstrun__step">
            <span className="firstrun__num num">{index + 1}</span>
            <span>
              <b className="firstrun__title">{t(step.title)}</b>
              <span className="muted firstrun__text">{t(step.text)}</span>
            </span>
          </li>
        ))}
      </ol>

      <Button
        size="sm"
        className="firstrun__go"
        onClick={() => {
          close()
          navigate(guide.action.path)
        }}
      >
        {t(guide.action.label)}
      </Button>
    </section>
  )
}
