/** Per-screen guidance and the glossary for the Help page and the contextual tips, in both languages. */
import { getLang } from "@/lib/i18n";

export interface ScreenGuide {
  id: string;
  title: string;
  to: string;
  purpose: string;
  controls: string[];
  reading: string[];
}

const SCREEN_GUIDES_EN: ScreenGuide[] = [
  {
    id: "help-search",
    title: "Search",
    to: "/search",
    purpose: "Ask a question in plain English and get the documents ranked by the vector model (or by a strategy it is compared with).",
    controls: [
      "Ranker — the document-selection strategy. The starred Vector model is the one variant 34 mandates.",
      "All words together — the assignment's allWordsTogether: only documents containing every query word.",
      "from / to — the assignment's date range (dateStartString / dateEndString) on the document's publication date.",
      "Press / anywhere to focus the search field.",
    ],
    reading: [
      "Each result carries an active link to the document and the list of your query words found in it (struck-through words are absent).",
      "The score is the cosine r(D, Q); the highlighted snippet is the passage densest in your words.",
      "«Why this score?» opens the glass box: every number behind the score, recomputed from the raw counts.",
    ],
  },
  {
    id: "help-corpus",
    title: "Corpus",
    to: "/corpus",
    purpose: "Browse the indexed collection, its statistics and each document's automatically extracted keywords.",
    controls: [
      "Add document — fetch and index one page by URL through the crawl pipeline (the Document class's AddDocumentToBase).",
      "Rebuild index — re-analyse every document and recompute all weights; needed whenever N changes.",
      "Delete — remove a document (DeleteDocumentFromBase); by default the weights are recomputed immediately.",
    ],
    reading: [
      "N (documents) and D (dictionary size) are the N and the dimensionality of every vector in the system.",
      "‖D‖ is 1.000 for every document because w_dk is L2-normalised — which is why the cosine reduces to a sum of weights.",
      "Keywords are ranked by formula 1.6 (A = N_dk · B_k); the rank column shows how differently the normalised weight orders them.",
    ],
  },
  {
    id: "help-crawl",
    title: "Crawl",
    to: "/crawl",
    purpose: "Acquire documents from the web (variant 34: «Сеть Интернет»).",
    controls: [
      "Seeds, max pages, max depth and the same-domain switch bound the crawl.",
      "Jobs run in the worker process; the page keeps polling and streams events live.",
    ],
    reading: [
      "Skipped pages carry a reason: robots.txt, exact or near duplicate (SimHash), too short after boilerplate removal, HTTP error.",
      "The frontier lists every URL with its decision and per-stage timings (fetch, extract, index).",
      "The log console at the bottom is the crawler's own structured log, streamed from the server.",
    ],
  },
  {
    id: "help-evaluation",
    title: "Evaluation",
    to: "/evaluation",
    purpose: "The required submenu: ROMIP 2004 quality metrics computed programmatically over stored runs, shown as tables and graphs.",
    controls: [
      "Collection — the automatic known-item set or the hand-authored topical set.",
      "Relevance table — «or» / «and» aggregation of assessor grades at threshold relevant−; num_q is the number of topics that keep a relevant document.",
      "Run all rankers — retrieve the top 100 for every judged topic with every ranker, in the background.",
    ],
    reading: [
      "Overview: aggregate table (num_q first, best per column in bold, † / ‡ significance against the baseline) and grouped bars with bootstrap intervals.",
      "Per topic: metrics per topic sorted by ascending AP, expandable top 10 with judged grades, and a diverging bar chart against the baseline.",
      "Curves: the 11-point interpolated PR curve (TREC method) with the optional non-zeroing reconstruction, the raw sawtooth, P@k and the grade distribution.",
      "Comparison aligns runs on the intersection of topics; Significance runs paired tests with Holm–Bonferroni correction.",
    ],
  },
  {
    id: "help-lab",
    title: "Relevance Lab",
    to: "/lab",
    purpose: "See the vector space and correct a query by relevance feedback — the «процедуры поиска и коррекции запросов» the theory names.",
    controls: [
      "Project — parse the query and draw it as a ray; documents are coloured by their cosine with it.",
      "Mark + / − on results (or click a point), then Apply Rocchio with your α, β, γ.",
      "Replay — step through the query's trajectory across rounds.",
    ],
    reading: [
      "The 3-D picture is a truncated SVD of the term–document matrix (formula 1.7): it keeps only the stated fraction of the variance, so hover shows both the angle in the picture and the true cosine.",
      "After a round the list re-sorts in place; ↑/↓ show how far each document moved.",
    ],
  },
];

