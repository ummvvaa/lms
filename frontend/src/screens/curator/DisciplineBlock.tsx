/**
 * Дисциплина в карточке ученика (фаза 66).
 *
 * Раньше здесь были два числа — процент и счётчик. Числами нельзя
 * поговорить с родителем: «три замечания» через месяц не помнит никто.
 * Поэтому в блоке дни, когда ученика не было, и замечания словами,
 * а числа остались подписью сверху — их читают дашборды и обзвон.
 *
 * Пишут куратор своей группы и директор школы; кто именно — решает
 * сервер, экран только показывает или прячет форму.
 */
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { toast } from 'sonner'
import { useAddRemark, useDropRemark, type CuratorCard as Card } from '../../api/hooks'
import { Row, Rows } from '../../components/patterns'
import { DataCard } from '../../components/ui'
import { Badge } from '../../components/ui/badge'
import { Button } from '../../components/ui/button'
import { Input } from '../../components/ui/input'
import { t } from '../../i18n'

const asDate = (value: string) => new Date(value).toLocaleDateString('ru')

export default function DisciplineBlock({ card }: { card: Card }) {
  const navigate = useNavigate()
  const block = card.behavior
  const add = useAddRemark(card.id)
  const drop = useDropRemark(card.id)
  const [text, setText] = useState('')

  const missed = block.days.filter((day) => !day.present)

  return (
    <DataCard
      title={t('Дисциплина')}
      note={`${t('Ведёт директор школы —')} ${block.owner}`}
      right={
        <>
          <Badge variant={(block.attendance_percent ?? 100) < 80 ? 'warn' : 'ok'} className="num">
            {block.attendance_percent === null ? t('нет данных') : `${block.attendance_percent}%`}
          </Badge>
          {/* посещаемость ведётся по группе за день (фаза 66), и отметить
              её из карточки нельзя — но дойти до нужного листа можно
              отсюда, а не искать группу и число руками (фаза 70) */}
          {card.group && (
            <Button
              size="sm"
              variant="outline"
              onClick={() => navigate(`/attendance?group=${encodeURIComponent(card.group)}`)}
            >
              {t('Открыть посещаемость')}
            </Button>
          )}
        </>
      }
    >
      <p className="muted">
        {missed.length === 0
          ? t('Пропусков за последний месяц нет')
          : `${t('Пропусков за последний месяц:')} ${missed.length}`}
      </p>
      {missed.length > 0 && (
        <Rows>
          {missed.slice(0, 8).map((day) => (
            <Row
              key={day.date}
              icon="calendar"
              tone="warn"
              title={asDate(day.date)}
              note={day.reason || t('причина не указана')}
              right={
                card.group ? (
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() =>
                      navigate(`/attendance?group=${encodeURIComponent(card.group)}&date=${day.date}`)
                    }
                  >
                    {t('Открыть день')}
                  </Button>
                ) : undefined
              }
            />
          ))}
        </Rows>
      )}

      <p className="muted cadm__note">
        {block.remarks.length === 0 ? t('Замечаний нет') : `${t('Замечаний:')} ${block.remarks.length}`}
      </p>
      <Rows>
        {block.remarks.map((remark) => (
          <Row
            key={remark.id}
            icon="alert"
            title={remark.text}
            note={`${asDate(remark.date)}${remark.author ? ` · ${remark.author}` : ''}`}
            right={
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
        <div className="ctask__field">
          <Input
            value={text}
            placeholder={t('Замечание словами — за что именно')}
            aria-label={t('Замечание')}
            onChange={(event) => setText(event.target.value)}
          />
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
      )}
    </DataCard>
  )
}
