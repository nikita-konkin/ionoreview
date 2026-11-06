# Сборка ИоноРазметки для Windows

`IonoReview.exe` — настольный редактор без установки Python. Сборка предназначена
для Windows 10/11 x64. Распакуйте **весь** `IonoReview-windows-x64.zip` в доступную
для записи папку и запустите `IonoReview/IonoReview.exe`. Папка `_internal` должна
оставаться рядом с exe: это переносимая сборка в одной папке, а не один файл.

Если рядом с exe есть `datasets/catalog.json`, сразу откроется каталог.
Если данных рядом нет, программа предложит выбрать готовый набор с
`manifest.json`, каталог с `catalog.json` или обычную папку изображений.
Для обычных изображений отдельно выбирается место рабочего набора и разметки.
Версия отображается в заголовке окна. В v0.2.0 обновлён внешний вид, добавлены
значок приложения, схема цветов «Моды», правила разметки с примерами и выбор
языка; открытие папки перенесено в меню **Файл**. В v0.1.1 добавлены отдельная кнопка
**Открыть папку…** и выбор другой папки из каталога. Можно выбирать весь
комплект с подпапкой `dataset` либо `images`, `arrays`, `annotations` внутри
готового набора. Набор определяется по `manifest.json`, аннотации сохраняются.
Те же варианты поддерживаются параметром `--data-root`.
Данные не сохраняются во временную папку распаковки или внутрь `_internal`.

Чтобы открыть отдельную библиотеку, укажите её относительный или абсолютный путь:

```powershell
.\IonoReview.exe --data-root .\datasets
```

В сборке нет пользовательских ионограмм, принятых аннотаций, научных документов
и весов моделей. Нужные наборы переносятся отдельно, вместе с `images`, `arrays`
при их наличии, `annotations`, `history` и `manifest.json`.
Подготовка LFS/HDF5 и дообучение VLM выполняются в Python-проекте;
exe содержит редактор и методы кластеризации.

## GitHub Actions

Workflow: [`.github/workflows/windows-exe.yml`](../.github/workflows/windows-exe.yml).
Он запускается на push в `main`/`master`, тег `v*`, pull request и вручную через
**Actions → Windows executable → Run workflow**. Изменения только в Markdown
не запускают автоматическую сборку; используйте ручной запуск или новый тег,
если нужно перепаковать обновлённую документацию.

Права workflow ограничены чтением репозитория. Публикация GitHub Release
автоматически не выполняется. Результат доступен в **Artifacts** запуска:

- `IonoReview-windows-x64.zip`;
- SHA-256 архива;
- `frozen-self-test.json` — результат проверки скомпилированного exe.

CI создаёт отдельное окружение Python 3.12, устанавливает зафиксированные
зависимости из `requirements-build.txt`, проверяет редактор и собирает его
PyInstaller. Самопроверка exe проверяет Tk, NumPy/SciPy/sklearn/OpenCV, PNG/NPZ,
оба метода кластеризации, сохранение и экспорт синтетической аннотации,
распознавание вложенных папок и переключение между наборами без изменения JSON.
Пользовательские данные в тестах не используются; самопроверка закрывается
автоматически. Артефакты хранятся 30 дней. Датасеты и модели в них не входят.

## Локальная сборка

Из корня исходного проекта, Python 3.12 x64 и PowerShell:

```powershell
python -m venv build/windows-venv
.\build\windows-venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\tools\build_windows.ps1 -Python .\build\windows-venv\Scripts\python.exe -OutputRoot .\build\windows
```

Используйте отдельное окружение без CUDA/LLM-пакетов. Скрипт выполняет сборку,
проверку exe, создание ZIP и контрольной суммы. С указанным `OutputRoot` результат
находится в `build/windows`, исполняемый файл — в
`build/windows/dist/IonoReview/IonoReview.exe`.

Если `OutputRoot` не задан, используется стандартная пользовательская папка
`%LOCALAPPDATA%\IonoReview\build`. Внутри `_internal` и папок научных данных
сборку не размещайте. При работе с Git исключите виртуальные окружения,
датасеты и результаты сборки из контроля версий.

## Отдельная диагностика exe

Команды выполняются из папки распакованного приложения:

```powershell
$report = Join-Path (Get-Location) 'self-test.json'
$process = Start-Process .\IonoReview.exe -ArgumentList @('--self-test', ('"' + $report + '"')) -PassThru -Wait -WindowStyle Hidden
$process.ExitCode
Get-Content $report
```

Нулевой код завершения и `ok: true` означают успешную самопроверку.
При ошибке обычного запуска сведения записываются в
`%LOCALAPPDATA%\IonoReview\last-error.log`. Ошибки обработчиков во время работы
редактора попадают в `%LOCALAPPDATA%\IonoReview\runtime.log`.

Основа схемы размещения файлов: [PyInstaller runtime information](https://pyinstaller.org/en/stable/runtime-information.html).
