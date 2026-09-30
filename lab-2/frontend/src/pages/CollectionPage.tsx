import { useEffect, useRef, useState } from 'react'
import { CollectionDoc, Evaluation, Info, LANG_FLAG, LANG_NAME, Lang, METHOD_ORDER, fmtMs, pct } from '../api'
import { api } from '../api'
import { Hint } from '../components/Hint'

function HardBadge({ note }: { note: string }) {
  return (
    <span className="row" style={{ gap: 4, display: 'inline-flex' }}>
      <span className="badge warn">сложный</span>
      <Hint text={<><b>Чем сложен:</b> {note}</>} />
    </span>
  )
}

export function CollectionPage({ info }: { info: Info }) {
  const [docs, setDocs] = useState<CollectionDoc[]>([])
  const [ev, setEv] = useState<Evaluation | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [upLang, setUpLang] = useState<Lang>('ru')
  const fileRef = useRef<HTMLInputElement>(null)

  const reload = () => api.collection().then(r => setDocs(r.documents)).catch(e => setError(e.message))
  useEffect(() => { reload() }, [])

  const run = async () => {
    setBusy(true); setError(null)
    try { setEv(await api.evaluate()) } catch (e: any) { setError(e.message) } finally { setBusy(false) }
  }
  const upload = async (file: File) => {
    setError(null)
    try { await api.upload(file, upLang); await reload(); setEv(null) } catch (e: any) { setError(e.message) }
  }
  const remove = async (id: string) => {
    if (!confirm('Удалить загруженный документ из коллекции?')) return
    try { await api.remove(id); await reload(); setEv(null) } catch (e: any) { setError(e.message) }
  }
  const methods = METHOD_ORDER.filter(m => info.methods.some(x => x.id === m))
  const titleOf = (m: string) => info.methods.find(x => x.id === m)?.title ?? m

  return (
    <>
      <div className="card no-print">
        <div className="card-head">
          <h2>Тестовая коллекция</h2>
          <Hint text="Коллекция — набор HTML-документов объёмом около одной страницы A4 с заранее известным языком (статьи Wikipedia). Нажмите «Прогнать коллекцию», чтобы получить сводную статистику по точности и времени каждого метода. Можно добавить собственные HTML-файлы." />
          <span className="badge">{docs.filter(d => d.group !== 'hard').length} обычных</span>
          <span className="badge warn">{docs.filter(d => d.group === 'hard').length} сложных</span>
          <Hint text="Обычные документы — статьи Wikipedia объёмом в страницу A4. Сложные — специально подобранные случаи, на которых методы ошибаются: транслит, гомоглифы, смешанные тексты, код с русскими комментариями, дореформенная орфография, сленг. Каждый сложный документ снабжён пояснением (значок «?» рядом с ним)." />
          <span className="spacer" />
          <select value={upLang} onChange={e => setUpLang(e.target.value as Lang)} title="Истинный язык загружаемого файла">
            <option value="ru">🇷🇺 Русский</option><option value="en">🇬🇧 Английский</option>
          </select>
          <button className="btn" onClick={() => fileRef.current?.click()}>＋ Добавить HTML</button>
          <input ref={fileRef} type="file" accept=".html,.htm,text/html" hidden multiple
            onChange={async e => { for (const f of Array.from(e.target.files ?? [])) await upload(f); e.target.value = '' }} />
          <button className="btn primary" disabled={busy || docs.length === 0} onClick={run}>
            {busy ? <span className="spinner" /> : '▶'} Прогнать коллекцию
          </button>
        </div>
        {error && <div className="alert error">{error}</div>}
        {!ev && (
          <div className="tbl-wrap">
            <table className="tbl">
              <thead><tr><th>ID</th><th>Документ</th><th>Истинный язык</th><th className="num">Символов</th><th>Источник</th><th /></tr></thead>
              <tbody>
                {docs.map(d => (
                  <tr key={d.id}>
                    <td className="mono">{d.id}</td>
                    <td><a href={d.url} target="_blank" rel="noreferrer" title="Открыть документ">{d.title} ↗</a> {d.group === 'hard' && <HardBadge note={d.note} />}</td>
                    <td><span className={'badge ' + d.lang}>{LANG_FLAG[d.lang]} {LANG_NAME[d.lang]}</span></td>
                    <td className="num">{d.chars.toLocaleString('ru-RU')}</td>
                    <td>{d.source.startsWith('http') ? <a href={d.source} target="_blank" rel="noreferrer">Wikipedia</a> : <span className="badge">{d.source === 'synthetic' ? 'синтетический' : 'загружен'}</span>}</td>
                    <td>{d.origin === 'upload' && <button className="btn sm danger" onClick={() => remove(d.id)}>удалить</button>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {ev && (
        <>
          <div className="card" style={{ marginTop: 16 }}>
            <div className="card-head">
              <h2>Сводная статистика</h2>
              <Hint text="Точность — доля документов, язык которых определён верно. Время — среднее время распознавания одного документа (без учёта извлечения текста из HTML)." />
              <span className="spacer" />
              <small className="no-print">полный прогон {fmtMs(ev.total_elapsed_ms)}</small>
              <a className="btn sm no-print" href="/api/collection/report?format=json" download>⬇ JSON</a>
              <a className="btn sm no-print" href="/api/collection/report?format=csv" download>⬇ CSV</a>
              <a className="btn sm no-print" href="/api/collection/report?format=html" target="_blank" rel="noreferrer">📄 Отчёт</a>
              <button className="btn sm no-print" onClick={() => window.print()}>🖨 Печать</button>
            </div>
            <div className="grid grid-3">
              {methods.map(m => {
                const s = ev.summary[m]
                return (
                  <div className="stat" key={m}>
                    <div className="l">{s.title}</div>
                    <div className="v" style={{ color: s.accuracy === 1 ? 'var(--ok)' : s.accuracy < 0.9 ? 'var(--bad)' : undefined }}>{pct(s.accuracy)}</div>
                    <div className="l">{s.correct} из {s.total} верно · {fmtMs(s.avg_time_ms)} / документ</div>
                    {s.groups?.hard && (
                      <div className="row" style={{ gap: 6, marginTop: 8, fontSize: '.8rem' }}>
                        <span className="badge ok">обычные {pct(s.groups.standard?.accuracy ?? 0)}</span>
                        <span className={'badge ' + (s.groups.hard.accuracy < 0.8 ? 'bad' : 'warn')}>сложные {pct(s.groups.hard.accuracy)} ({s.groups.hard.correct}/{s.groups.hard.total})</span>
                      </div>
                    )}
                    <Confusion s={s} langs={ev.languages} />
                  </div>
                )
              })}
            </div>
          </div>

          <div className="card" style={{ marginTop: 16 }}>
            <div className="card-head">
              <h2>Результаты по документам</h2>
              <Hint text="Ссылка в столбце «Документ» открывает исходный HTML. Ячейки методов подсвечены зелёным при верном ответе и красным при ошибке; под языком — время распознавания." />
              <span className="spacer" />
              <button className="btn sm no-print" onClick={() => setEv(null)}>← к списку</button>
            </div>
            <div className="tbl-wrap">
              <table className="tbl">
                <thead>
                  <tr><th>ID</th><th>Документ</th><th>Истинный</th><th className="num">Симв.</th>{methods.map(m => <th key={m}>{titleOf(m)}</th>)}</tr>
                </thead>
                <tbody>
                  {ev.documents.map(r => (
                    <tr key={r.id}>
                      <td className="mono">{r.id}</td>
                      <td><a href={r.url} target="_blank" rel="noreferrer">{r.title} ↗</a> {r.group === 'hard' && <HardBadge note={r.note} />}</td>
                      <td><span className={'badge ' + r.true_lang}>{LANG_FLAG[r.true_lang]} {LANG_NAME[r.true_lang]}</span></td>
                      <td className="num">{r.chars.toLocaleString('ru-RU')}</td>
                      {methods.map(m => {
                        const p = r.predictions[m]
                        return (
                          <td key={m} className={p.correct ? 'ok' : 'bad'}>
                            {LANG_FLAG[p.lang]} {LANG_NAME[p.lang]}
                            <br /><small className="mono">{fmtMs(p.elapsed_ms)} · {pct(p.confidence)}</small>
                          </td>
                        )
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </>
  )
}

function Confusion({ s, langs }: { s: Evaluation['summary'][string]; langs: Lang[] }) {
  return (
    <table className="tbl" style={{ marginTop: 10, fontSize: '.8rem' }}>
      <thead><tr><th style={{ padding: 4 }}>истина ↓ / ответ →</th>{langs.map(l => <th key={l} style={{ padding: 4 }}>{LANG_FLAG[l]}</th>)}</tr></thead>
      <tbody>
        {langs.map(t => (
          <tr key={t}><td style={{ padding: 4 }}>{LANG_FLAG[t]} {LANG_NAME[t]}</td>
            {langs.map(p => <td key={p} className={'num ' + (t === p ? '' : s.confusion[t][p] ? 'bad' : '')} style={{ padding: 4 }}>{s.confusion[t][p]}</td>)}
          </tr>
        ))}
      </tbody>
    </table>
  )
}