export interface GlossaryEntry {
  id: string;
  term: string;
  definition: string;
}

const GLOSSARY_EN: GlossaryEntry[] = [
  { id: "glossary-pod", term: "Search image of a document (ПОД)", definition: "The document as the system sees it: its lemmatised terms with weights. Built once at indexing time." },
  { id: "glossary-poz", term: "Search image of a query (ПОЗ)", definition: "The query after the same linguistic pipeline. The assignment specifies a binary vector: every query word weighs 1." },
  { id: "glossary-idf", term: "Inverse document frequency B_i", definition: "log(N / P_i): rarer terms weigh more. A term in every document has B_i = 0 and never affects a score." },
  { id: "glossary-norm", term: "Euclidean norm ‖D‖", definition: "Length of the document vector. The normalised weight w_dk divides by it, so every stored document has ‖D‖ = 1." },
  { id: "glossary-cosine", term: "Cosine similarity r(D, Q)", definition: "(D, Q) / (‖D‖·‖Q‖): the cosine of the angle between the two vectors, 1 for identical directions, 0 for orthogonal." },
  { id: "glossary-inverted-index", term: "Inverted index", definition: "For each term, the list of documents containing it with the counts and positions — what lets the cosine be computed by scanning only the query's terms." },
  { id: "glossary-qrels", term: "Relevance table (qrels)", definition: "The judged (topic, document) pairs turned into binary relevance at a threshold. ROMIP publishes two: «or» (any assessor said relevant) and «and» (every assessor did)." },
  { id: "glossary-pool", term: "Pool", definition: "The set of pairs that get judged: the union of every ranker's top-k, plus an oracle query and a random sample so the pool is not confined to what our own systems retrieved." },
  { id: "glossary-map", term: "Average precision, MAP", definition: "Mean of the precision at each relevant document, divided by the number of relevant documents in the judgments; averaged over topics it is MAP, the primary metric." },
  { id: "glossary-11pt", term: "11-point interpolated curve", definition: "Precision interpolated at recall 0.0, 0.1, …, 1.0 and averaged over topics; a topic that never reaches a level contributes 0 there (the TREC convention)." },
  { id: "glossary-intersection", term: "Topic intersection", definition: "Comparisons of means are only valid over the same topics, so the Comparison tab recomputes every mean on the topics all selected runs scored." },
  { id: "glossary-holm", term: "Holm–Bonferroni", definition: "A correction for testing many pairs at once: seven rankers make 21 comparisons, and without it one false 'significant' result is likely." },
  { id: "glossary-rocchio", term: "Rocchio feedback", definition: "q' = α·q + β·mean(relevant) − γ·mean(non-relevant): the query moves towards what the user liked. Pseudo-relevance feedback assumes the top results are relevant." },
  { id: "glossary-lsa", term: "Latent semantic analysis", definition: "Truncated SVD of the term–document matrix; the first three components give the coordinates drawn in the Relevance Lab." },
  { id: "glossary-known-item", term: "Known-item collection", definition: "Topics derived automatically from a document's opening text; that document is the one relevant answer. Exact but degenerate: recall and bpref collapse to 'was it found'." },
  { id: "glossary-llm-assessor", term: "LLM assessor", definition: "A local language model that grades pool pairs on ROMIP's five-point scale, seeing only the topic and the document. Recorded with model, digest and prompt version; agreement with humans is not measured in this lab." },
];

