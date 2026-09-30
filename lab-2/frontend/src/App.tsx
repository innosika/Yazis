import { useEffect, useState } from 'react'
import { Info, api } from './api'
import { DocumentPage } from './pages/DocumentPage'
import { CollectionPage } from './pages/CollectionPage'
import { VoicePage } from './pages/VoicePage'
import { CurvePage } from './pages/CurvePage'
import { HelpPage } from './pages/HelpPage'

const TABS = [
  { id: 'document', label: 'Документ', icon: '📄' },
  { id: 'collection', label: 'Коллекция', icon: '📚' },
  { id: 'voice', label: 'Голос', icon: '🎤' },
  { id: 'curve', label: 'Кривая обучения', icon: '📈' },
  { id: 'help', label: 'Справка', icon: '❔' },
] as const
type Tab = typeof TABS[number]['id']

export default function App() {
  const [tab, setTab] = useState<Tab>(() => (location.hash.slice(1) as Tab) || 'document')
  const [info, setInfo] = useState<Info | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let tries = 0
    const load = () => api.info().then(setInfo).catch(e => {
      if (tries++ < 30) setTimeout(load, 2000)
      else setError(String(e.message || e))
    })
    load()
  }, [])
  useEffect(() => { location.hash = tab }, [tab])

  return (
    <div className="app">
      <header className="topbar">
        <div className="topbar-inner">
          <div className="brand">
            <div className="logo">Аa</div>
            <div>
              <h1 style={{ fontSize: '1.05rem' }}>Распознавание языка текста</h1>
              <small>ЛР 2 · вариант 1 · русский / английский · HTML</small>
            </div>
          </div>
          <nav className="tabs" aria-label="Разделы">
            {TABS.map(t => (
              <button key={t.id} className={'tab' + (tab === t.id ? ' active' : '')} onClick={() => setTab(t.id)}>
                <span aria-hidden style={{ marginRight: 6 }}>{t.icon}</span>{t.label}
              </button>
            ))}
          </nav>
        </div>
      </header>
      <main className="main">
        {error && <div className="alert error">Не удалось связаться с сервером: {error}</div>}
        {!info && !error && (
          <div className="card row"><span className="spinner" /> Сервер запускается: загружается корпус и обучается нейросеть (обычно 10–30 секунд)…</div>
        )}
        {info && tab === 'document' && <DocumentPage info={info} />}
        {info && tab === 'collection' && <CollectionPage info={info} />}
        {info && tab === 'voice' && <VoicePage info={info} />}
        {info && tab === 'curve' && <CurvePage info={info} />}
        {info && tab === 'help' && <HelpPage info={info} />}
      </main>
      <footer className="footer">Методы: N-грамм (Cavnar–Trenkle) · алфавитный · нейросетевой (MLP). Backend: Python / FastAPI / PyTorch · Frontend: React</footer>
    </div>
  )
}
