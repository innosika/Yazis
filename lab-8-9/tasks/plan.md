# Lector — голосовой ридер научных статей (ЯзИС, ЛР 8 + ЛР 9, вариант 1)

## Context

Две лабораторные по ЯзИС: ЛР 8 «Система синтеза речи» и ЛР 9 «Система распознавания речи».
Вариант 1 в обеих: **английский язык, научные статьи по computer science**. Требования похожи,
поэтому делаем одну систему **Lector**: веб-приложение, которое читает CS-статьи вслух
нейросетевым голосом и управляется голосом. Каталог `/home/user/University/Yazis/lab-8-9`
пока пустой: там только `.claude/skills` и `skills-lock.json`.

Решения пользователя:
- интерфейс **только на английском**;
- ключ Groq будет;
- «другое приложение» закрываем **расширением для Chrome/Chromium**;
- Ubuntu, docker compose + make, всё бесплатно, без тяжёлых локальных моделей;
- в интерфейсе нет пометок «ЛР 8» / «ЛР 9»;
- отчёт не нужен.

Машина: 14 ядер, 36 ГБ RAM, GPU нет, поэтому всё считается на CPU.

| Требование методички | Как закрываем |
|---|---|
| ЛР 8: ввод текста | Экран *New*: поле ввода, загрузка PDF, arXiv ID/URL, встроенная статья-пример |
| ЛР 8: вставка из буфера | Кнопка *Paste*, ⌘V на пустом экране, голосовая команда «read clipboard» |
| ЛР 8: указатель мыши в другом приложении (html) | Расширение Chrome: кнопка ▶ у выделения на любой странице, контекстное меню, Alt+R |
| ЛР 8: воспроизведение | Док-плеер, подсветка текущего предложения и слова, клик по предложению переходит к нему |
| ЛР 8: голос, темп, громкость и др. | 13 отобранных голосов US/UK (28 всего) и смесь двух голосов; темп 0.5–2×; высота тона ±4 полутона; громкость; паузы; правила чтения; словарь произношений |
| ЛР 9: список операций | Вкладка *Commands*: около 30 встроенных команд с вкл/выкл и фразами на каждом языке, свои команды-макросы, тестер (текст или аудиофайл) |
| ЛР 9: реакция с уведомлением | VAD, затем ASR, затем сопоставление, затем действие. Уведомляют HUD-пилюля (`aria-live`) с состояниями listening / hearing / recognizing / result / rejected, тост, звук, опциональное голосовое подтверждение и журнал *Activity* |
| ЛР 9: выбор ЕЯ | Язык распознавания English (по умолчанию) / Русский / Deutsch / Français, у каждого свой набор фраз; для синтеза — акцент US/UK |

## Технологии (ресёрч, сентябрь 2026)

| Задача | Выбор | Почему |
|---|---|---|
| TTS | **Kokoro-82M**: `kokoro` 0.9.4 (PyTorch **CPU**) + `misaki[en]` + espeak-ng | Лучшая открытая TTS для CPU: Apache-2.0, RTF около 0.2–0.5. **Отдаёт таймстемпы слов**, голоса смешиваются. Groq TTS на бесплатном тарифе даёт 3,6K токенов в день, это ничто. |
| ASR | **Groq `whisper-large-v3-turbo`** + локальная **Parakeet-TDT-0.6B-v3 int8** (`onnx-asr` 0.12) | Whisper: точность, параметры `language` и `prompt`, 20 RPM, 2000 RPD, но биллинг от 10 с на запрос. Parakeet: около 670 МБ, быстрая на CPU, en/ru/de/fr, не тратит квоту. |
| VAD | `@ricky0123/vad-web` 0.0.31 (Silero v5, onnxruntime-web) в браузере | На сервер уходят только фразы. Web Speech API в Chromium на Linux не работает. |
| LLM | Groq `openai/gpt-oss-20b`, strict `json_schema`, `reasoning_effort: low` | Фолбэк для свободных формулировок команд; explain и summarize. Llama убрали из free tier в августе 2026. |
| Импорт | `arxiv.org/html/<id>` (LaTeXML, формулы в `alttext`; проверено на 1706.03762), затем ar5iv, затем PDF; `pymupdf4llm`; `trafilatura` | Научные статьи в основном лежат на arXiv. |
| Бэкенд | Python **3.12** (kokoro требует `<3.13`), FastAPI, pydantic-settings, SQLAlchemy 2 + **SQLite (WAL)**, httpx, rapidfuzz, soundfile, soxr | Один пользователь; Postgres не нужен. |
| Фронтенд | React 19, Vite 8, TS strict, Tailwind v4, `radix-ui`, lucide-react, zustand, TanStack Query, sonner, cmdk, Vitest; шрифты @fontsource: Inter, Source Serif 4, JetBrains Mono | Как в lab-4, плюс доступные примитивы. Анимации на CSS, без motion. TS закрепить на версии, которую поддерживает typescript-eslint. |
| Расширение | Chrome MV3, чистый JS без сборки: content script (shadow DOM) + service worker (роутер) + **offscreen document** (fetch и звук) | Запросы к localhost идут из контекста расширения с `host_permissions`, поэтому нет Local Network Access и CORS страницы. |

