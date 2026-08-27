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
import { t } from '../i18n'
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
  title: 'Три шага, чтобы начать',
  steps: [
    {
      title: 'Откройте таблицу быстрого ввода',
      text: 'Строка на каждого ученика, только поля вашего домена. Tab и стрелки водят по ячейкам.',
    },
    {
      title: 'Вставьте кусок своей таблицы',
      text: 'Скопируйте диапазон из Excel и вставьте в ячейку — значения лягут вправо и вниз. Чужие поля не тронутся.',
    },
    {
      title: 'Готово — данные на дашборде',
      text: 'Файл целиком отдайте администратору: его загрузку вы увидите в истории и сможете отменить.',
    },
  ],
  action: { label: 'Открыть таблицу', path: '/table' },
}

const GUIDES: Record<Role, Guide> = {
  student: {
    title: 'С чего начать',
    steps: [
      {
        title: 'Заполните профиль',
        text: 'Несколько коротких вопросов о себе — кабинет наполнится вашими данными.',
      },
      { title: 'Выберите вузы', text: 'В каталоге видно, куда вы проходите уже сейчас и чего не хватает.' },
      { title: 'Посмотрите план', text: 'Задачи соберутся из ваших вузов и их дедлайнов.' },
    ],
    action: { label: 'Заполнить профиль', path: '/onboarding' },
  },
  director_behavior: DIRECTOR,
  director_admission: {
    title: 'Три шага, чтобы начать',
    steps: [
      {
        title: 'Заведите справочник вузов',
        text: 'Заполните стартовый справочник одной кнопкой или заведите вузы руками; файл требований загрузит администратор.',
      },
      {
        title: 'Проверьте данные и снимите плашки',
        text: 'Записи заготовки помечены «не подтверждено». Сверьте их с сайтами вузов.',
      },
      {
        title: 'Загрузите данные учеников',
        text: 'После этого процент соответствия посчитается сам, а дедлайны превратятся в задачи.',
      },
    ],
    action: { label: 'Открыть справочник', path: '/directory' },
  },
  director_exam: DIRECTOR,
  director_talent: DIRECTOR,
  director_sport: DIRECTOR,
  admin: {
    title: 'Три шага, чтобы начать',
    steps: [
      {
        title: 'Заведите директоров',
        text: 'Каждому — своя учётная запись. Пароль человек задаёт себе сам по ссылке.',
      },
      { title: 'Заведите учебные группы', text: 'По ним раскладываются ученики и считаются дашборды.' },
      {
        title: 'Заведите учеников',
        text: 'Списком на экране «Пользователи». Файлы с данными по доменам тоже грузите вы — на экране «Импорт».',
      },
    ],
    action: { label: 'Открыть пользователей', path: '/users' },
  },
}

export function markFirstRunSeen(): void {
  localStorage.setItem(SEEN_KEY, '1')
}

export default function FirstRun({
  role,
  forced = false,
  onClose,
}: {
  role: Role
  /** вызван из меню, а не сам при первом входе */
  forced?: boolean
  onClose?: () => void
}) {
  const navigate = useNavigate()
  const [hidden, setHidden] = useState(() => !forced && localStorage.getItem(SEEN_KEY) === '1')
  const guide = GUIDES[role]

  if (hidden || !guide) return null

  const close = () => {
    markFirstRunSeen()
    setHidden(true)
    onClose?.()
  }

  return (
    <section className="card card-pad firstrun">
      <div className="row-between firstrun__head">
        <span className="eyebrow">{guide.title}</span>
        <Button variant="outline" size="sm" onClick={close}>
          {t('Пропустить')}
        </Button>
      </div>

      <ol className="firstrun__list">
        {guide.steps.map((step, index) => (
          <li key={step.title} className="firstrun__step">
            <span className="firstrun__num num">{index + 1}</span>
            <span>
              <b className="firstrun__title">{step.title}</b>
              <span className="muted firstrun__text">{step.text}</span>
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
        {guide.action.label}
      </Button>
    </section>
  )
}
