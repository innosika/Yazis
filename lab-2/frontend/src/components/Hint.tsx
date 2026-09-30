import { ReactNode } from 'react'

/** Всплывающая подсказка «?» — наводите мышь или фокусируйте с клавиатуры. */
export function Hint({ text, left }: { text: ReactNode; left?: boolean }) {
  return (
    <span className="hint">
      <button type="button" aria-label="Подсказка">?</button>
      <span className={'tip' + (left ? ' left' : '')} role="tooltip">{text}</span>
    </span>
  )
}
