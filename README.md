# WhisperX Web

Локальное веб-приложение для расшифровки аудио и видео с разделением текста по спикерам.

Приложение запускается на вашем компьютере, открывается в браузере и умеет:

- загружать аудио и видео файлы;
- скачивать звук по ссылке через `yt-dlp`;
- записывать звук с микрофона;
- определять или задавать количество спикеров;
- экспортировать результат в `TXT`, `SRT` и `JSON`.

Эта инструкция рассчитана на чистый компьютер. Папка проекта может лежать где угодно: на рабочем столе, на диске `D:`, в загрузках или в любой другой папке.

Для установки нужен интернет. На диске желательно иметь не меньше 10-20 ГБ свободного места: зависимости и модели могут занимать несколько гигабайт.

## 1. Что должно быть в папке проекта

В папке проекта должны лежать такие файлы и папки:

```text
server.py
pyproject.toml
uv.lock
README.md
audio/
models/
templates/
static/
```

Если этих файлов нет, значит вы открыли не ту папку.

## 2. Установка на Windows с нуля

Откройте PowerShell.

Проверьте, доступен ли `winget`:

```powershell
winget --version
```

Если команда не найдена, установите из Microsoft Store приложение `App Installer`, затем откройте новый PowerShell и повторите проверку.

Установите `uv`:

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Закройте PowerShell и откройте его заново.

Проверьте `uv`:

```powershell
uv --version
```

Установите FFmpeg:

```powershell
winget install -e --id Gyan.FFmpeg --accept-source-agreements --accept-package-agreements
```

Закройте PowerShell и откройте его заново.

Проверьте FFmpeg:

```powershell
ffmpeg -version
```

Установите Python 3.13 через `uv`:

```powershell
uv python install 3.13
```

Проверьте Python:

```powershell
uv python list
```

## 3. Как открыть терминал в папке проекта

Самый простой способ:

1. Откройте папку проекта в Проводнике.
2. Щелкните правой кнопкой мыши по пустому месту внутри папки.
3. Выберите `Open in Terminal` или `Открыть в Терминале`.

После этого проверьте, что терминал действительно открыт в папке проекта:

```powershell
dir
```

В списке должны быть `server.py`, `pyproject.toml` и `uv.lock`.

Если терминал открыт не там, перейдите в папку проекта вручную:

```powershell
cd "ПОЛНЫЙ_ПУТЬ_К_ПАПКЕ_ПРОЕКТА"
```

Примеры:

```powershell
cd "C:\Users\User\Desktop\whisperx-web"
cd "D:\Projects\whisperx-web"
cd "C:\Users\User\Downloads\whisperx-web"
```

Путь у каждого компьютера свой. Не копируйте примеры буквально, если ваша папка лежит в другом месте.

## 4. Установка зависимостей проекта

Все следующие команды выполняйте внутри папки проекта, где лежит `pyproject.toml`.

Установите зависимости:

```powershell
uv sync
```

Это создаст виртуальное окружение `.venv` внутри папки проекта и установит все библиотеки из `pyproject.toml` и `uv.lock`.

Проверьте, что сервер хотя бы запускает справку:

```powershell
uv run python server.py --help
```

Если появилась справка с параметрами `--host`, `--port`, `--model`, `--device`, значит установка Python-зависимостей прошла успешно.

## 5. Первый запуск на CPU

Для первого запуска используйте маленькую модель. Она быстрее скачивается и проще проверяется:

```powershell
uv run python server.py --model tiny --device cpu --port 8000
```

При первом запуске будут скачаны модели. Это нормально. Дождитесь строки примерно такого вида:

```text
Server: http://0.0.0.0:8000
```

Не закрывайте терминал. Пока сервер работает, это окно должно оставаться открытым.

Откройте в браузере:

```text
http://localhost:8000
```

Если страница открылась, приложение запущено.

## 6. Как пользоваться

В веб-интерфейсе выберите источник:

- `File` - загрузить аудио или видео файл с компьютера;
- `URL` - вставить ссылку на поддерживаемый сайт;
- `Mic` - записать звук с микрофона.

Перед запуском можно выбрать:

- язык расшифровки, например `ru`, `en` или автоопределение;
- количество спикеров, например `2`, или `0` для автоопределения.

После обработки можно экспортировать результат в `TXT`, `SRT` или `JSON`.

