import { mergeProps } from '@base-ui/react/merge-props'
import { useRender } from '@base-ui/react/use-render'
import { cva, type VariantProps } from 'class-variance-authority'

import { cn } from '@/lib/utils'

const badgeVariants = cva(
  'group/badge inline-flex h-5 w-fit shrink-0 items-center justify-center gap-1 overflow-hidden rounded-4xl border border-transparent px-2 py-0.5 text-xs font-medium whitespace-nowrap transition-all focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50 has-data-[icon=inline-end]:pr-1.5 has-data-[icon=inline-start]:pl-1.5 aria-invalid:border-destructive aria-invalid:ring-destructive/20 dark:aria-invalid:ring-destructive/40 [&>svg]:pointer-events-none [&>svg]:size-3!',
  {
    variants: {
      variant: {
        default: 'bg-primary text-primary-foreground [a]:hover:bg-primary/80',
        secondary: 'bg-secondary text-secondary-foreground [a]:hover:bg-secondary/80',
        destructive:
          'bg-destructive/10 text-destructive focus-visible:ring-destructive/20 dark:bg-destructive/20 dark:focus-visible:ring-destructive/40 [a]:hover:bg-destructive/20',
        outline: 'border-border text-foreground [a]:hover:bg-muted [a]:hover:text-muted-foreground',
        ghost: 'hover:bg-muted hover:text-muted-foreground dark:hover:bg-muted/50',
        link: 'text-primary underline-offset-4 hover:underline',
        /* Тона состояний: подложка `*-bg`, текст `*`. Обычного красного
           нет — «плохо» тёмно-красный, рядом с оранжевым он читается
           как тревога, а алый — нет */
        good: 'bg-[var(--good-bg)] text-[var(--good)]',
        warn: 'bg-[var(--warn-bg)] text-[var(--warn)]',
        bad: 'bg-[var(--bad-bg)] text-[var(--bad)]',
        info: 'bg-[var(--info-bg)] text-[var(--info)]',
        neutral: 'bg-[var(--neutral-bg)] text-[var(--ink-2)]',
        accent: 'bg-[var(--accent-bg)] text-[var(--accent-ink)]',
        /* Прежние имена тонов — псевдонимы новых, чтобы старые вызовы
           не сломались: бирюзы и индиго в языке больше нет, их место
           заняли нейтральная пометка и вторичный графит */
        ok: 'bg-[var(--good-bg)] text-[var(--good)]',
        risk: 'bg-[var(--bad-bg)] text-[var(--bad)]',
        brand: 'bg-[var(--accent-bg)] text-[var(--accent-ink)]',
        mute: 'bg-[var(--neutral-bg)] text-[var(--ink-2)]',
        teal: 'bg-[var(--info-bg)] text-[var(--info)]',
        indigo: 'bg-[var(--neutral-bg)] text-[var(--ink-2)]',
      },
    },
    defaultVariants: {
      variant: 'default',
    },
  },
)

function Badge({
  className,
  variant = 'default',
  render,
  ...props
}: useRender.ComponentProps<'span'> & VariantProps<typeof badgeVariants>) {
  return useRender({
    defaultTagName: 'span',
    props: mergeProps<'span'>(
      {
        className: cn(badgeVariants({ variant }), className),
      },
      props,
    ),
    render,
    state: {
      slot: 'badge',
      variant,
    },
  })
}

export type BadgeVariant = NonNullable<VariantProps<typeof badgeVariants>['variant']>

export { Badge, badgeVariants }
