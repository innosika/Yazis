import { useRef, useState } from 'react'
import { DetectResult, Info, api } from '../api'
import { Hint } from '../components/Hint'
import { ResultsView } from '../components/ResultsView'

const SAMPLES = {
  ru: 'Байкал — озеро тектонического происхождения в южной части Восточной Сибири, самое глубокое озеро на планете и крупнейший природный резервуар пресной воды.',
  en: 'The Grand Canyon is a steep-sided canyon carved by the Colorado River in Arizona. It is 277 miles long, up to 18 miles wide and attains a depth of over a mile.',
  mix: 'Machine learning — это раздел искусственного интеллекта. The model learns patterns from data, а затем применяет их к новым примерам.',
}

export function DocumentPage({ info }: { info: Info }) {
  const [text, setText] = useState('')
  const [result, setResult] = useState<DetectResult | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [over, setOver] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)

  const run = async () => {
    if (!text.trim()) return
    setBusy(true); setError(null)
    try { setResult(await api.detect(text)) } catch (e: any) { setError(e.message) } finally { setBusy(false) }
  }
  const runFile = async (file: File) => {
    setBusy(true); setError(null)
    try {
      const r = await api.detectFile(file)
      setResult(r); setText(r.text_preview ? `${r.text_preview}${r.text_chars > 600 ? '…' : ''}` : '')
    } catch (e: any) { setError(e.message) } finally { setBusy(false) }
  }

  return (
    <>
      <div className="card">
        <div className="card-head">
          <h2>Распознать язык документа</h2>
          <Hint text="Вставьте текст или загрузите HTML-файл (около одной страницы A4). Система очистит HTML от разметки, нормализует текст и применит три метода одновременно." />
          <span className="spacer" />
          <small>Примеры:</small>
          {(['ru', 'en', 'mix'] as const).map(k => (
            <button key={k} className="btn sm" onClick={() => { setText(SAMPLES[k]); setResult(null) }}>
              {k === 'ru' ? '🇷🇺 русский' : k === 'en' ? '🇬🇧 английский' : '🔀 смешанный'}
            </button>
          ))}
        </div>
        <textarea placeholder="Вставьте сюда текст или HTML-код…" value={text} onChange={e => setText(e.target.value)} />
        <div className="row" style={{ marginTop: 12 }}>
          <button className="btn primary" disabled={busy || !text.trim()} onClick={run}>
            {busy ? <span className="spinner" /> : '🔍'} Определить язык
          </button>
          <button className="btn" onClick={() => { setText(''); setResult(null); setError(null) }}>Очистить</button>
          <span className="spacer" style={{ flex: 1 }} />
          <small>{text.length.toLocaleString('ru-RU')} символов</small>
        </div>
        <div style={{ marginTop: 14 }}
          className={'dropzone' + (over ? ' over' : '')}
          onClick={() => fileRef.current?.click()}
          onDragOver={e => { e.preventDefault(); setOver(true) }}
          onDragLeave={() => setOver(false)}
          onDrop={e => { e.preventDefault(); setOver(false); const f = e.dataTransfer.files[0]; if (f) runFile(f) }}>
          📎 Перетащите HTML-файл сюда или нажмите, чтобы выбрать (.html, .htm, .txt)
          <input ref={fileRef} type="file" accept=".html,.htm,.txt,text/html,text/plain" hidden
            onChange={e => { const f = e.target.files?.[0]; if (f) runFile(f); e.target.value = '' }} />
        </div>
        {error && <div className="alert error" style={{ marginTop: 12 }}>{error}</div>}
      </div>

      {result && (
        <div style={{ marginTop: 16 }}>
          {result.filename && <div className="alert info" style={{ marginBottom: 12 }}>Файл <b>{result.filename}</b>: извлечено {result.text_chars.toLocaleString('ru-RU')} символов текста.</div>}
          <ResultsView result={result} methods={info.methods} />
        </div>
      )}
    </>
  )
}