## 7. Обычный запуск после первой проверки

Когда первый запуск прошел успешно, можно использовать модель `small`:

```powershell
uv run python server.py --model small --device cpu --port 8000
```

CPU-запуск работает почти на любом компьютере, но длинные записи могут обрабатываться долго.

## 8. Запуск на NVIDIA GPU

GPU-запуск нужен только если на компьютере есть NVIDIA-видеокарта и установлен свежий драйвер NVIDIA.

Запуск Whisper и диаризации на GPU:

```powershell
uv run python server.py --model large-v3 --device cuda --onnx-device cuda --port 8000
```

Если Whisper на GPU работает, но ONNX-диаризация падает с ошибкой CUDA, оставьте диаризацию на CPU:

```powershell
uv run python server.py --model large-v3 --device cuda --onnx-device cpu --port 8000
```

Если GPU-запуск не нужен, используйте CPU-команду из предыдущего раздела.

## 9. Запуск через короткую команду

В проекте есть script entrypoint `whisperx-web`.

Можно запускать так:

```powershell
uv run whisperx-web --model small --device cpu --port 8000
```

Это то же приложение, просто без явного `python server.py`.

## 10. Параметры запуска

| Параметр | По умолчанию | Описание |
|---|---:|---|
| `--host` | `0.0.0.0` | Адрес, на котором слушает сервер. |
| `--port` | `8000` | Порт сервера. |
| `--model` | `small` | Модель Whisper: `tiny`, `base`, `small`, `medium`, `large-v2`, `large-v3`, `turbo`. |
| `--device` | `auto` | Устройство для Whisper: `auto`, `cpu`, `cuda`. |
| `--compute-type` | `auto` | Тип вычислений: `auto`, `float16`, `int8_float16`, `int8`. |
| `--onnx-device` | `auto` | Устройство для ONNX-диаризации: `auto`, `cpu`, `cuda`. |
| `--gap` | `1.5` | Пауза в секундах, после которой начинается новая реплика. |
| `--chunk-duration` | `10.0` | Размер окна диаризации в секундах. |
| `--chunk-step` | `2.5` | Шаг окна диаризации в секундах. |
| `--hf-cache` | `.cache/hf` | Папка кэша Hugging Face моделей. |
| `--yandex-token` | пусто | Токен Яндекс.Музыки для скачивания треков из `music.yandex.ru`. |

Важно: у сервера нет параметра запуска `--language`. Язык задается в веб-интерфейсе или в API-запросе.

## 11. Примеры запуска

Минимальная проверка:

```powershell
uv run python server.py --model tiny --device cpu
```

Обычный CPU-запуск:

```powershell
uv run python server.py --model small --device cpu
```

Более качественная модель на CPU:

```powershell
uv run python server.py --model medium --device cpu
```

GPU-запуск:

```powershell
uv run python server.py --model large-v3 --device cuda --compute-type float16 --onnx-device cuda
```

Другой порт:

```powershell
uv run python server.py --model small --device cpu --port 8010
```

Своя папка кэша моделей:

```powershell
uv run python server.py --model small --device cpu --hf-cache ".cache/hf"
```

Запуск с токеном Яндекс.Музыки:

```powershell
uv run python server.py --model small --device cpu --yandex-token "ВАШ_ТОКЕН"
```

## 12. API

API нужно только если вы хотите обращаться к серверу не через веб-интерфейс.

### `GET /health`

Проверка состояния:

```powershell
curl.exe http://localhost:8000/health
```

Пример ответа:

```json
{
  "status": "ok",
  "models_loaded": true,
  "device": "cpu",
  "model": "small",
  "yandex_token_set": false
}
```

### `POST /transcribe`

Расшифровка загруженного файла.

Поля формы:

- `file` - аудио или видео файл;
- `language` - язык, например `ru` или `en`; пустая строка включает автоопределение;
- `num_speakers` - количество спикеров; `0` включает автоопределение.

Пример:

```powershell
curl.exe -X POST http://localhost:8000/transcribe `
  -F "file=@audio.mp3" `
  -F "language=ru" `
  -F "num_speakers=2"
```

### `POST /transcribe/url`

Скачивание аудио по ссылке и расшифровка.

Пример:

```powershell
curl.exe -X POST http://localhost:8000/transcribe/url `
  -H "Content-Type: application/json" `
  -d '{"url":"https://youtu.be/...","language":"ru","num_speakers":0}'
```