Почему веб: всё поднимается в контейнерах, «другое приложение» закрывает расширение, а
веб-интерфейс проще сделать красивым.

## Продукт и UX

Минималистичный ридер в духе Readwise Reader / Speechify. Интерфейс монохромный, с одним
«голосовым» акцентом; произносимое предложение подсвечено маркером. Нейтральные тона
тёплые, бумажные; текст статьи набран серифом. Светлая и тёмная темы; экран 400 px не ломается.
Перед вёрсткой загрузить скилл `frontend-design`.

- **Library (левая панель):** недавние документы с прогрессом чтения, кнопка *New*.
- **New:** поле «Paste an abstract, a paragraph or a whole paper…». Там же *Paste*,
  *Upload PDF*, «arXiv ID or URL» и чипы-примеры. Встроенную статью про алгоритмы и
  нотацию я напишу сам; arXiv-ID подгружаются на лету.
- **Ридер:**
  - колонка около 70ch и оглавление;
  - предложения рендерятся как `<span data-s>`, формула — атомарный span;
  - текущее слово подсвечивается через **CSS Custom Highlight API** из rAF-цикла, без
    ре-рендера React;
  - панель у выделения: *Read selection · Read from here · Explain · Pronounce as…*;
  - переключатель *Spoken form* показывает произносимый вид текста, например
    `O(n log n)` → «big O of n log n».
- **Док-плеер:** ⏮ ⏯ ⏭, прогресс с метками разделов и оставшимся временем, скорость, громкость,
  чип голоса и **mic-orb** (кольца по уровню сигнала, цвет по состоянию).
- **Voice HUD** над доком: `“slower” → Speed 0.9×`,
  `Didn't catch that — did you mean “slower”?` или `Cloud cooling down — using local`.
- **Settings (справа), вкладки:**
  - *Voice*: голос с превью, смесь A/B, скорость, тон, громкость, паузы;
  - *Reading*: цитаты, формулы, URL, аббревиатуры, заголовки;
  - *Listening*: движок Auto/Cloud/Local, язык, режим, чувствительность, микрофон,
    подтверждения, совет про наушники;
  - *Commands*;
  - *Pronunciation*.
- **Activity:** поповер у mic-orb. Список событий хранится на клиенте: транскрипт →
  команда, метод, уверенность, движок, задержки. Сверху три числа.
- **⌘K:** палитра действий с их голосовыми фразами.
- **Хоткеи:** Space, ←/→, `[`/`]`, удержание **M** для push-to-talk.

## Архитектура

### Синтез
1. **Сегментатор** правиловый, со списком научных сокращений: Fig., Eq., Sec., et al., e.g.,
   i.e., vs., cf., инициалы, десятичные числа.
2. **Нормализатор — это переписчик спанов, а не цепочка замен строк.** Он работает со
   списком `Segment(src_start, src_end, spoken, frozen)`. Правила только расщепляют
   незамороженные сегменты; произносимый текст — их конкатенация. Инварианты: сегменты
   монотонны, не пересекаются и покрывают исходник.

   **misaki получает только «скучный» текст:** слова, целые числа и `.,;:?`. Всё остальное
   раскрываем сами. Синтаксис `[word](/ipa/)` из misaki **не используем**, он сдвигает
   смещения. Произношения задаются респеллингом в нашем слое.

   Приоритет P1 — 12 правил:
   - цитаты;
   - сокращения;
   - единицы и проценты;
   - акронимы (лексикон и эвристика);
   - Big-O / Θ / Ω;
   - символы и греческие буквы;
   - `x_i` и `2^n`;
   - перенос слов;
   - URL и e-mail;
   - заголовки;
   - идентификаторы;
   - версии и диапазоны.

   P2: LaTeX из `alttext` (`\frac`, `\sum`, …). Встроенный CS-лексикон и сокращения лежат в
   YAML в коде.
