import { useMemo, useState } from 'react'

import { classes } from '@/lib/format'
import type { TreeNode } from '@/lib/types'

/**
 * The dependency tree of one sentence, drawn as SVG.
 *
 * Layout is Reingold-Tilford in its simplest honest form: a leaf takes one column, an
 * internal node sits above the centre of its children, and depth sets the row. That is
 * enough for sentence-sized trees and it keeps the drawing deterministic - the same
 * sentence always looks the same, which matters when the picture is being explained to
 * someone.
 *
 * Each node carries the word, its fine tag and its Russian equivalent, so the tree answers
 * the two questions the assignment cares about - what is the structure, and what did each
 * node become - without a legend.
 */

const NODE_WIDTH = 132
const NODE_HEIGHT = 58
const COLUMN_GAP = 16
const ROW_GAP = 34
const PADDING = 24

interface Placed {
  node: TreeNode
  x: number
  y: number
  parent?: Placed
}

const POS_TONE: Record<string, string> = {
  VERB: 'fill-[var(--c-accent-soft)] stroke-[var(--c-accent)]',
  AUX: 'fill-[var(--c-accent-soft)] stroke-[var(--c-accent)]',
  NOUN: 'fill-[var(--c-target)] stroke-[var(--c-target-border)]',
  PROPN: 'fill-[var(--c-target)] stroke-[var(--c-target-border)]',
  PRON: 'fill-[var(--c-target)] stroke-[var(--c-target-border)]',
  ADJ: 'fill-[var(--c-source)] stroke-[var(--c-source-border)]',
  ADV: 'fill-[var(--c-source)] stroke-[var(--c-source-border)]',
  PUNCT: 'fill-[var(--c-sunken)] stroke-[var(--c-border)]',
}

export function ParseTree({ root }: { root: TreeNode }) {
  const [selected, setSelected] = useState<number | null>(null)

  const { placed, width, height } = useMemo(() => layout(root), [root])
  const active = placed.find((item) => item.node.id === selected)?.node

  return (
    <div>
      <div className="scroll-thin overflow-auto border-b border-line">
        <svg
          width={width}
          height={height}
          viewBox={`0 0 ${width} ${height}`}
          role="img"
          aria-label={`Dependency tree with ${placed.length} nodes`}
          className="block"
        >
          {placed.map(
            (item) =>
              item.parent && (
                <g key={`edge-${item.node.id}`}>
                  <path
                    d={edge(item.parent, item)}
                    fill="none"
                    className="stroke-[var(--c-border-strong)]"
                    strokeWidth={1.4}
                  />
                  <text
                    x={(item.parent.x + NODE_WIDTH / 2 + item.x + NODE_WIDTH / 2) / 2}
                    y={item.y - 8}
                    textAnchor="middle"
                    className="fill-[var(--c-ink-faint)] font-mono text-[9px]"
                  >
                    {item.node.dep}
                  </text>
                </g>
              ),
          )}

          {placed.map((item) => (
            <g
              key={item.node.id}
              transform={`translate(${item.x}, ${item.y})`}
              onClick={() => setSelected(item.node.id)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' || event.key === ' ') {
                  event.preventDefault()
                  setSelected(item.node.id)
                }
              }}
              tabIndex={0}
              role="button"
              aria-label={`${item.node.text}, ${item.node.pos_name}, ${item.node.dep_description}`}
              className="cursor-pointer outline-none focus-visible:[&>rect]:stroke-[var(--c-accent)]"
            >
              <rect
                width={NODE_WIDTH}
                height={NODE_HEIGHT}
                rx={6}
                strokeWidth={selected === item.node.id ? 2 : 1}
                className={classes(
                  POS_TONE[item.node.upos] ?? 'fill-[var(--c-raised)] stroke-[var(--c-border)]',
                  selected === item.node.id && 'stroke-[var(--c-accent)]',
                )}
              />
              <text
                x={NODE_WIDTH / 2}
                y={19}
                textAnchor="middle"
                className="fill-[var(--c-ink)] text-[13px] font-semibold"
              >
                {clip(item.node.text, 16)}
              </text>
              <text
                x={NODE_WIDTH / 2}
                y={33}
                textAnchor="middle"
                className="fill-[var(--c-ink-faint)] font-mono text-[9px]"
              >
                {item.node.tag}
              </text>
              <text
                x={NODE_WIDTH / 2}
                y={48}
                textAnchor="middle"
                className="fill-[var(--c-ink-muted)] text-[12px]"
              >
                {item.node.translation ? clip(item.node.translation, 17) : '—'}
              </text>
            </g>
          ))}
        </svg>
      </div>

      <div className="flex flex-wrap items-start gap-x-6 gap-y-2 px-4 py-3 text-xs">
        {active ? (
          <dl className="grid flex-1 grid-cols-[auto_1fr] gap-x-3 gap-y-1">
            <dt className="font-medium text-ink-faint">Word</dt>
            <dd className="text-ink">
              {active.text}
              {active.lemma !== active.text.toLowerCase() && (
                <span className="text-ink-faint"> · lemma “{active.lemma}”</span>
              )}
            </dd>
            <dt className="font-medium text-ink-faint">Part of speech</dt>
            <dd className="text-ink">
              {active.pos_name} · <code className="font-mono">{active.tag}</code> {active.tag_name}
            </dd>
            <dt className="font-medium text-ink-faint">Role</dt>
            <dd className="text-ink">
              <code className="font-mono">{active.dep}</code> — {active.dep_description}
            </dd>
            {active.features.length > 0 && (
              <>
                <dt className="font-medium text-ink-faint">Features</dt>
                <dd className="text-ink">{active.features.join(' · ')}</dd>
              </>
            )}
            {active.translation && (
              <>
                <dt className="font-medium text-ink-faint">Russian</dt>
                <dd className="text-ink">
                  {active.translation}
                  {active.target_decoded.length > 0 && (
                    <span className="text-ink-faint"> · {active.target_decoded.join(', ')}</span>
                  )}
                </dd>
              </>
            )}
          </dl>
        ) : (
          <p className="flex-1 text-ink-faint">
            Select a node to see its full analysis. The label on each edge is the dependency
            relation; the line under each word is the Russian form it produced.
          </p>
        )}

        <ul className="flex flex-wrap gap-2.5 text-[11px] text-ink-muted no-print">
          {[
            ['verb', 'var(--c-accent-soft)', 'var(--c-accent)'],
            ['noun / pronoun', 'var(--c-target)', 'var(--c-target-border)'],
            ['adjective / adverb', 'var(--c-source)', 'var(--c-source-border)'],
            ['other', 'var(--c-raised)', 'var(--c-border)'],
          ].map(([label, background, border]) => (
            <li key={label} className="flex items-center gap-1.5">
              <span
                aria-hidden="true"
                className="inline-block size-3 rounded-sm border"
                style={{ background, borderColor: border }}
              />
              {label}
            </li>
          ))}
        </ul>
      </div>
    </div>
  )
}