Для Яндекс.Музыки токен передается при запуске сервера через `--yandex-token`.

### `POST /export/{fmt}`

Экспорт результата.

Поддерживаемые форматы:

- `txt`;
- `srt`;
- `json`.

В тело запроса передается JSON, полученный из `/transcribe` или `/transcribe/url`.

## 13. Поддерживаемые файлы

Для загрузки поддерживаются:

```text
mp3, wav, flac, m4a, ogg, opus, aac, wma, webm, mp4, mkv
```

Если файл не читается напрямую, приложение пробует конвертировать его через FFmpeg.

## 14. Остановка приложения

Чтобы остановить сервер, вернитесь в окно терминала, где он запущен, и нажмите:

```text
Ctrl+C
```

После остановки страница `http://localhost:8000` перестанет работать до следующего запуска.

## 15. Обновление или переустановка зависимостей

Если зависимости сломались или окружение нужно пересоздать, выполните внутри папки проекта:

```powershell
Remove-Item -Recurse -Force .venv
uv sync
```

Если папки `.venv` нет, первая команда может вывести ошибку. В этом случае просто выполните `uv sync`.

## 16. Частые проблемы

### `uv` не найден

Закройте терминал, откройте новый и проверьте:

```powershell
uv --version
```

Если команда все еще не найдена, повторите установку `uv` из раздела 2.

### `ffmpeg` не найден

Закройте терминал, откройте новый и проверьте:

```powershell
ffmpeg -version
```

Если команда не найдена, повторите установку FFmpeg:

```powershell
winget install -e --id Gyan.FFmpeg --accept-source-agreements --accept-package-agreements
```

### `server.py` не найден

Вы находитесь не в папке проекта. Выполните:

```powershell
dir
```

Если в списке нет `server.py`, перейдите в правильную папку через `cd "ПУТЬ_К_ПАПКЕ"`.

### Первый запуск долго скачивает файлы

Это нормально. При первом запуске скачиваются модели Whisper и модель диаризации. Следующие запуски будут быстрее.

### Браузер пишет, что сайт недоступен

Проверьте, что сервер все еще запущен в терминале. Также убедитесь, что открываете:

```text
http://localhost:8000
```

Если вы запускали сервер с другим портом, например `--port 8010`, открывайте:

```text
http://localhost:8010
```

### `Models not loaded yet`

Модели еще загружаются. Подождите окончания загрузки в терминале и обновите страницу.

### GPU не используется при `--device auto`

Запустите явно:

```powershell
uv run python server.py --device cuda --onnx-device cuda
```

Если будет ошибка ONNX/CUDA:

```powershell
uv run python server.py --device cuda --onnx-device cpu
```

### Ошибка при обработке ссылки

Проверьте:

- установлен ли FFmpeg;
- открывается ли ссылка в браузере;
- поддерживает ли сайт скачивание через `yt-dlp`;
- не требует ли сайт авторизации, cookies или ограниченного доступа.

## 17. Linux и macOS

Основная инструкция выше написана для Windows.

На Linux порядок такой же: установить `uv`, установить FFmpeg, перейти в папку проекта, выполнить `uv sync`, затем запустить сервер.

Ubuntu/Debian:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
sudo apt update
sudo apt install -y ffmpeg
uv python install 3.13
uv sync
uv run python server.py --model small --device cpu --port 8000
```

После запуска откройте:

```text
http://localhost:8000
```

macOS сейчас не основной поддерживаемый сценарий для этой папки без изменений, потому что в `pyproject.toml` указана зависимость `onnxruntime-gpu`. Для macOS обычно требуется заменить ее на CPU-версию `onnxruntime` и пересобрать окружение.

## 18. Структура проекта

```text
server.py              FastAPI-сервер, API и запуск моделей
pipeline.py            Загрузка аудио, Whisper, диаризация и группировка реплик
formatting.py          Экспорт в TXT, SRT и JSON
audio/                 Загрузка аудио и источники URL
models/                Whisper и ONNX-диаризация
templates/index.html   Веб-интерфейс
static/                Статические файлы
pyproject.toml         Зависимости и entrypoint
uv.lock                Зафиксированные версии зависимостей
```