3. **Выравнивание** (`tts/align.py`). В каждом `Result` проверяем
   `"".join(t.text + t.whitespace) == chunk`, затем считаем кумулятивные смещения. Позиция
   токена в произносимом тексте через bisect даёт сегмент, а сегмент — исходный span.
   Если проверка не прошла, выравниваем посимвольно через difflib и пишем warning. Правила:
   - таймстемпы чанков сдвигаем на накопленную длину аудио (длинное предложение режется
     по 510 фонем);
   - у пунктуации `start_ts = None`;
   - при pitch-сдвиге таймстемпы делим на p;
   - EspeakFallback — часть readiness-проверки и отдельный тест, иначе OOV-слова молча
     пропадают.

   План Б: `generate_from_tokens`.
4. **Pitch.** Синтез со скоростью `s/p`, затем soxr-ресемплинг ×p, где `p = 2^(st/12)`,
   `st ∈ [−4, 4]`. Эффективная скорость зажата в [0.5, 2.0].
5. **Воркер инференса.** Одна модель и очередь с приоритетом: *now*, затем *prefetch*, затем
   *extension*. Одинаковые запросы дедуплицируются по хешу через общий Future; задачи
   отключившихся клиентов снимаются. Потоки: `torch.set_num_threads(6)`,
   `interop=1`, onnxruntime `intra=4`.
6. **Кеш:** `sha256(model, normalizer_ver, lexicon_ver, voice|blend, speed, pitch, spoken)`,
   WAV PCM16 24 кГц в `/data/cache`, LRU до 2 ГБ.
7. **API:** `POST /api/tts/synthesize` возвращает `{audio_url, duration, spoken,
   words:[{start,end,src_start,src_end}]}`. `GET /api/tts/audio/{hash}.wav` отдаётся с
   `immutable`. `POST /api/tts/segment` режет текст на единицы воспроизведения (для
   расширения). Единицу длиннее примерно 40 слов режем по `;` / `,`, так первый звук
   приходит примерно через 0.3–0.8 с.
8. **Клиент.** AudioContext стартует по жесту пользователя. Громкость — GainNode.
   Воспроизведение бесшовное через `start(when)` с паузами из настроек; пауза — через
   `ctx.suspend()`. Предзагрузка на 3 единицы вперёд, `AbortController` при переходе. Если
   скорость или голос сменились посреди предложения, текущую единицу запрашиваем заново и
   продолжаем с `start_ts` текущего слова.

### Распознавание и команды
1. **Профили VAD.** Для команд: `redemptionMs≈550`, `preSpeechPadMs≈300`,
   `minSpeechMs≈250`. Во время чтения — строгий `positiveSpeechThreshold≈0.7`. Параметры
   `ort.env.wasm.numThreads=1`, версия onnxruntime-web закреплена под vad-web.
2. **Защита от эха.** AEC Chrome не вычитает вывод Web Audio (crbug 687574), поэтому
   защита многоуровневая:
   - **push-to-talk** (удержание M или mic-orb) ставит TTS на паузу, эха нет вообще;
   - **hands-free без чтения:** обычный VAD, облачный движок;
   - **hands-free во время чтения:**
     - запрос уходит на **локальную Parakeet**, квота не тратится;
     - **вычитание эха:** транскрипт выравнивается со словами, которые реально звучали в
       окне `[speechStart − pad − 0.3 с, speechEnd]` (они точно известны из таймстемпов),
       и сопоставляется только остаток;
     - принимаются только exact, шаблон или fuzzy ≥ 90, без LLM и без автоприглушения;
   - в UI совет про наушники.

   Замер: 60 с TTS через динамики, должно выполниться 0 команд.
3. **ASR-роутер** (Auto/Cloud/Local). Groq получает короткий `prompt`: слова команд и
   несколько CS-терминов, **без текста TTS**. Обрабатываем `retry-after` и
   `x-ratelimit-*`; circuit breaker уводит на local. Parakeet грузится лениво и прогревается.
