import { Detection, LANG_FLAG, LANG_NAME, MethodInfo, fmtMs, pct } from '../api'
import { Hint } from './Hint'

export function MethodCard({ det, info, truth }: { det: Detection; info?: MethodInfo; truth?: string }) {
  const correct = truth ? det.lang === truth : undefined
  const langs = Object.keys(det.scores)
  return (
    <div className="card method-card">
      <div className="card-head" style={{ marginBottom: 4 }}>
        <h3>{info?.title ?? det.method}</h3>
        {info && <Hint text={<><b>{info.title}.</b> {info.description}<br /><br /><i>{info.metric}</i></>} />}
        <span className="spacer" />
        {correct !== undefined && <span className={'badge ' + (correct ? 'ok' : 'bad')}>{correct ? 'верно' : 'ошибка'}</span>}
      </div>
      <div className={'lang ' + det.lang}>{LANG_FLAG[det.lang]} {LANG_NAME[det.lang]}</div>
      <div className="row" style={{ gap: 6 }}>
        <small>уверенность {pct(det.confidence)}</small>
        <Hint text="Уверенность — насколько лучший язык оторвался от второго по метрике метода. Значения близко к 0 означают, что метод почти «угадывает»." />
      </div>
      <div className="bar"><span style={{ width: `${Math.max(3, det.confidence * 100)}%` }} /></div>
      <dl className="kv">
        {langs.map(l => (
          <ScoreRow key={l} method={det.method} lang={l} value={det.scores[l]} info={info} det={det} />
        ))}
        <dt>время</dt><dd className="mono">{fmtMs(det.elapsed_ms)}</dd>
      </dl>
      <Details det={det} />
    </div>
  )
}

function ScoreRow({ method, lang, value, det }: { method: string; lang: string; value: number; info?: MethodInfo; det: Detection }) {
  let v: string
  if (method === 'ngram') v = value.toLocaleString('ru-RU')
  else if (method === 'neural') v = pct(value)
  else v = value.toFixed(3)
  const label = method === 'ngram' ? 'расстояние' : method === 'neural' ? 'вероятность' : 'оценка'
  return (
    <>
      <dt>{label} → {LANG_NAME[lang]}</dt>
      <dd className="mono" style={{ fontWeight: det.lang === lang ? 600 : 400 }}>{v}</dd>
    </>
  )
}

function Details({ det }: { det: Detection }) {
  const d = det.details || {}
  if (det.method === 'ngram' && d.doc_profile) {
    return (
      <details style={{ marginTop: 10, fontSize: '.85rem' }}>
        <summary className="muted" style={{ cursor: 'pointer' }}>Профиль документа ({d.doc_profile_size} N-грамм)</summary>
        <div className="mono" style={{ marginTop: 6, wordBreak: 'break-all' }}>
          {d.doc_profile.map((g: string, i: number) => <span key={i} className="badge" style={{ margin: 2 }}>{g.replaceAll('_', '␣')}</span>)}
        </div>
        <small>Совпадений с профилем: {Object.entries(d.matched || {}).map(([l, n]) => `${LANG_NAME[l]} — ${n}`).join(', ')}</small>
      </details>
    )
  }
  if (det.method === 'alphabet' && d.shares) {
    return (
      <details style={{ marginTop: 10, fontSize: '.85rem' }}>
        <summary className="muted" style={{ cursor: 'pointer' }}>Разбор ({d.letters} букв)</summary>
        <dl className="kv">
          {Object.keys(d.shares).map(l => (
            <>
              <dt key={l + 's'}>доля {LANG_NAME[l].toLowerCase()} букв</dt><dd key={l + 'sv'} className="mono">{pct(d.shares[l])}</dd>
              <dt key={l + 'c'}>сходство частот</dt><dd key={l + 'cv'} className="mono">{d.cosine[l].toFixed(3)}</dd>
            </>
          ))}
        </dl>
      </details>
    )
  }
  return null
}