const THIRD_PARTY_EN: Array<{ name: string; role: string }> = [
  { name: "Python 3.12 · FastAPI · Uvicorn", role: "HTTP API and server-sent events" },
  { name: "PostgreSQL 17 + pgvector", role: "documents, inverted index, judgments, runs; dense vectors for the semantic ranker" },
  { name: "SQLAlchemy 2 (async) · asyncpg · Alembic", role: "data access and migrations" },
  { name: "Redis 7 · TaskIQ", role: "task queue (Redis Streams) for crawls, judging and evaluation runs; pub/sub for live progress" },
  { name: "spaCy (en_core_web_sm)", role: "tokenisation, lemmatisation and part-of-speech filtering for documents and queries" },
  { name: "httpx · trafilatura · selectolax · protego", role: "fetching, boilerplate removal and robots.txt for the crawler" },
  { name: "NumPy · SciPy", role: "sparse term–document matrix and truncated SVD; statistical tests" },
  { name: "FastEmbed (BAAI/bge-small-en-v1.5)", role: "sentence embeddings for the semantic baseline" },
  { name: "Ollama (qwen2.5:3b-instruct)", role: "local LLM assessor for the topical pool" },
  { name: "pytrec_eval (NIST trec_eval)", role: "reference implementation the metric core is cross-validated against" },
  { name: "React 19 · TypeScript · Vite · TanStack Router & Query", role: "the interface" },
  { name: "Tailwind CSS v4 · Motion", role: "design tokens and animation" },
  { name: "Recharts · react-three-fiber · three.js · KaTeX", role: "charts, the 3-D vector space, formula typesetting" },
  { name: "Docker Compose", role: "one-command deployment of every service" },
];

const SCREEN_GUIDES_RU: ScreenGuide[] = [
  {
    id: "help-search",
    title: "Поиск",
    to: "/search",
    purpose: "Задайте вопрос на естественном языке (корпус английский) и получите документы, упорядоченные векторной моделью или одной из стратегий, с которыми она сравнивается.",
    controls: [
      "Стратегия отбора — способ выбора и упорядочения документов. Векторная модель со звёздочкой — та, что требует вариант 34.",
      "Все слова вместе — параметр allWordsTogether из задания: только документы, содержащие каждое слово запроса.",
      "с / по — диапазон дат (dateStartString / dateEndString) по дате публикации документа.",
      "Клавиша / в любом месте страницы переводит курсор в поле запроса.",
    ],
    reading: [
      "Каждый результат содержит активную ссылку на документ и список слов запроса, найденных в нём (зачёркнутые слова отсутствуют).",
      "Ранг — косинус r(D, Q); подсвеченный фрагмент — участок текста, наиболее плотный по словам запроса.",
      "«Почему такой ранг?» открывает «стеклянный ящик»: все числа, стоящие за рангом, пересчитанные из исходных счётчиков.",
    ],
  },
  {
    id: "help-corpus",
    title: "Корпус",
    to: "/corpus",
    purpose: "Просмотр проиндексированной коллекции, её статистики и автоматически выделенных ключевых слов каждого документа.",
    controls: [
      "Добавить документ — загрузить и проиндексировать одну страницу по URL через конвейер обхода (метод AddDocumentToBase класса Document).",
      "Перестроить индекс — заново разобрать все документы и пересчитать веса; необходимо при любом изменении N.",
      "Удалить — убрать документ (DeleteDocumentFromBase); по умолчанию веса пересчитываются сразу.",
    ],
    reading: [
      "N (документов) и D (размер словаря) — те самые N и размерность каждого вектора в системе.",
      "‖D‖ равна 1,000 у каждого документа, потому что w_dk нормированы (L2) — поэтому косинус сводится к сумме весов.",
      "Ключевые слова упорядочены по формуле 1.6 (A = N_dk · B_k); столбец с рангом показывает, насколько иначе их упорядочивает нормированный вес.",
    ],
  },
  {
    id: "help-crawl",
    title: "Обход",
    to: "/crawl",
    purpose: "Сбор документов из сети Интернет (сфера применения по варианту 34).",
    controls: [
      "Стартовые URL, число страниц, глубина и ограничение доменом задают границы обхода.",
      "Задания выполняются в фоновом обработчике; страница опрашивает статус и показывает события в реальном времени.",
    ],
    reading: [
      "У каждой пропущенной страницы указана причина: robots.txt, точный или почти-дубликат (SimHash), слишком короткий текст после очистки, ошибка HTTP.",
      "Фронтир перечисляет все URL с решением по каждому и временем этапов (загрузка, извлечение, индексирование).",
      "Журнал внизу — структурированный лог обходчика, передаваемый с сервера.",
    ],
  },
  {
    id: "help-evaluation",
    title: "Оценка качества",
    to: "/evaluation",
    purpose: "Требуемое заданием подменю: метрики РОМИП-2004, вычисленные программно по сохранённым прогонам и показанные таблицами и графиками.",
    controls: [
      "Коллекция — автоматическая коллекция известных документов или тематическая, составленная вручную.",
      "Таблица релевантности — агрегация оценок асессоров «or» / «and» при пороге «возможно соответствующий»; num_q — число тем, у которых остался хотя бы один релевантный документ.",
      "Прогнать все стратегии — найти первые 100 документов по каждой оценённой теме каждой стратегией, в фоне.",
    ],
    reading: [
      "Сводка: таблица агрегатов (сначала num_q, лучшее в столбце жирным, † / ‡ — значимость относительно базовой) и столбики с бутстреп-интервалами.",
      "По темам: метрики по каждой теме, упорядоченные по возрастанию AP, раскрываемый топ-10 с оценками и диаграмма разностей с базовой стратегией.",
      "Кривые: 11-точечная интерполированная кривая (методика TREC) с реконструкцией без обнуления, сырая «пила», P@k и распределение оценок.",
      "Сравнение выравнивает прогоны на пересечении тем; Значимость — парные критерии с поправкой Холма–Бонферрони.",
    ],
  },
  {
    id: "help-lab",
    title: "Лаборатория релевантности",
    to: "/lab",
    purpose: "Увидеть векторное пространство и скорректировать запрос по обратной связи — «процедуры поиска и коррекции запросов», названные в теоретической части задания.",
    controls: [
      "Спроецировать — разобрать запрос и нарисовать его лучом; документы окрашены по косинусу с ним.",
      "Отметьте + / − у результатов (или щёлкните по точке), затем «Применить Роккио» со своими α, β, γ.",
      "Повтор — пошаговый просмотр траектории запроса по раундам.",
    ],
    reading: [
      "Трёхмерная картинка — усечённое SVD матрицы «термин–документ» (формула 1.7): она сохраняет лишь указанную долю дисперсии, поэтому при наведении показаны и угол на картинке, и истинный косинус.",
      "После раунда список пересортировывается на месте; ↑/↓ показывают, насколько сдвинулся каждый документ.",
    ],
  },
];