4. **Фильтры:** `no_speech_prob`; типовые галлюцинации («Thank you.»); вывод, повторяющий
   prompt; пустые ответы и повторы.
5. **Нормализация фразы:** регистр, пунктуация, числительные 0–100, порядковые и
   «one point five» для en/ru/de/fr.
6. **Матчер:**
   - (1) шаблоны со слотами `{number}{voice}{section}{term}` компилируются в regex,
     уверенность 1.0; `{section}` ищется fuzzy по заголовкам документа;
   - (2) иначе `rapidfuzz`, порог 82;
   - (3) иначе LLM, только если чтение не идёт, во фразе не больше 12 слов и результата
     нет в кеше; strict schema с enum включённых команд или `none`.

   Ответ: `{transcript, command, slots, confidence, method, alternatives, engine, timings}`.
7. **Каталог.** Около 30 действий, живут в коде вместе с фразами на 4 языках:
   - play/pause/resume/stop;
   - next/prev sentence и paragraph, repeat, start over, go to section, read abstract;
   - faster/slower/set speed, louder/quieter/mute;
   - switch voice / next voice;
   - where am I, time left;
   - explain {term}, summarize section;
   - read clipboard, new document, open library, dark/light, what can I say,
     stop listening.

   В БД хранятся только пользовательские правки: вкл/выкл, фразы, свои команды. Своя
   команда = фразы + 1…N шагов (действие + параметры) + ответ; например, «study mode»:
   speed 0.9, voice Emma и ответ «Study mode on». `make catalog` генерирует
   `frontend/src/voice/catalog.gen.json`. Обработчики типизированы как
   `Record<CommandId, Handler>`, так что `tsc` ловит команду без обработчика.
8. **Тестер в *Commands*:** ввести фразу **или загрузить или записать аудио** и увидеть, что
   сработает. Это и отладка, и демонстрация на защите, и способ проверить полный путь без
   микрофона.

### Документы, настройки, ассистент
- Блоки, разделы и предложения лежат в `documents.structure` (JSON); там же позиция чтения.
- `settings`: один JSON-профиль, его берёт и расширение.
- `lexicon`: пользовательские записи.
- Порядок импорта: paste/.txt/.md, затем PDF (с починкой переносов, вырезанием колонтитулов
  и References), затем arXiv, затем URL (P2).
- Assist: `POST /api/assist/explain` (термин плюс абзац) и `/summarize` (раздел, обрезанный
  под 8K TPM). Ответ показывается в карточке и зачитывается. Без ключа функции скрыты, в
  Settings есть подсказка.

### Контейнеры и модели
- **`models`** — одноразовый сервис на том же образе: `python -m scripts.fetch_models`.
  Скачивает Kokoro (около 330 МБ, плюс голоса), Parakeet int8 (около 670 МБ) и проверяет
  `en_core_web_sm` в томе `models` (`HF_HOME`). Повторный запуск ничего не качает.
- **`backend`:** `depends_on: models: service_completed_successfully`, `HF_HUB_OFFLINE=1`,
  healthcheck на `/api/health/ready` (статус по каждой модели плюс прогрев), `start_period
  60s`, порт **8030**.
- **`frontend`:** node:22 → nginx:1.27, порт **8100**.
  - Прокси `/api/`, `client_max_body_size 50m`.
  - `types { application/javascript mjs; application/wasm wasm; }`.
  - Ассеты VAD/ORT в `/vad/`, без immutable-кеша.
- **Dockerfile бэкенда.** Слои по порядку:
  1. apt `espeak-ng`;
  2. `torch==…+cpu` из `https://download.pytorch.org/whl/cpu`;
  3. `requirements.txt` с `--extra-index-url …/cpu` и закреплённым URL колеса
     `en_core_web_sm`;
  4. dev-зависимости;
  5. код.

  Кеш pip подключается через BuildKit `--mount=type=cache`. Проверка: `pip list | grep -ci
  nvidia` = 0, образ не больше 2 ГБ.
- **Makefile** по образцу lab-4. Цели: `help up down restart build models logs logs-api ps
  test test-all loopback catalog lint format shell info extension reset-db clean`.
  - `up` копирует `.env.example` в `.env`, если его нет, затем запускает
    `$(COMPOSE) run --rm models` (прогресс скачивания виден), затем `up -d --build --wait`,
    затем `info`.
  - `.env.example`: `GROQ_API_KEY`, `WEB_PORT=8100`, `API_PORT=8030`, `TTS_THREADS`.
  - Ключ в `lab-2/.env` уже есть. **Спросить пользователя**, копировать ли его.

