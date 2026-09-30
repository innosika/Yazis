import { useState } from 'react'

import { ParseTree } from '@/components/translate/ParseTree'
import { Badge, EmptyState, Hint, Select } from '@/components/ui/primitives'
import { classes } from '@/lib/format'
import type { TokenInfo, Tree } from '@/lib/types'

/**
 * Tab 2 of the assignment: "the built syntactic parse tree of a chosen sentence".
 *
 * The sentence is chosen from a list, the tree is drawn above, and the token table below
 * gives the same analysis in a form that can be read row by row - which is what the
 * grammatical-information requirement actually needs.
 */
export function TreeTab({ trees, tokens }: { trees: Tree[]; tokens: TokenInfo[] }) {
  const [index, setIndex] = useState(0)

  if (trees.length === 0) {
    return <EmptyState title="No sentences to analyse" body="Translate a text first." />
  }

  const selected = trees[Math.min(index, trees.length - 1)]
  const sentenceTokens = tokens.filter((token) => token.sentence === selected.sentence)

  return (
    <div>
      <div className="flex flex-wrap items-center gap-3 border-b border-line px-4 py-2.5">
        <label
          htmlFor="tree-sentence"
          className="flex items-center gap-1.5 text-xs font-medium text-ink-muted no-print"
        >
          Sentence
          <Hint text="The tree is a dependency parse: every word points at its syntactic head, and the head of the main clause points at itself. This is the same structure the transfer rules read when they assign cases and reorder the sentence." />
        </label>
        <Select
          id="tree-sentence"
          value={String(index)}
          onChange={(event) => setIndex(Number(event.target.value))}
          className="max-w-2xl no-print"
        >
          {trees.map((tree, position) => (
            <option key={tree.sentence} value={position}>
              {position + 1}. {tree.text.slice(0, 110)}
              {tree.text.length > 110 ? '…' : ''}
            </option>
          ))}
        </Select>
        <span className="nums ml-auto text-xs text-ink-faint">
          {sentenceTokens.length} tokens · depth {depthOf(selected)}
        </span>
      </div>

      <p className="border-b border-line bg-source/40 px-4 py-2.5 text-[15px] leading-relaxed text-ink">
        {selected.text}
      </p>

      {selected.root ? (
        <ParseTree root={selected.root} />
      ) : (
        <EmptyState title="This sentence has no parse" body="It contains no analysable words." />
      )}

      <div className="scroll-thin max-h-[40vh] overflow-auto border-t border-line">
        <table className="w-full border-collapse text-sm">
          <caption className="sr-only">Token-by-token analysis of the selected sentence</caption>
          <thead className="sticky top-0 bg-raised">
            <tr className="border-b border-line text-left">
              {['#', 'Token', 'Lemma', 'Part of speech', 'Tag', 'Features', 'Role', 'Head', 'Russian'].map(
                (heading) => (
                  <th
                    key={heading}
                    scope="col"
                    className="px-3 py-2 text-[11px] font-semibold tracking-wide text-ink-faint uppercase"
                  >
                    {heading}
                  </th>
                ),
              )}
            </tr>
          </thead>
          <tbody>
            {sentenceTokens.map((token) => (
              <tr
                key={token.index}
                className={classes(
                  'border-b border-line last:border-0 hover:bg-raised',
                  token.dropped_by_rule && 'text-ink-faint',
                )}
              >
                <td className="nums px-3 py-1.5 text-xs text-ink-faint">{token.index}</td>
                <td className="px-3 py-1.5 font-medium text-ink">{token.text}</td>
                <td className="px-3 py-1.5 text-ink-muted">{token.lemma}</td>
                <td className="px-3 py-1.5 text-ink-muted">{token.pos_name}</td>
                <td className="px-3 py-1.5">
                  <code className="font-mono text-[11px] text-ink" title={token.tag_name}>
                    {token.tag}
                  </code>
                </td>
                <td className="px-3 py-1.5 text-xs text-ink-muted">
                  {token.features.join(' · ') || '—'}
                </td>
                <td className="px-3 py-1.5">
                  <code className="font-mono text-[11px] text-ink-muted">{token.dep}</code>
                </td>
                <td className="px-3 py-1.5 text-xs text-ink-faint">
                  {token.head === token.index
                    ? 'root'
                    : (sentenceTokens.find((item) => item.index === token.head)?.text ?? '—')}
                </td>
                <td className="px-3 py-1.5">
                  {token.dropped_by_rule ? (
                    <Badge tone="neutral" title={token.note}>
                      dropped
                    </Badge>
                  ) : token.translation ? (
                    <span title={token.target_decoded.join(', ')} className="text-ink">
                      {token.translation}
                    </span>
                  ) : (
                    <span className="text-ink-faint">—</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function depthOf(tree: Tree): number {
  const walk = (node: typeof tree.root, level = 0): number =>
    node ? Math.max(level, ...node.children.map((child) => walk(child, level + 1))) : 0
  return walk(tree.root)
}
