/**
 * «Кружки» ученика (31.10.2026): карточки кружков своей параллели и тех, где он состоит.
 *
 * Карточка — название, описание, дни и время, ментор и статус «Вы записаны».
 * «Записаться» записывает сразу: мест без лимита, заявок нет. «Выйти из
 * кружка» — с подтверждением; записаться снова можно в любой момент, пока
 * запись открыта. Закрыта — кнопки нет, подпись «Запись закрыта»; записанный
 * остаётся и может выйти. Пересечение со спортивной секцией — тихой строкой
 * у кнопки: записаться всё равно можно. Ученик видит только себя и задание
 * ментора — чужих имён, заметок и ярлыков здесь нет.
 */
import { useState } from 'react'
import { toast } from 'sonner'
import { useMyClubAction, useMyClubs, type MyClub } from '../../api/clubs'
import Modal from '../../components/Modal'
import { Chip, DataCard, ErrorNote, Loading, ScreenHead } from '../../components/ui'
import { Button } from '../../components/ui/button'
import { t } from '../../i18n'
import { formatDateLong, formatDayMonth } from '../../lib/format'
import '../directors/directors.css'
import '../sport/sport.css'
import './clubs.css'

const fail = (reason: unknown) => toast.error(reason instanceof Error ? reason.message : String(reason))

export default function StudentClubs() {
  const { data, isLoading, error } = useMyClubs()
  if (isLoading && !data) return <Loading kind="cards" />
  if (error) return <ErrorNote error={error} />
  if (!data) return null
  return (
    <div className="lay-screen">
      <ScreenHead title={t('Кружки')} subtitle={t('Записывайся сам — мест хватит всем, можно в несколько кружков')} />
      {data.clubs.length === 0 ? (
        <DataCard title={t('Кружки')} empty={t('для твоей параллели кружков пока нет')} />
      ) : (
        <div className="clubs-cards">
          {data.clubs.map((club) => (
            <ClubCard key={club.id} club={club} />
          ))}
        </div>
      )}
    </div>
  )
}

function ClubCard({ club }: { club: MyClub }) {
  const { enroll, leave } = useMyClubAction()
  const [leaving, setLeaving] = useState(false)
  return (
    <DataCard
      title={club.title}
      note={club.schedule}
      right={
        club.enrolled ? (
          <Chip tone="good" size="sm">
            {t('Вы записаны')}
          </Chip>
        ) : undefined
      }
    >
      {club.description && <p className="clubs-text">{club.description}</p>}
      <div className="dir__lines">
        <div className="dir__line">
          <span>{t('Дни и время')}</span>
          <b className="num">{club.schedule}</b>
        </div>
        <div className="dir__line">
          <span>{t('Ментор')}</span>
          <b>{club.mentor_name}</b>
        </div>
        {club.enrolled && club.enrolled_at && (
          <div className="dir__line">
            <span>{t('В кружке')}</span>
            <b>{t('с {date}', { date: formatDateLong(club.enrolled_at) })}</b>
          </div>
        )}
      </div>
      {club.enrolled && club.homework.length > 0 && <Homework club={club} />}
      {!club.enrolled && club.overlaps.length > 0 && (
        <p className="clubs-warn">
          {t('Пересекается с твоей секцией: {what}', { what: club.overlaps.join('; ') })}
        </p>
      )}
      <div className="clubs-actions">
        {club.enrolled ? (
          <Button variant="outline" onClick={() => setLeaving(true)}>
            {t('Выйти из кружка')}
          </Button>
        ) : club.can_enroll ? (
          <Button
            disabled={enroll.isPending}
            onClick={() =>
              enroll.mutate(club.id, {
                onSuccess: (data) => {
                  toast.success(t('Ты записан в кружок «{title}»', { title: club.title }))
                  for (const warning of data.warnings ?? [])
                    toast.warning(t('Пересекается с твоей секцией: {what}', { what: warning }))
                },
                onError: fail,
              })
            }
          >
            {t('Записаться')}
          </Button>
        ) : (
          <span className="t-note">{t('Запись закрыта')}</span>
        )}
      </div>
      {leaving && (
        <Modal title={t('Выйти из кружка?')} note={club.title} onClose={() => setLeaving(false)}>
          <p className="t-note">{t('Записаться снова можно в любой момент, пока запись открыта.')}</p>
          <div className="acad__actions">
            <Button variant="outline" onClick={() => setLeaving(false)}>
              {t('Отмена')}
            </Button>
            <Button
              variant="destructive"
              disabled={leave.isPending}
              onClick={() =>
                leave.mutate(club.id, {
                  onSuccess: () => {
                    toast.success(t('Ты вышел из кружка «{title}»', { title: club.title }))
                    setLeaving(false)
                  },
                  onError: fail,
                })
              }
            >
              {t('Выйти')}
            </Button>
          </div>
        </Modal>
      )}
    </DataCard>
  )
}

/** Задание ментора: текст и срок; сдачи в LMS нет. */
function Homework({ club }: { club: MyClub }) {
  return (
    <div className="sport-list">
      <span className="t-card">{t('Домашнее задание')}</span>
      <div className="dir__rows">
        {club.homework.map((row) => (
          <div key={row.id} className="dir__row clubs-homework">
            <span className="dir__what">
              <span className="clubs-text">{row.text}</span>
              <span className="t-note">{t('срок {date}', { date: formatDayMonth(row.due) })}</span>
            </span>
            <span />
            <span />
          </div>
        ))}
      </div>
    </div>
  )
}
