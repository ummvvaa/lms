/**
 * Перехватчик ошибок вокруг дерева приложения.
 *
 * Необработанное исключение при рендере размонтирует всё дерево React,
 * и директор видит белую страницу — «система сломалась совсем». Так
 * в фазе 32 и вышло с меню профиля: подпись группы стояла вне группы,
 * Base UI бросал исключение, и белел весь экран.
 *
 * Здесь падение превращается в сообщение и кнопку «Обновить». Ошибка
 * пишется в консоль и уходит в Sentry, если он подключён на странице.
 * Границ две: внешняя вокруг всего приложения и внутренняя вокруг
 * содержимого экрана — чтобы упавший раздел не уносил с собой меню.
 */
import { Component, type ErrorInfo, type ReactNode } from 'react'
import { t } from '../i18n'
import { Button } from './ui/button'

interface Props {
  children: ReactNode
  /** «экран» — внутри каркаса, меню остаётся; «всё» — сам каркас упал */
  scope?: 'screen' | 'app'
}

interface State {
  error: Error | null
}

/** Sentry, если его подключили тегом на странице. Своей зависимости нет. */
function report(error: Error, info: ErrorInfo) {
  console.error('Необработанная ошибка интерфейса:', error, info.componentStack)
  const sentry = (globalThis as { Sentry?: { captureException?: (e: unknown, ctx?: unknown) => void } })
    .Sentry
  sentry?.captureException?.(error, { extra: { componentStack: info.componentStack } })
}

export default class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    report(error, info)
  }

  render() {
    const { error } = this.state
    if (!error) return this.props.children
    const scope = this.props.scope ?? 'screen'
    return (
      <div className={`crash crash--${scope}`} role="alert">
        <div className="crash__box card card-pad">
          <b className="crash__title">{t('Этот экран не открылся')}</b>
          <p className="muted crash__what">
            {t(
              'Произошла ошибка в интерфейсе. Данные не пострадали — обновите страницу и попробуйте ещё раз.',
            )}
          </p>
          <code className="crash__detail">{error.message}</code>
          <div className="crash__actions">
            <Button onClick={() => window.location.reload()}>{t('Обновить')}</Button>
            {scope === 'screen' && (
              <Button
                variant="outline"
                onClick={() => {
                  window.location.assign('/dashboard')
                }}
              >
                {t('На дашборд')}
              </Button>
            )}
          </div>
        </div>
      </div>
    )
  }
}
