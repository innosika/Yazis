import { DetectResult, LANG_FLAG, LANG_NAME, METHOD_ORDER, MethodInfo } from '../api'
import { Hint } from './Hint'
import { MethodCard } from './MethodCard'

export function ResultsView({ result, methods, truth }: { result: DetectResult; methods: MethodInfo[]; truth?: string }) {
  const infoOf = (id: string) => methods.find(m => m.id === id)
  const ordered = [...result.results].sort((a, b) => METHOD_ORDER.indexOf(a.method) - METHOD_ORDER.indexOf(b.method))
  return (
    <div style={{ display: 'grid', gap: 16 }}>
      <div className="consensus">
        <div>
          <div className="muted" style={{ fontSize: '.8rem' }}>Итог (голосование методов)</div>
          <div className="big">{result.consensus ? `${LANG_FLAG[result.consensus]} ${LANG_NAME[result.consensus]}` : '—'}</div>
        </div>
        <span className={'badge ' + (result.agree ? 'ok' : 'warn')}>{result.agree ? 'все методы согласны' : 'методы расходятся'}</span>
        <Hint text="Итоговый язык — тот, за который проголосовало большинство из трёх методов. Если методы расходятся, посмотрите на уверенность каждого: чаще всего ошибается тот, у кого она минимальна." />
        <span className="spacer" style={{ flex: 1 }} />
        <small>{result.text_chars.toLocaleString('ru-RU')} символов · {result.words.toLocaleString('ru-RU')} слов</small>
      </div>
      <div className="grid grid-3">
        {ordered.map(det => <MethodCard key={det.method} det={det} info={infoOf(det.method)} truth={truth} />)}
      </div>
    </div>
  )
}
