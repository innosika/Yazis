import { Info, LANG_NAME, fmtMs } from '../api'

export function HelpPage({ info }: { info: Info }) {
  return (
    <div className="grid grid-2" style={{ alignItems: 'start' }}>
      <div className="card prose">
        <h2>Как пользоваться</h2>
        <ol className="steps">
          <li><b>Документ.</b> Вставьте текст или перетащите HTML-файл — получите ответ трёх методов, их уверенность и время работы. Кнопки «примеры» подставляют готовые фрагменты.</li>
          <li><b>Коллекция.</b> Нажмите «Прогнать коллекцию»: система определит язык каждого тестового документа и покажет точность, среднее время и матрицу ошибок по каждому методу. Ссылки открывают исходные документы. Результат можно сохранить в JSON/CSV, открыть как отчёт или распечатать.</li>
          <li><b>Голос.</b> Продиктуйте фразу — речь превратится в текст (Whisper), а язык определят наши методы.</li>
          <li><b>Кривая обучения.</b> Показывает, как точность методов зависит от длины текста.</li>
        </ol>
        <p>Значок <span className="hint" style={{ verticalAlign: 'middle' }}><button type="button" tabIndex={-1}>?</button></span> рядом с элементами интерфейса открывает подсказку при наведении.</p>

        <h3>Как работает система</h3>
        <ol>
          <li><b>Предобработка.</b> Из HTML удаляются теги, скрипты и стили; текст переводится в нижний регистр, удаляются цифры и пунктуация.</li>
          <li><b>Профили.</b> По тренировочному корпусу для каждого языка построен поисковый образ языка (ПОЯ): профиль N-грамм, распределение букв и обученная нейросеть.</li>
          <li><b>Сравнение.</b> Для входного документа строится его образ и сравнивается с ПОЯ каждого языка по метрике метода.</li>
          <li><b>Решение.</b> Язык с наилучшей метрикой принимается за ответ; итог — голосование трёх методов.</li>
        </ol>

        <h3>Частые вопросы</h3>
        <p><b>Почему методы расходятся на коротком тексте?</b> При 1–3 словах профиль документа почти пуст. Алфавитный метод обычно устойчивее всех: ему достаточно нескольких букв. N-грамм и нейросеть требуют больше контекста.</p>
        <p><b>Что означает «уверенность»?</b> Нормированный отрыв лучшего языка от второго по метрике метода. Не является вероятностью в строгом смысле (кроме нейросети, где это разность softmax).</p>
        <p><b>Можно ли добавить свои документы?</b> Да — на вкладке «Коллекция» выберите истинный язык и загрузите HTML-файлы. Они сохраняются в папке <code>data/uploads</code>.</p>
      </div>

      <div style={{ display: 'grid', gap: 16 }}>
        <div className="card prose">
          <h2>Методы</h2>
          {info.methods.map(m => (
            <div key={m.id} style={{ marginTop: 12 }}>
              <h3>{m.title}</h3>
              <p>{m.description}</p>
              <small><i>{m.metric}</i> · обучение {fmtMs(info.fit_times_ms[m.id] ?? 0)}</small>
            </div>
          ))}
        </div>
        <div className="card prose">
          <h2>Тренировочный корпус</h2>
          <table className="tbl">
            <thead><tr><th>Язык</th><th className="num">Файлов</th><th className="num">Размер</th><th className="num">Слов</th></tr></thead>
            <tbody>
              {(Object.keys(info.corpus) as (keyof typeof info.corpus)[]).map(l => (
                <tr key={l}><td>{LANG_NAME[l]}</td><td className="num">{info.corpus[l].files}</td><td className="num">{(info.corpus[l].bytes / 1024).toFixed(1)} КБ</td><td className="num">{info.corpus[l].words.toLocaleString('ru-RU')}</td></tr>
              ))}
            </tbody>
          </table>
          <p><small>Статьи Wikipedia: {Object.values(info.corpus).flatMap(c => c.titles).join(', ')}.</small></p>
          <h3>Нейросеть</h3>
          <p><small>Обучающих фрагментов: {info.neural.samples} · эпох: {info.neural.epochs} · признаков: {info.neural.features} · скрытый слой: {info.neural.hidden} · точность на валидации: {((info.neural.val_accuracy ?? 0) * 100).toFixed(1)}%</small></p>
        </div>
      </div>
    </div>
  )
}
