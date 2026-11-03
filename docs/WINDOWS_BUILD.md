# Сборка ИоноРазметки для Windows

`IonoReview.exe` — настольный редактор без установки Python. Сборка предназначена
для Windows 10/11 x64. Распакуйте **весь** `IonoReview-windows-x64.zip` в доступную
для записи папку и запустите `IonoReview/IonoReview.exe`. Папка `_internal` должна
оставаться рядом с exe: это переносимая сборка в одной папке, а не один файл.

Если рядом с exe есть `datasets/catalog.json`, сразу откроется каталог.
Если данных рядом нет, программа предложит выбрать готовый набор с
`manifest.json`, каталог с `catalog.json` или обычную папку изображений.
Для обычных изображений отдельно выбирается место рабочего набора и разметки.
Данные не сохраняются во временную папку распаковки или внутрь `_internal`.

Можно открыть уже подготовленную библиотеку напрямую:

```powershell
.\IonoReview.exe --data-root N:\ionoreview\datasets
```

В сборке **нет** пользовательских ионограмм, принятых аннотаций, научных
документов и весов моделей. Переносите нужные наборы отдельно, вместе с их
`images`, `arrays`, `annotations`, `history` и `manifest.json`.
Подготовка исходных LFS/HDF5 и дообучение VLM выполняются в Python-проекте;
этот exe содержит редактор и методы кластеризации.

## GitHub Actions

Workflow: `.github/workflows/windows-exe.yml`. Запускается на push в `main`/`master`,
тег `v*`, pull request и вручную через **Actions → Windows executable → Run workflow**.
Права workflow ограничены чтением репозитория; публикация Release автоматически
не выполняется. Результат находится в **Artifacts** соответствующего запуска:

- `IonoReview-windows-x64.zip`;
- SHA-256 архива;
- `frozen-self-test.json` — результат проверки именно скомпилированного exe.

CI устанавливает зафиксированные зависимости из `requirements-build.txt`,
проверяет редактор, собирает приложение PyInstaller и запускает самопроверку
скомпилированного файла. Проверяются Tk, NumPy/SciPy/sklearn/OpenCV, PNG/NPZ,
оба метода кластеризации, сохранение и экспорт синтетической аннотации.
Самопроверка автоматически закрывается; данные пользователя не используются.
Артефакты хранятся 30 дней. Датасеты и модели в артефакт не попадают.

Чтобы workflow работал на GitHub, репозиторий должен быть загружен на GitHub.
Наличие YAML в локальном Git само по себе не запускает облачную сборку.

## Локальная сборка

Из корня исходного проекта, Python 3.12 x64:

```powershell
python -m venv C:\Builds\ionoreview-venv
C:\Builds\ionoreview-venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\tools\build_windows.ps1 -Python C:\Builds\ionoreview-venv\Scripts\python.exe -OutputRoot C:\Builds\ionoreview-output
```

Используйте отдельное окружение без CUDA/LLM-пакетов. Скрипт сам выполняет
замораживание, тест exe, создание ZIP и контрольной суммы. Build/dist по умолчанию
находятся в `%LOCALAPPDATA%\IonoReview\build`, а не в папке с научными данными.

Для отдельной диагностики exe:

```powershell
$p = Start-Process .\IonoReview.exe -ArgumentList '--self-test', 'C:\Temp\ionoreview-test.json' -PassThru -Wait
$p.ExitCode
Get-Content C:\Temp\ionoreview-test.json
```

При ошибке обычного запуска сведения записываются в
`%LOCALAPPDATA%\IonoReview\last-error.log`. Ошибки обработчиков во время
работы редактора попадают в `%LOCALAPPDATA%\IonoReview\runtime.log`.

Основа схемы размещения файлов: [PyInstaller runtime information](https://pyinstaller.org/en/stable/runtime-information.html).
