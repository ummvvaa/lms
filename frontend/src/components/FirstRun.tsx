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

const SEEN_KEY = 'first-run-seen'

interface Guide {
  title: string
  steps: { title: string; text: string }[]
  action: { label: string; path: string }
}

const DIRECTOR: Guide = {
  title: 'Три шага, чтобы начать',
  steps: [
    {
      title: 'Загрузите файл со своими данными',
      text: 'XLSX или CSV — тот же, что вы ведёте сейчас. Ничего переделывать не нужно.',
    },
    {
      title: 'Проверьте, что колонки распознались',
      text: 'Система предложит соответствие, а вы поправите его вручную. Чужие поля она не тронет.',
    },
    {
      title: 'Готово — данные в таблице и на дашборде',
      text: 'Если что-то пошло не так, загрузку можно отменить целиком в истории.',
    },
  ],
  action: { label: 'Перейти к импорту', path: '/import' },
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
        text: 'Загрузите свой файл требований или заполните стартовый справочник одной кнопкой.',
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
      { title: 'Заведите учеников', text: 'Руками или импортом — дальше директора наполнят свои домены.' },
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
        <button className="btn btn-ghost btn-sm" onClick={close}>
          {t('Пропустить')}
        </button>
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

      <button
        className="btn btn-primary btn-sm firstrun__go"
        onClick={() => {
          close()
          navigate(guide.action.path)
        }}
      >
        {guide.action.label}
      </button>
    </section>
  )
}
