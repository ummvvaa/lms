/**
 * Состав подгрупп английского файлом школы.
 *
 * Книга расписания говорит, из каких групп собрана подгруппа потока, но не
 * кто в ней учится; без состава урок подгруппы стоит у всех групп потока,
 * а ученик своего английского не видит. Здесь — список «подгруппа — ученик —
 * группа»: сначала проверка (база не меняется), потом «Применить». Разбор
 * и правила — на сервере (`academics/subgroup_members.py`).
 */
import { useRef, useState } from 'react'
import { toast } from 'sonner'
import { useSubgroupMembersApply, useSubgroupMembersCheck, type SubgroupMembersReport } from '../../api/academics'
import EditDrawer from '../../components/EditDrawer'
import Field from '../../components/Field'
import { Row, Rows, ShowAll } from '../../components/patterns'
import { Chip, ErrorNote, Loading } from '../../components/ui'
import { Button } from '../../components/ui/button'
import { Input } from '../../components/ui/input'
import { t, tn } from '../../i18n'
import { Block } from './ScheduleImport'
import { dateWords } from './shared'

type SubgroupRow = SubgroupMembersReport['subgroups'][number]

/** «17 учеников · придут 17 · уйдут 0» — что сделает запись с подгруппой. */
function subgroupNote(row: SubgroupRow): string {
  return [
    tn(row.students, '{n} ученик|{n} ученика|{n} учеников'),
    t('придут {n}', { n: row.joined }),
    t('уйдут {n}', { n: row.left }),
  ].join(' · ')
}

function Report({ data }: { data: SubgroupMembersReport }) {
  return (
    <>
      {/* чип — короткая пометка, подробности — строкой: длинная фраза в чипе обрезалась краем панели */}
      <Chip tone={data.errors.length ? 'bad' : data.warnings.length ? 'warn' : 'good'}>
        {data.errors.length
          ? tn(data.errors_total, '{n} ошибка — состав не запишется|{n} ошибки — состав не запишется|{n} ошибок — состав не запишется')
          : t('можно записать')}
      </Chip>
      <p className="acad__note">
        {t('Найдено учеников: {matched} из {lines} строк; состав запишется с {date}', {
          matched: data.matched,
          lines: data.lines,
          date: dateWords(data.since),
        })}
      </p>

      {data.errors.length > 0 && (
        <Block title={t('Ошибки — исправьте в файле и проверьте снова')} count={data.errors_total}>
          <Rows>
            <ShowAll limit={10}>
              {data.errors.map((text) => (
                <Row key={text} icon="alert" tone="bad" title={text} />
              ))}
            </ShowAll>
          </Rows>
        </Block>
      )}

      {/* файл школы — блоками: какой блок в какую подгруппу лёг, чтобы
          было видно, что кабинет указал верно */}
      {data.blocks.length > 0 && (
        <Block title={t('Блоки файла')} count={data.blocks.length}>
          <Rows>
            <ShowAll limit={12}>
              {data.blocks.map((block) => (
                <Row
                  key={`${block.sheet}|${block.header}|${block.subgroup}`}
                  icon={block.subgroup ? 'check' : 'alert'}
                  tone={block.subgroup ? 'good' : 'bad'}
                  title={block.subgroup ? `${block.header} → ${block.subgroup}` : block.header}
                  note={[block.sheet, tn(block.students, '{n} строка|{n} строки|{n} строк'), block.teacher].filter(Boolean).join(' · ')}
                />
              ))}
            </ShowAll>
          </Rows>
        </Block>
      )}

      {data.skipped.length > 0 && (
        <p className="acad__note">{t('Пропущены листы без подгрупп: {sheets}', { sheets: data.skipped.map((name) => `«${name.trim()}»`).join(', ') })}</p>
      )}

      {/* строками, а не таблицей: в узкой панели колонка названия
          ломала «EEP-11.2-1» по букве */}
      {data.subgroups.length > 0 && (
        <Block title={t('Подгруппы')} count={data.subgroups.length}>
          <Rows>
            <ShowAll limit={12}>
              {data.subgroups.map((row) => (
                <Row key={row.id} title={row.name} note={subgroupNote(row)} />
              ))}
            </ShowAll>
          </Rows>
        </Block>
      )}

      {data.warnings.length > 0 && (
        <Block title={t('Предупреждения — запись пойдёт, но проверьте')} count={data.warnings.length}>
          <Rows>
            <ShowAll limit={10}>
              {data.warnings.map((text) => (
                <Row key={text} icon="alert" tone="warn" title={text} />
              ))}
            </ShowAll>
          </Rows>
        </Block>
      )}
    </>
  )
}

export default function SubgroupMembersImport({ onClose }: { onClose: () => void }) {
  const fileInput = useRef<HTMLInputElement>(null)
  const [file, setFile] = useState<File | null>(null)
  // пусто — сервер берёт начало учебного года: журналы прошлых уроков получают своих учеников
  const [since, setSince] = useState('')
  const [data, setData] = useState<SubgroupMembersReport | null>(null)
  const check = useSubgroupMembersCheck()
  const apply = useSubgroupMembersApply()

  const run = (picked: File, date: string) =>
    check.mutate(
      { file: picked, since: date },
      {
        onSuccess: (report) => {
          setData(report)
          if (!date) setSince(report.since)
        },
      },
    )

  return (
    <EditDrawer
      open
      onClose={onClose}
      title={t('Состав подгрупп английского')}
      sub={t('Файл школы: блоки «учитель, уровень, кабинет» со списком ФИО — подгруппа по кабинету. У ученика одна подгруппа — EEP или GE.')}
      footer={
        <>
          <Button
            disabled={!data?.ok || apply.isPending || !file}
            onClick={() =>
              file &&
              apply.mutate(
                { file, since },
                {
                  onSuccess: (result) => {
                    toast.success(tn(result.subgroups.length, 'Состав записан: {n} подгруппа|Состав записан: {n} подгруппы|Состав записан: {n} подгрупп'))
                    onClose()
                  },
                  onError: (error) => toast.error(error.message),
                },
              )
            }
          >
            {apply.isPending ? t('Применяется…') : t('Применить')}
          </Button>
          <Button variant="outline" onClick={onClose}>
            {t('Отмена')}
          </Button>
        </>
      }
    >
      <div className="acad__import">
        <p className="muted">{t('Сначала проверка: база не меняется, пока не нажата «Применить». Повторная загрузка того же файла ничего не удваивает, новый файл переводит учеников с выбранной даты — прошлые оценки остаются в прежней подгруппе.')}</p>
        <Input
          ref={fileInput}
          type="file"
          accept=".xlsx,.xlsm"
          className="users__file"
          onChange={(event) => {
            const picked = event.target.files?.[0]
            event.target.value = ''
            if (!picked) return
            setFile(picked)
            setData(null)
            run(picked, since)
          }}
        />
        <div className="toolbar mb-0">
          <Button variant="outline" size="sm" onClick={() => fileInput.current?.click()}>
            {t('Выбрать файл')}
          </Button>
          {file && <span className="muted">{file.name}</span>}
        </div>
        <Field
          kind="date"
          name="since"
          label={t('Состав действует с')}
          value={since}
          onChange={(value) => {
            setSince(value)
            if (file) run(file, value)
          }}
        />
        {check.isPending && <Loading />}
        {check.isError && <ErrorNote error={check.error} />}
        {data && <Report data={data} />}
      </div>
    </EditDrawer>
  )
}