### Расширение Chrome (`extension/`)
- `host_permissions`: `http://localhost:8100/*` и `http://127.0.0.1:8100/*`; options-страница
  для base URL.
- **Content script** не делает запросов. Он показывает ▶ у выделения и мини-плеер
  (pause / stop / speed) в shadow DOM.
- **Service worker** только маршрутизирует сообщения: контекстное меню *Read aloud with Lector*
  и *Open in Lector*, команда Alt+R.
- **Offscreen document** владеет состоянием плеера: `GET /api/settings`, затем
  `/api/tts/segment`, затем `/synthesize` по единицам, затем воспроизведение. Перед каждым
  запросом проверяем `runtime.getContexts` и пересоздаём документ: он закрывается после
  30 с тишины.
- Popup: статус и быстрые настройки. `make extension` собирает zip, в README инструкция
  «Load unpacked».

## Структура репозитория

```
lab-8-9/  Makefile docker-compose.yml .env.example .gitignore README.md(рус.) SPEC.md tasks/
  backend/ Dockerfile requirements*.txt pytest.ini ruff.toml mypy.ini
    app/ main.py config.py state.py db/{base,models}.py schemas/
      api/routes_{health,documents,tts,voice,commands,lexicon,settings,assist}.py
      text/{segment.py, normalize/{engine.py, rules_*.py}, lexicon.py, data/*.yaml}
      importers/{text,pdf,arxiv,web,structure}.py
      tts/{engine.py(воркер+приоритеты), voices.py, align.py, dsp.py, cache.py}
      asr/{groq.py, local.py, router.py, filters.py(галлюцинации, echo_subtract)}
      commands/{catalog.py, numbers.py, normalize.py, matcher.py, llm.py, service.py}
      llm/{client.py, assist.py}   data/sample_article.md
    scripts/{fetch_models.py, loopback.py, export_catalog.py}
    tests/ (fixtures/: arXiv HTML, маленький PDF, WAV; маркер slow)
  frontend/ Dockerfile nginx.conf vite.config.ts (static-copy ассетов VAD/ORT)
    src/{api/, stores/(player,settings,voice,activity), audio/{engine,earcons,wav}.ts,
         reader/, player/, voice/{mic.ts,actions.ts,catalog.gen.json,VoiceHud,MicOrb},
         library/, settings/tabs/, palette/, ui/, index.css(токены)}
  extension/ manifest.json background.js offscreen.{html,js} content.js popup.* options.* icons/
```

## Порядок работ

Сначала `SPEC.md` и `tasks/plan.md` в формате lab-4 (скиллы `spec-driven-development`,
`incremental-implementation`). Текст, выравнивание и матчер пишем через TDD. P1 — ядро,
закрывающее обе лабораторные. P2 делаем после, P3 — только если останется время.

