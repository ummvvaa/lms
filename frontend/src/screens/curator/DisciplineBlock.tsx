/**
 * Дисциплина в карточке ученика (фаза 66, посещаемость по урокам — шаг 4 серии).
 *
 * Числами нельзя поговорить с родителем: «три замечания» через месяц
 * не помнит никто. Поэтому в блоке дни, когда ученика не было на уроках,
 * с предметами и отметками словами, и замечания словами; процент за месяц
 * стоит подписью сверху — его читают дашборды и обзвон.
 *
 * Посещаемость считают учителя на уроках; куратор оформляет уважительную
 * причину за период. Замечания пишут куратор своей группы и директор
 * школы; кто именно — решает сервер, экран только показывает или прячет форму.
 */
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { toast } from 'sonner'
import { useAddRemark, useDropRemark, type CuratorCard as Card } from '../../api/hooks'
import Field from '../../components/Field'
import { Row, Rows } from '../../components/patterns'
import { Chip, DataCard, EmptyNote } from '../../components/ui'
import { Button } from '../../components/ui/button'
import { t } from '../../i18n'
import { ExcuseDialog } from '../academics/GradesTab'
import { dateWords } from '../academics/shared'

const asDate = (value: string) => new Date(value).toLocaleDateString('ru')

export default function DisciplineBlock({ card }: { card: Card }) {
  const navigate = useNavigate()
  const block = card.behavior
  const add = useAddRemark(card.id)
  const drop = useDropRemark(card.id)
  const [text, setText] = useState('')
  const [excusing, setExcusing] = useState<{ from: string; to: string } | null>(null)

  const missed = block.days.filter((day) => !day.present)
  const unexcused = block.unexcused_days ?? []
  // блок молчит целиком: уроков с отметкой ещё не было, пропусков и замечаний нет
  const silent = block.attendance_percent === null && missed.length === 0 && block.remarks.length === 0
  const attendanceTone = block.attendance_percent === null ? 'neutral' : block.attendance_percent < 85 ? 'warn' : 'good'

  return (
    <DataCard
      title={t('Дисциплина')}
      note={`${t('Посещаемость — по урокам за месяц; замечания ведёт')} ${block.owner}`}
      right={
        <>
          <Chip tone={attendanceTone} className="num">
            {block.attendance_percent === null ? t('уроков с отметкой не было') : `${block.attendance_percent} %`}
          </Chip>
          {card.group && (
            <Button size="sm" variant="outline" onClick={() => navigate(`/attendance?group=${encodeURIComponent(card.group)}`)}>
              {t('Открыть посещаемость')}
            </Button>
          )}
        </>
      }
    >
      {/* Блок молчит целиком — одна строка; поле замечания ниже остаётся:
          замечание записывают прямо здесь */}
      {silent && <EmptyNote what="уроков с отметкой ещё не было" who="отмечают учителя на уроках" />}
      {!silent && (
        <p className="acad__note">
          {missed.length === 0
            ? t('Пропусков за последний месяц нет')
            : `${t('Дней с пропусками за месяц:')} ${missed.length}${unexcused.length ? ` · ${t('без причины')} ${unexcused.length}` : ''}`}
        </p>
      )}
      {unexcused.length > 0 && block.may_write && (
        <div className="acad__actions">
          <Button size="sm" onClick={() => setExcusing({ from: unexcused[0], to: unexcused[unexcused.length - 1] })}>
            {t('Оформить уважительную причину')}
          </Button>
        </div>
      )}
      {missed.length > 0 && (
        <Rows>
          {missed.slice(0, 8).map((day) => (
            <Row
              key={day.date}
              icon="calendar"
              tone={unexcused.includes(day.date) ? 'bad' : day.absent ? 'warn' : 'info'}
              title={dateWords(day.date)}
              note={day.reason || t('причина не указана')}
              acts={
                <>
                  {block.may_write && day.absent ? (
                    <Button size="sm" variant="secondary" onClick={() => setExcusing({ from: day.date, to: day.date })}>
                      {t('Оформить')}
                    </Button>
                  ) : null}
                  {card.group ? (
                    <Button size="sm" variant="ghost" onClick={() => navigate(`/attendance?group=${encodeURIComponent(card.group)}&date=${day.date}`)}>
                      {t('Открыть день')}
                    </Button>
                  ) : null}
                </>
              }
            />
          ))}
        </Rows>
      )}

      <p className="acad__note cadm__note">
        {block.remarks.length === 0 ? t('Замечаний нет') : `${t('Замечаний:')} ${block.remarks.length}`}
      </p>
      <Rows>
        {block.remarks.map((remark) => (
          <Row
            key={remark.id}
            icon="alert"
            title={remark.text}
            note={`${asDate(remark.date)}${remark.author ? ` · ${remark.author}` : ''}`}
            acts={
              block.may_write ? (
                <Button
                  size="sm"
                  variant="ghost"
                  disabled={drop.isPending}
                  onClick={() =>
                    drop.mutate(remark.id, {
                      onSuccess: () => toast.success(t('Замечание снято')),
                      onError: (error) => toast.error(error.message),
                    })
                  }
                >
                  {t('Снять')}
                </Button>
              ) : undefined
            }
          />
        ))}
      </Rows>

      {block.may_write && (
        <div className="cnotes__form">
          <Field kind="text" name="remark" label={t('Замечание')} value={text} onChange={setText} placeholder={t('Замечание словами — за что именно')} />
          <div className="acad__actions">
            <Button
              size="sm"
              disabled={add.isPending || !text.trim()}
              onClick={() =>
                add.mutate(
                  { text },
                  {
                    onSuccess: () => {
                      setText('')
                      toast.success(t('Замечание записано'))
                    },
                    onError: (error) => toast.error(error.message),
                  },
                )
              }
            >
              {t('Записать')}
            </Button>
          </div>
        </div>
      )}
      {excusing && <ExcuseDialog student={card.id} from={excusing.from} to={excusing.to} onClose={() => setExcusing(null)} />}
    </DataCard>
  )
}
