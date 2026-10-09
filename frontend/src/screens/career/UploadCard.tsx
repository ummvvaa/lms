/**
 * Загрузка теста файлом: сначала проверка без записи — что нашлось и что не так,
 * по листу и строке, — потом «Загрузить». Формат — `guides/CAREER_TESTS.md`,
 * пустой шаблон скачивается с экрана.
 */
import { useRef, useState } from 'react'
import { toast } from 'sonner'
import { useCareerPreview, useCareerUpload, type CareerFileReport } from '../../api/career'
import { downloadFile } from '../../api/client'
import Modal from '../../components/Modal'
import { Row, Rows, ShowAll } from '../../components/patterns'
import { Chip, ErrorNote, Loading } from '../../components/ui'
import { Button } from '../../components/ui/button'
import { Input } from '../../components/ui/input'
import { t, tn } from '../../i18n'

function Report({ data }: { data: CareerFileReport }) {
  return (
    <>
      <Chip tone={data.errors.length ? 'bad' : data.warnings.length ? 'warn' : 'good'}>
        {data.errors.length ? tn(data.errors.length, '{n} ошибка — тест не запишется|{n} ошибки — тест не запишется|{n} ошибок — тест не запишется') : t('можно загружать')}
      </Chip>
      {data.title && (
        <p className="acad__note">
          <b>{data.title}</b>
          {' · '}
          {[tn(data.items, '{n} утверждение|{n} утверждения|{n} утверждений'), tn(data.scales.length, '{n} шкала|{n} шкалы|{n} шкал'), tn(data.options.length, '{n} вариант ответа|{n} варианта ответа|{n} вариантов ответа'), t('порог для разбора {n}', { n: data.threshold })].join(' · ')}
        </p>
      )}
      {data.errors.length > 0 && (
        <Rows>
          <ShowAll limit={10}>
            {data.errors.map((text) => (
              <Row key={text} icon="alert" tone="bad" title={text} />
            ))}
          </ShowAll>
        </Rows>
      )}
      {data.warnings.length > 0 && (
        <Rows>
          <ShowAll limit={10}>
            {data.warnings.map((text) => (
              <Row key={text} icon="alert" tone="warn" title={text} />
            ))}
          </ShowAll>
        </Rows>
      )}
      {data.scales.length > 0 && (
        <Rows>
          <ShowAll limit={8}>
            {data.scales.map((scale) => (
              <Row key={scale.code} icon="compass" title={scale.title} note={scale.code} />
            ))}
          </ShowAll>
        </Rows>
      )}
    </>
  )
}

export default function UploadCard({ onClose }: { onClose: () => void }) {
  const fileInput = useRef<HTMLInputElement>(null)
  const [file, setFile] = useState<File | null>(null)
  const [data, setData] = useState<CareerFileReport | null>(null)
  const preview = useCareerPreview()
  const upload = useCareerUpload()

  return (
    <Modal wide title={t('Загрузить тест')} note={t('Книга xlsx: «Тест», «Ответы», «Шкалы», «Вопросы», «Интерпретация». Сначала проверка, база не меняется.')} onClose={onClose}>
      <div className="acad__import">
        <Input
          ref={fileInput}
          type="file"
          accept=".xlsx"
          className="users__file"
          onChange={(event) => {
            const picked = event.target.files?.[0]
            event.target.value = ''
            if (!picked) return
            setFile(picked)
            setData(null)
            preview.mutate(picked, { onSuccess: setData })
          }}
        />
        <div className="toolbar mb-0">
          <Button variant="outline" size="sm" onClick={() => fileInput.current?.click()}>
            {t('Выбрать файл')}
          </Button>
          <Button variant="link" size="sm" onClick={() => void downloadFile('/career/tests/template/', 'career-test-template.xlsx').catch((error: Error) => toast.error(error.message))}>
            {t('Скачать шаблон')}
          </Button>
          {file && <span className="muted">{file.name}</span>}
        </div>
        {preview.isPending && <Loading />}
        {preview.isError && <ErrorNote error={preview.error} />}
        {data && <Report data={data} />}
      </div>
      <div className="toolbar ctest__foot">
        <Button
          disabled={!data?.ok || upload.isPending || !file}
          onClick={() =>
            file &&
            upload.mutate(file, {
              onSuccess: (test) => {
                toast.success(t('Тест «{title}» загружен — включите его и назначьте группам', { title: test.title }))
                onClose()
              },
              onError: (error) => toast.error(error.message),
            })
          }
        >
          {upload.isPending ? t('Загружается…') : t('Загрузить')}
        </Button>
        <Button variant="outline" onClick={onClose}>
          {t('Отмена')}
        </Button>
      </div>
    </Modal>
  )
}