const GLOSSARY_RU: GlossaryEntry[] = [
  { id: "glossary-pod", term: "Поисковый образ документа (ПОД)", definition: "Документ, каким его видит система: леммы с весами. Строится один раз при индексировании." },
  { id: "glossary-poz", term: "Поисковый образ запроса (ПОЗ)", definition: "Запрос после того же лингвистического конвейера. По заданию — бинарный вектор: каждое слово запроса весит 1." },
  { id: "glossary-idf", term: "Инверсная частота B_i", definition: "log(N / P_i): чем реже термин, тем больше вес. Термин, встречающийся во всех документах, имеет B_i = 0 и ни на что не влияет." },
  { id: "glossary-norm", term: "Евклидова норма ‖D‖", definition: "Длина вектора документа. Нормированный вес w_dk делится на неё, поэтому у каждого хранимого документа ‖D‖ = 1." },
  { id: "glossary-cosine", term: "Косинусная мера r(D, Q)", definition: "(D, Q) / (‖D‖·‖Q‖): косинус угла между векторами — 1 при совпадении направлений, 0 при ортогональности." },
  { id: "glossary-inverted-index", term: "Инвертированный индекс", definition: "Для каждого термина — список документов, где он встречается, с частотами и позициями. Благодаря ему косинус считается просмотром только терминов запроса." },
  { id: "glossary-qrels", term: "Таблица релевантности (qrels)", definition: "Оценённые пары (тема, документ), сведённые к бинарной релевантности при пороге. РОМИП публикует две: «or» (релевантен по мнению любого асессора) и «and» (по мнению всех)." },
  { id: "glossary-pool", term: "Пул", definition: "Множество пар, которые оцениваются: объединение top-k всех стратегий плюс оракульный запрос и случайная выборка, чтобы пул не ограничивался тем, что нашли наши системы." },
  { id: "glossary-map", term: "Средняя точность, MAP", definition: "Среднее точностей на позициях релевантных документов, делённое на число релевантных документов; усреднённое по темам — MAP, главная метрика." },
  { id: "glossary-11pt", term: "11-точечная интерполированная кривая", definition: "Точность, интерполированная на уровнях полноты 0,0; 0,1; …; 1,0 и усреднённая по темам; тема, не достигшая уровня, даёт там 0 (соглашение TREC)." },
  { id: "glossary-intersection", term: "Пересечение тем", definition: "Сравнивать средние можно только по одним и тем же темам, поэтому раздел «Сравнение» пересчитывает средние на темах, оценённых всеми выбранными прогонами." },
  { id: "glossary-holm", term: "Поправка Холма–Бонферрони", definition: "Поправка на множественные сравнения: семь стратегий дают 21 пару, и без неё хотя бы один ложно «значимый» результат почти неизбежен." },
  { id: "glossary-rocchio", term: "Обратная связь Роккио", definition: "q′ = α·q + β·centroid(релевантных) − γ·centroid(нерелевантных): запрос сдвигается к тому, что пользователь отметил. Псевдо-обратная связь считает релевантными верхние результаты." },
  { id: "glossary-lsa", term: "Латентно-семантический анализ (LSA)", definition: "Усечённое сингулярное разложение матрицы «термин–документ»; первые три компоненты дают координаты, которые рисует лаборатория." },
  { id: "glossary-known-item", term: "Коллекция известных документов", definition: "Темы получены автоматически из начала текста документа; этот документ — единственный релевантный ответ. Точно, но вырожденно: полнота и bpref сводятся к признаку «найден ли документ»." },
  { id: "glossary-llm-assessor", term: "LLM-асессор", definition: "Локальная языковая модель, оценивающая пары пула по пятибалльной шкале РОМИП и видящая только тему и документ. Записываются модель, хеш и версия промпта; согласованность с людьми в этой работе не измерена." },
];