function layout(root: TreeNode): { placed: Placed[]; width: number; height: number } {
  const placed: Placed[] = []
  let column = 0
  let maxDepth = 0

  const walk = (node: TreeNode, depth: number, parent?: Placed): Placed => {
    maxDepth = Math.max(maxDepth, depth)
    const y = PADDING + depth * (NODE_HEIGHT + ROW_GAP)

    if (node.children.length === 0) {
      const item: Placed = { node, x: PADDING + column * (NODE_WIDTH + COLUMN_GAP), y, parent }
      column += 1
      placed.push(item)
      return item
    }

    const item: Placed = { node, x: 0, y, parent }
    placed.push(item)
    const children = node.children.map((child) => walk(child, depth + 1, item))
    // Centre the parent over the span its children occupy.
    const first = children[0].x
    const last = children[children.length - 1].x
    item.x = (first + last) / 2
    return item
  }

  walk(root, 0)
  return {
    placed,
    width: Math.max(PADDING * 2 + column * (NODE_WIDTH + COLUMN_GAP), 320),
    height: PADDING * 2 + (maxDepth + 1) * NODE_HEIGHT + maxDepth * ROW_GAP,
  }
}

/** A vertical-then-horizontal curve: easier to follow than a straight diagonal. */
function edge(from: Placed, to: Placed): string {
  const x1 = from.x + NODE_WIDTH / 2
  const y1 = from.y + NODE_HEIGHT
  const x2 = to.x + NODE_WIDTH / 2
  const y2 = to.y
  const midpoint = y1 + (y2 - y1) / 2
  return `M ${x1} ${y1} C ${x1} ${midpoint}, ${x2} ${midpoint}, ${x2} ${y2}`
}

function clip(text: string, limit: number): string {
  return text.length > limit ? `${text.slice(0, limit - 1)}…` : text
}