| # | Срез | Проверка |
|---|---|---|
| T0 | Каркас: compose (models/backend/frontend), Makefile, health, SPA-оболочка с токенами и темами, `git init` | `make up`; `curl :8030/api/health/live`; :8100 открывается; образ не больше 2 ГБ, без nvidia |
| T1 | Модели и ядро TTS: `fetch_models`, обёртка Kokoro, воркер, прогрев, readiness | повторный `make models` ничего не качает; slow-тест: «Hello world» с таймстемпами; OOV «zyxwvnet» получает фонемы; RTF в логе |
| T2 | Сегментатор и нормализатор (движок спанов, 12 правил, YAML-лексикон) | не меньше 60 golden-кейсов input → spoken, инварианты спанов, golden-набор сегментации |
| T3 | API синтеза: выравнивание, кеш, pitch, голоса и смесь | каждый `src[a:b]` — реальное слово; кеш отвечает < 20 мс; +3 полутона меняют длительность ≤ 5 %; у предложения из 45 слов таймстемпы монотонны |
| T4 | Документы и импорт: text/md, затем PDF, затем arXiv; встроенная статья | фикстуры; `curl`-импорт `1706.03762` даёт оглавление с «Attention» |
| T5 | **Ридер и плеер** (ЛР 8): Library, New, ридер, док, движок, предзагрузка, подсветка слова, клик для перехода, настройки Voice/Reading, *Spoken form* | браузер: подсветка идёт за аудио, prefetch N+1…N+3 виден в сети, смена скорости посреди предложения, консоль чистая |
| T6 | Произношения и опции чтения | «LaTeX → lay-tek» меняет хеш аудио; pytest |
| T7 | ASR-бэкенд: Groq, Parakeet, роутер, circuit breaker, фильтры, echo-subtract | моки respx: 429 уводит на local с cooldown, 401 даёт понятную ошибку; unit-тесты фильтров; curl с WAV |
| T8 | Команды: каталог, числительные, шаблоны, fuzzy, LLM, правки, макросы, `/api/commands/test` | табличные тесты на 4 языках, 20 предложений статьи → `null`, LLM замокан |
| T9 | **Loopback** (`make loopback`): Kokoro синтезирует фразы команд и слот-варианты (3 голоса × 3 скорости), затем 16 кГц WAV, затем recognize (local). Плюс шум 20 дБ и подмешанное предложение статьи на −12 дБ с context (проверка echo-subtract); `ENGINE=groq` — 15 фраз с паузой 3 с | local exact ≥ 95 %; ложные срабатывания на 50 предложениях ≤ 2 %; печатается таблица точности |
| T10 | **Голос во фронтенде** (ЛР 9): MicVAD-профили, push-to-talk, HUD, mic-orb, звуки, тосты, Activity, реестр действий, echo guard | тестер с аудиофайлом из Kokoro: HUD и действие; ручная проверка с микрофоном; замер эха |
| T11 | UI Commands (вкл/выкл, фразы по языкам, конструктор макросов, тестер) и палитра ⌘K | «study mode» срабатывает и текстом, и голосом |
| T12 | Расширение Chrome | выделение на arxiv.org → ▶ играет; меню и Alt+R работают; остановка SW не рвёт звук; без бэкенда — понятная ошибка |
| T13 | P2: explain/summarize, UI смеси голосов, импорт URL, LaTeX-alttext | моки httpx, живой вызов с ключом |
| T14 | README (рус.): быстрый старт, требования → где, алгоритмы, ограничения, чек-лист ручной проверки. Строка `lab-8-9` в `University/CLAUDE.md` (правило самого файла) | `make clean && make up` с нуля с замером времени; `make lint test`; снимок `docker stats` |

P3, по остатку времени: диктовка, wake word, экспорт MP3, петля RTCPeerConnection для AEC.

## Риски

| Риск | Что делаем |
|---|---|
| Эхо TTS расходует квоту Groq и вызывает ложные команды | Многоуровневая защита (см. выше): во время чтения только local, только exact/fuzzy ≥ 90 |
| Подсветка слов сползает (чанки, pitch, OOV) | Проверка join-инварианта, кумулятивные смещения, деление на p, readiness espeak, тесты T3 |
| В образ попадает CUDA-torch или модели качаются в рантайме | CPU-индекс, отдельный сервис `models`, `HF_HUB_OFFLINE=1`, проверка nvidia = 0 |
| CPU-конкуренция задерживает первый звук | Одна модель, приоритетная очередь, разбиение длинных единиц, прогрев |
| Раздача ассетов VAD/ORT (MIME, версии) | Явные `types` в nginx, закреплённые версии, проверка в T10 |
| Расползание объёма | Объём замораживается после T12; P3 только по остатку времени |

## Проверка end-to-end
1. `make clean && make up`: все сервисы healthy, `ready` отвечает 200, `make info` печатает URL.
2. `make test` (быстрые тесты), `make loopback` (точность голосового пути без микрофона),
   `make lint` (ruff, mypy strict, eslint, tsc).
3. Встроенный браузер, `http://localhost:8100`:
   - импорт встроенной статьи и arXiv-статьи, чтение;
   - `/api/tts/synthesize` проходит, подсветка движется;
   - смена голоса, скорости и тона применяется;
   - *Spoken form*;
   - тестер: текст «slow down a bit» → Slower (llm), аудиофайл «go to section three» → раздел 3;
   - своя команда;
   - темы и ширина 400 px;
   - в консоли нет ошибок.
4. Микрофон, эхо через динамики и расширение проверяет пользователь вручную по чек-листу
   из README: во встроенном браузере нет реального микрофона и нельзя поставить
   unpacked-расширение.