const THIRD_PARTY_RU: Array<{ name: string; role: string }> = [
  { name: "Python 3.12 · FastAPI · Uvicorn", role: "HTTP-API и потоки событий (SSE)" },
  { name: "PostgreSQL 17 + pgvector", role: "документы, инвертированный индекс, оценки, прогоны; плотные векторы для семантической стратегии" },
  { name: "SQLAlchemy 2 (async) · asyncpg · Alembic", role: "доступ к данным и миграции" },
  { name: "Redis 7 · TaskIQ", role: "очередь задач (Redis Streams) для обхода, оценивания и прогонов; pub/sub для прогресса" },
  { name: "spaCy (en_core_web_sm)", role: "токенизация, лемматизация и фильтр по частям речи для документов и запросов" },
  { name: "httpx · trafilatura · selectolax · protego", role: "загрузка страниц, удаление шаблонных элементов и robots.txt для обходчика" },
  { name: "NumPy · SciPy", role: "разреженная матрица «термин–документ» и усечённое SVD; статистические критерии" },
  { name: "FastEmbed (BAAI/bge-small-en-v1.5)", role: "векторы предложений для семантической базовой стратегии" },
  { name: "Ollama (qwen2.5:3b-instruct)", role: "локальный LLM-асессор для тематического пула" },
  { name: "pytrec_eval (NIST trec_eval)", role: "эталонная реализация, с которой сверено ядро метрик" },
  { name: "React 19 · TypeScript · Vite · TanStack Router & Query", role: "интерфейс" },
  { name: "Tailwind CSS v4 · Motion", role: "дизайн-токены и анимация" },
  { name: "Recharts · react-three-fiber · three.js · KaTeX", role: "графики, трёхмерное векторное пространство, набор формул" },
  { name: "Docker Compose", role: "развёртывание всех сервисов одной командой" },
];

export const screenGuides = (): ScreenGuide[] => (getLang() === "ru" ? SCREEN_GUIDES_RU : SCREEN_GUIDES_EN);
export const glossary = (): GlossaryEntry[] => (getLang() === "ru" ? GLOSSARY_RU : GLOSSARY_EN);
export const thirdParty = (): Array<{ name: string; role: string }> => (getLang() === "ru" ? THIRD_PARTY_RU : THIRD_PARTY_EN);
