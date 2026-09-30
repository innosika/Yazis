import { useEffect, useRef, useState } from 'react'
import { DetectResult, Info, LANG_NAME, api } from '../api'
import { Hint } from '../components/Hint'
import { ResultsView } from '../components/ResultsView'

const WHISPER_LANG: Record<string, string> = { russian: 'русский', english: 'английский', ru: 'русский', en: 'английский' }

export function VoicePage({ info }: { info: Info }) {
  const [recording, setRecording] = useState(false)
  const [busy, setBusy] = useState(false)
  const [seconds, setSeconds] = useState(0)
  const [result, setResult] = useState<DetectResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const recRef = useRef<MediaRecorder | null>(null)
  const chunks = useRef<Blob[]>([])
  const timer = useRef<number | null>(null)
  const supported = typeof navigator !== 'undefined' && !!navigator.mediaDevices?.getUserMedia && typeof MediaRecorder !== 'undefined'

  useEffect(() => () => { if (timer.current) clearInterval(timer.current) }, [])

  const start = async () => {
    setError(null); setResult(null)
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const mime = ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus', 'audio/mp4'].find(m => MediaRecorder.isTypeSupported(m)) || ''
      const rec = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined)
      chunks.current = []
      rec.ondataavailable = e => { if (e.data.size) chunks.current.push(e.data) }
      rec.onstop = async () => {
        stream.getTracks().forEach(t => t.stop())
        const type = rec.mimeType || 'audio/webm'
        const blob = new Blob(chunks.current, { type })
        const ext = type.includes('ogg') ? 'ogg' : type.includes('mp4') ? 'mp4' : 'webm'
        setBusy(true)
        try { setResult(await api.voice(blob, `speech.${ext}`)) } catch (e: any) { setError(e.message) } finally { setBusy(false) }
      }
      rec.start()
      recRef.current = rec
      setRecording(true); setSeconds(0)
      timer.current = window.setInterval(() => setSeconds(s => s + 1), 1000)
    } catch (e: any) {
      setError('Нет доступа к микрофону: ' + (e.message || e) + '. Разрешите доступ в браузере (нужен https или localhost).')
    }
  }
  const stop = () => {
    recRef.current?.stop(); setRecording(false)
    if (timer.current) { clearInterval(timer.current); timer.current = null }
  }
  const onFile = async (f: File) => {
    setError(null); setResult(null); setBusy(true)
    try { setResult(await api.voice(f, f.name)) } catch (e: any) { setError(e.message) } finally { setBusy(false) }
  }

  return (
    <>
      <div className="card">
        <div className="card-head">
          <h2>Голосовая диктовка</h2>
          <Hint text="Нажмите кнопку записи и произнесите несколько фраз на русском или английском. Аудио отправляется в Groq Whisper (whisper-large-v3) для перевода речи в текст — язык при этом НЕ указывается. Затем полученный текст распознаётся тремя методами лабораторной работы, а ответ Whisper показывается для сравнения." />
        </div>
        {!info.voice_available && <div className="alert warn" style={{ marginBottom: 12 }}>Ключ GROQ_API_KEY не задан — диктовка недоступна. Добавьте ключ в файл <code>.env</code> и выполните <code>make restart</code>.</div>}
        {!supported && <div className="alert warn" style={{ marginBottom: 12 }}>Браузер не поддерживает запись звука. Можно загрузить готовый аудиофайл ниже.</div>}
        <div className="row" style={{ gap: 16 }}>
          {!recording ? (
            <button className="btn record" disabled={!info.voice_available || !supported || busy} onClick={start}>🎙 Начать запись</button>
          ) : (
            <button className="btn record on" onClick={stop}>■ Остановить ({seconds} с)</button>
          )}
          {recording && <div className="wave" aria-label="идёт запись"><span /><span /><span /><span /><span /></div>}
          {busy && <span className="row"><span className="spinner" /> Распознаём речь и язык…</span>}
          <span className="spacer" style={{ flex: 1 }} />
          <label className="btn" style={{ cursor: 'pointer' }}>
            📁 Загрузить аудио
            <input type="file" accept="audio/*,.webm,.mp3,.wav,.m4a,.ogg" hidden disabled={!info.voice_available}
              onChange={e => { const f = e.target.files?.[0]; if (f) onFile(f); e.target.value = '' }} />
          </label>
        </div>
        <p className="muted" style={{ marginTop: 12, fontSize: '.85rem' }}>
          Совет: для чистого эксперимента продиктуйте 1–2 предложения. Чем короче фраза, тем сложнее методам — это хорошо видно на вкладке «Кривая обучения».
        </p>
        {error && <div className="alert error" style={{ marginTop: 12 }}>{error}</div>}
      </div>

      {result && (
        <div style={{ marginTop: 16, display: 'grid', gap: 16 }}>
          <div className="card">
            <div className="card-head">
              <h3>Распознанный текст</h3>
              <span className="spacer" />
              {result.whisper_language && (
                <span className="badge" title="Язык, который определил Whisper при транскрипции">
                  Whisper: {WHISPER_LANG[result.whisper_language.toLowerCase()] ?? result.whisper_language}
                  {result.consensus && (WHISPER_LANG[result.whisper_language.toLowerCase()] === LANG_NAME[result.consensus].toLowerCase() ? ' ✓ совпадает' : ' ≠ наш ответ')}
                </span>
              )}
              {result.duration != null && <small>{result.duration.toFixed(1)} с</small>}
            </div>
            <div className="preview">{result.transcript}</div>
          </div>
          <ResultsView result={result} methods={info.methods} />
        </div>
      )}
    </>
  )
}
