import { useState } from 'react'
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Curve, Info, METHOD_COLOR, METHOD_ORDER, api, fmtMs, pct } from '../api'
import { Hint } from '../components/Hint'

const DEFAULT_LENGTHS = [5, 10, 20, 40, 80, 160, 320, 640, 1280]

export function CurvePage({ info }: { info: Info }) {
  const [curve, setCurve] = useState<Curve | null>(null)
  const [busy, setBusy] = useState(false)
  const [samples, setSamples] = useState(6)
  const [error, setError] = useState<string | null>(null)
  const methods = METHOD_ORDER.filter(m => info.methods.some(x => x.id === m))
  const titleOf = (m: string) => info.methods.find(x => x.id === m)?.title ?? m

  const run = async () => {
    setBusy(true); setError(null)
    try { setCurve(await api.curve(DEFAULT_LENGTHS, samples)) } catch (e: any) { setError(e.message) } finally { setBusy(false) }
  }
  const data = curve?.points.map(p => ({
    length: p.length,
    ...Object.fromEntries(methods.map(m => [m, +(p[m].accuracy * 100).toFixed(1)])),
  }))

  return (
    <>
      <div className="card">
        <div className="card-head">
          <h2>Кривая обучения: точность vs длина текста</h2>
          <Hint text="Из каждого документа коллекции случайно вырезаются фрагменты заданной длины (в символах), и каждый метод пытается определить их язык. График показывает, сколько текста нужно каждому методу для уверенного ответа. Это и есть ответ на вопрос «какой метод лучше на коротких сообщениях, а какой — на длинных документах»." />
          <span className="spacer" />
          <label className="row" style={{ gap: 6 }}>
            <small>фрагментов на документ</small>
            <select value={samples} onChange={e => setSamples(+e.target.value)}>{[2, 4, 6, 10, 15].map(n => <option key={n} value={n}>{n}</option>)}</select>
          </label>
          <button className="btn primary" disabled={busy} onClick={run}>{busy ? <span className="spinner" /> : '📈'} Построить</button>
        </div>
        <p className="muted" style={{ margin: 0, fontSize: '.9rem' }}>
          Длины фрагментов: {DEFAULT_LENGTHS.join(', ')} символов. Для каждой длины и метода считается доля верно распознанных фрагментов
          ({curve ? `${curve.documents} документов × ${curve.samples_per_doc} фрагментов = ${curve.documents * curve.samples_per_doc} проверок на точку` : 'документов × фрагментов'}).
        </p>
        {error && <div className="alert error" style={{ marginTop: 12 }}>{error}</div>}
      </div>

      {curve && data && (
        <>
          <div className="card" style={{ marginTop: 16 }}>
            <div style={{ width: '100%', height: 360 }}>
              <ResponsiveContainer>
                <LineChart data={data} margin={{ top: 10, right: 20, left: 0, bottom: 10 }}>
                  <CartesianGrid stroke="#eee" strokeDasharray="3 3" />
                  <XAxis dataKey="length" scale="log" type="number" domain={['dataMin', 'dataMax']} ticks={DEFAULT_LENGTHS}
                    label={{ value: 'длина фрагмента, символов (лог. шкала)', position: 'insideBottom', offset: -4, fontSize: 12 }} tick={{ fontSize: 12 }} />
                  <YAxis domain={[(min: number) => Math.max(0, Math.floor((min - 3) / 5) * 5), 100]} unit="%" tick={{ fontSize: 12 }} width={48} allowDecimals={false} />
                  <Tooltip formatter={(v: any, name: any) => [`${v}%`, titleOf(String(name))]} labelFormatter={l => `${l} символов`} />
                  <Legend formatter={(v) => titleOf(String(v))} />
                  {methods.map(m => (
                    <Line key={m} type="monotone" dataKey={m} stroke={METHOD_COLOR[m]} strokeWidth={2.5} dot={{ r: 4 }} activeDot={{ r: 6 }} isAnimationActive={false} />
                  ))}
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>

          <div className="grid grid-2" style={{ marginTop: 16 }}>
            <div className="card">
              <div className="card-head"><h3>Минимальная длина для точности ≥ 95%</h3>
                <Hint text="Первая длина фрагмента, начиная с которой метод отвечает верно не менее чем в 95% случаев. Чем меньше — тем лучше метод справляется с коротким текстом." /></div>
              <table className="tbl">
                <tbody>
                  {methods.map(m => (
                    <tr key={m}><td><span style={{ display: 'inline-block', width: 10, height: 10, borderRadius: 5, background: METHOD_COLOR[m], marginRight: 8 }} />{titleOf(m)}</td>
                      <td className="num mono">{curve.min_length_95[m] != null ? `${curve.min_length_95[m]} симв.` : 'не достигнута'}</td></tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="card">
              <div className="card-head"><h3>Таблица точности и времени</h3></div>
              <div className="tbl-wrap">
                <table className="tbl">
                  <thead><tr><th className="num">Длина</th>{methods.map(m => <th key={m}>{titleOf(m)}</th>)}</tr></thead>
                  <tbody>
                    {curve.points.map(p => (
                      <tr key={p.length}><td className="num mono">{p.length}</td>
                        {methods.map(m => <td key={m} className={p[m].accuracy >= 0.95 ? 'ok' : p[m].accuracy < 0.7 ? 'bad' : ''}>{pct(p[m].accuracy)}<br /><small className="mono">{fmtMs(p[m].avg_time_ms)}</small></td>)}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </>
      )}
    </>
  )
}
