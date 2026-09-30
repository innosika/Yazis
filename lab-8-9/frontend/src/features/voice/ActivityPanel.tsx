import { useVoice } from '@/stores/voice'

function median(xs: number[]): number {
  if (!xs.length) return 0
  const s = [...xs].sort((a, b) => a - b)
  return s[Math.floor(s.length / 2)]!
}

function engineName(e: string): string {
  if (e.startsWith('groq')) return 'Whisper (cloud)'
  if (e.startsWith('local')) return 'Parakeet (local)'
  return e
}

export function ActivityPanel() {
  const activity = useVoice((s) => s.activity)
  const clear = useVoice((s) => s.clearActivity)
  const heard = activity.filter((a) => a.rejected !== 'echo')
  const understood = heard.filter((a) => a.command)
  const latency = median(activity.map((a) => a.asrMs + a.matchMs))
  return (
    <div className="grid">
      <div className="flex items-center justify-between border-b border-line px-4 py-3">
        <h3 className="text-[13px] font-semibold text-ink">Voice activity</h3>
        {activity.length > 0 && (
          <button onClick={clear} className="text-[12.5px] text-ink-muted hover:text-ink">Clear</button>
        )}
      </div>
      {activity.length === 0 ? (
        <p className="px-4 py-6 text-[13px] leading-relaxed text-ink-muted">
          Nothing heard yet. Every phrase you say appears here with what Lector understood, which recogniser answered and how long it took.
        </p>
      ) : (
        <>
          <dl className="grid grid-cols-3 gap-2 border-b border-line px-4 py-3">
            <div>
              <dt className="text-[12px] text-ink-muted">Understood</dt>
              <dd className="text-base font-semibold text-ink tabular-nums">{heard.length ? Math.round((understood.length / heard.length) * 100) : 0}%</dd>
            </div>
            <div>
              <dt className="text-[12px] text-ink-muted">Median response</dt>
              <dd className="text-base font-semibold text-ink tabular-nums">{Math.round(latency)} ms</dd>
            </div>
            <div>
              <dt className="text-[12px] text-ink-muted">Last engine</dt>
              <dd className="truncate text-[13px] font-medium text-ink">{engineName(activity[0]!.engine)}</dd>
            </div>
          </dl>
          <ol className="scroll-thin max-h-80 overflow-y-auto">
            {activity.map((a) => (
              <li key={a.id} className="grid gap-0.5 border-b border-line px-4 py-2.5 last:border-0">
                <div className="flex items-baseline justify-between gap-3">
                  <span className="truncate text-[13px] text-ink">“{a.transcript || '…'}”</span>
                  <time className="shrink-0 text-[11.5px] text-ink-faint tabular-nums">{new Date(a.at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}</time>
                </div>
                <div className="flex flex-wrap items-center gap-x-2 text-[12px] text-ink-muted">
                  {a.command ? (
                    <span className="text-success">{a.title}</span>
                  ) : (
                    <span>{a.rejected === 'echo' ? 'Ignored: Lector’s own voice' : a.rejected === 'no command' ? 'Not a command' : `Ignored: ${a.rejected}`}</span>
                  )}
                  {a.method && <span>by {a.method === 'llm' ? 'language model' : a.method}{a.confidence !== null ? `, ${Math.round(a.confidence * 100)}%` : ''}</span>}
                  <span>{engineName(a.engine)}, {Math.round(a.asrMs + a.matchMs)} ms</span>
                </div>
              </li>
            ))}
          </ol>
        </>
      )}
    </div>
  )
}
