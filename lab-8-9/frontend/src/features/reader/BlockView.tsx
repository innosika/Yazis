import katex from 'katex'
import { memo, useCallback, useMemo, type ReactNode } from 'react'

import { cx } from '@/components/ui/primitives'
import type { Block } from '@/lib/types'
import { registerBlockElement, usePlayer } from '@/stores/player'

interface Segment {
  o: number
  text: string
  math: boolean
}

function segments(text: string, from: number, to: number, math: [number, number][]): Segment[] {
  const out: Segment[] = []
  let pos = from
  for (const [a, b] of math) {
    if (b <= from || a >= to) continue
    if (a > pos) out.push({ o: pos, text: text.slice(pos, a), math: false })
    out.push({ o: a, text: text.slice(a, b), math: true })
    pos = b
  }
  if (pos < to) out.push({ o: pos, text: text.slice(pos, to), math: false })
  return out
}

const texCache = new Map<string, string>()

function renderTex(source: string, display: boolean): string {
  const key = `${display ? 'd' : 'i'}${source}`
  const hit = texCache.get(key)
  if (hit) return hit
  const tex = source.replace(/^\\\(|\\\)$/g, '').replace(/^\$|\$$/g, '')
  const html = katex.renderToString(tex, { throwOnError: false, displayMode: display, strict: 'ignore', output: 'htmlAndMathml' })
  texCache.set(key, html)
  return html
}

function Seg({ seg, display }: { seg: Segment; display: boolean }) {
  if (seg.math) {
    return (
      <span
        data-o={seg.o}
        data-l={seg.text.length}
        data-atomic="1"
        className={display ? 'block overflow-x-auto py-2 text-center' : undefined}
        dangerouslySetInnerHTML={{ __html: renderTex(seg.text, display) }}
      />
    )
  }
  return (
    <span data-o={seg.o} data-l={seg.text.length}>
      {seg.text}
    </span>
  )
}

const HEADING_NUMBER = /^((?:\d+(?:\.\d+)*|[A-Z]|[IVX]+)\.?)\s+/

function Content({ block, index, current }: { block: Block; index: number; current: number }) {
  const jump = useCallback(
    (sentence: number) => {
      const p = usePlayer.getState()
      const selection = window.getSelection()
      if (selection && !selection.isCollapsed) return // the user is selecting text
      void p.jumpToSentence(index, sentence, true)
    },
    [index],
  )
  const display = block.kind === 'equation'
  const nodes: ReactNode[] = []
  let pos = 0
  block.sentences.forEach((s, si) => {
    if (s.start > pos) nodes.push(<Seg key={`g${pos}`} seg={{ o: pos, text: block.text.slice(pos, s.start), math: false }} display={false} />)
    let segs = segments(block.text, s.start, s.end, block.math)
    let number: ReactNode = null
    if (block.kind === 'heading') {
      const m = block.text.match(HEADING_NUMBER)
      if (m) {
        const len = m[0].length
        number = (
          <span data-o={0} data-l={len} className="mr-2 text-ink-faint tabular-nums lg:absolute lg:right-full lg:mr-4 lg:w-16 lg:text-right">
            {block.text.slice(0, len)}
          </span>
        )
        segs = segments(block.text, len, s.end, block.math)
      }
    }
    nodes.push(
      <span
        key={`s${si}`}
        data-b={index}
        data-s={si}
        onClick={() => jump(si)}
        className={cx('sentence', si === current && 'is-current')}
      >
        {number}
        {segs.map((seg) => (
          <Seg key={seg.o} seg={seg} display={display} />
        ))}
      </span>,
    )
    pos = s.end
  })
  if (pos < block.text.length) nodes.push(<Seg key={`t${pos}`} seg={{ o: pos, text: block.text.slice(pos), math: false }} display={false} />)
  return <>{nodes}</>
}

export const BlockView = memo(function BlockView({ block, index, spoken }: { block: Block; index: number; spoken?: string }) {
  const current = usePlayer((s) => (s.snippet === null && s.block === index && s.status !== 'idle' ? s.sentence : -1))
  const ref = useCallback((el: HTMLElement | null) => registerBlockElement(index, el), [index])
  const body = useMemo(() => <Content block={block} index={index} current={current} />, [block, index, current])
  const spokenLine = spoken && spoken !== block.text ? <p className="spoken-form mt-1.5">{spoken}</p> : null

  if (block.kind === 'heading') {
    const level = Math.min(block.level || 1, 3)
    const cls = cx(
      'relative font-serif font-semibold tracking-[-0.01em] text-ink',
      level === 1 ? 'mt-14 mb-4 text-[1.55rem] leading-tight' : level === 2 ? 'mt-10 mb-3 text-[1.25rem] leading-snug' : 'mt-8 mb-2 text-[1.1rem] leading-snug',
    )
    const Tag = level === 1 ? 'h2' : level === 2 ? 'h3' : 'h4'
    return (
      <div id={`block-${index}`} className="scroll-mt-24">
        <Tag ref={ref} className={cls}>{body}</Tag>
        {spokenLine}
      </div>
    )
  }
  if (block.kind === 'item') {
    return (
      <div id={`block-${index}`} className="relative mb-2 pl-6">
        <span aria-hidden className="absolute top-[0.1em] left-1 text-ink-faint">•</span>
        <p ref={ref}>{body}</p>
        {spokenLine}
      </div>
    )
  }
  if (block.kind === 'equation') {
    return (
      <div id={`block-${index}`} className="my-5">
        <div ref={ref}>{body}</div>
        {spokenLine}
      </div>
    )
  }
  return (
    <div id={`block-${index}`} className="mb-5">
      <p ref={ref}>{body}</p>
      {spokenLine}
    </div>
  )
})
