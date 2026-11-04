# Дообучение визуальной модели для ионограмм

Этот модуль готовит проверенные аннотации, дообучает **Qwen/Qwen3.5-2B** с QLoRA
и создаёт предложения полигонов для редактора. Это экспериментальный инструмент:
предсказания требуют экспертной проверки, а качество оценивается на независимых
наблюдениях.

Для обучения используется модель Hugging Face, а не GGUF для LM Studio.
Адаптер совместим с той базой и revision, на которых он обучен. Его нельзя
подставлять в модель другого размера или в произвольный GGUF.

## Требования

- Python 3.12 и отдельное окружение с зависимостями `training/requirements.txt`.
- NVIDIA GPU с CUDA и поддержкой BF16; необходимые версии PyTorch закреплены
  в зависимостях. Пример установки ниже использует CUDA 12.8 wheels.
- Достаточно свободной видеопамяти для модели, изображений и длины ответа.
  Порог запуска задаётся в `min_train_vram_gib` и `min_inference_vram_gib`.
- Место для весов, кэша, снимков данных и checkpoint.
- Настроенный проект `local_llm_helper` с `llmhelper/lock.py` и собственной
  конфигурацией: GPU-операции используют его общий lease. Путь задаётся в `helper_root`.

Наличие совместимой карты не гарантирует, что любая партия поместится в память.
Объём зависит от настроек обработки изображений и длины разметки. При нехватке
памяти модуль отказывает в запуске, не завершая чужие процессы и не выгружая
модели LM Studio самостоятельно.

На платформах без оптимизированных kernels Transformers может использовать
референсные реализации PyTorch; скорость следует проверять в своей среде.

## Установка

Команды выполняются из корня репозитория. В примере окружение находится в
игнорируемой папке `build`, отдельно от окружения редактора:

```powershell
python -m venv build/training-venv
$py = '.\build\training-venv\Scripts\python.exe'
& $py -m pip install torch==2.11.0 torchvision==0.26.0 --index-url https://download.pytorch.org/whl/cu128
& $py -m pip install -r training/requirements.txt
Copy-Item training/config.json training/local.json
```

В `training/local.json` настройте расположение помощника и данных. Например,
следующие поля подходят для помощника в соседнем репозитории и кэша в домашней
папке пользователя:

```json
{
  "helper_root": "../local_llm_helper",
  "cache_dir": "~/.cache/ionoreview-training/hub",
  "run_root": "~/.cache/ionoreview-training/runs",
  "dataset_root": "training/data"
}
```

Это фрагмент конфигурации: остальные поля сохраняются из `training/config.json`.
Относительные пути разрешаются от корня проекта, `~` — от домашней папки.
Сохраните JSON как UTF-8 без BOM. `training/local.json` не включается в Git.
В CLI параметр `--config` указывается **до** названия команды.

```powershell
& $py -m ionoreview.finetune --config training/local.json fetch
& $py -m ionoreview.finetune --config training/local.json doctor
```

`fetch` скачивает публичные веса заданного revision. Обучающие изображения и
аннотации при этом не отправляются в Hugging Face. `trust_remote_code` не включён.
`doctor` проверяет зависимости, наличие весов и доступность CUDA. Дополнительные
проверки: `doctor --cuda-smoke` и `doctor --load-cpu`.

## Подготовка эталона

Разметьте и примите ионограммы в редакторе. Для каждой записи должны быть
заданы корректный `split` и согласованные классы. Записи со статусом `pending`,
`changes` или `ambiguous` в обучение не включаются.

```powershell
& $py -m ionoreview.finetune --config training/local.json prepare
& $py -m ionoreview.finetune --config training/local.json inspect
```

Подготовка создаёт неизменяемый снимок с fingerprint. При тех же исходных данных
снимок используется повторно. Указатель на активный снимок —
`<dataset_root>/latest.json`; состав и преобразования записываются в `report.json`.
Исходные аннотации не перезаписываются.

Каждый пример содержит:

- обзор ионограммы для контекста;
- фрагмент в исходном разрешении;
- границы частоты и дальности из NPZ, если они доступны;
- время наблюдения, передатчик и приёмник из метаданных;
- JSON полигонов для этого фрагмента.

Размер, перекрытие сетки и обработка контуров задаются в конфигурации. Одинаковая
сетка используется при подготовке и предсказании; её положение не выбирается
по эталонным маскам. Координаты ответа нормированы в `0…1000` по центрам крайних
пикселей фрагмента. Группы исходной разметки сохраняются в эталоне; `group_id`
для предложений уточняет эксперт.

Преобразования контуров, исправления невалидной геометрии и пропущенные слишком
малые части записываются в отчёт снимка. Проверяйте эти сведения перед обучением.
Сравнение преобразованных масок с эталоном характеризует точность представления,
а не качество обученной модели.

Loss считается только по ответу ассистента. Prompt, изображения и padding
исключаются. `inspect` проверяет длину всех примеров: превышение
`max_seq_length` вызывает ошибку, а не молчаливое обрезание ответа.

Разделяйте данные по независимым наблюдениям или целым дням, а не по фрагментам.
Кропы одного изображения не являются независимыми примерами. Контролируйте
покрытие классов: отсутствие класса в train нельзя исправить его наличием
только в validation или test. Тестовая часть не используется для optimizer,
few-shot примеров или подбора настроек.

## Дообучение

Перед запуском освободите GPU от несовместимых задач. Команда использует общий
GPU lease помощника и проверяет свободную память.

```powershell
& $py -m ionoreview.finetune --config training/local.json train --name round001
```

Имя запуска должно быть новым. Настройки NF4/BF16, LoRA, learning rate, число
эпох и накопление градиента берутся из конфигурации. Vision encoder заморожен;
обучаются LoRA-проекции текстового декодера. Checkpoint выбирается по validation
loss, итоговый адаптер сохраняется в `<run_root>/round001/adapter`.

Для технической проверки цепочки можно ограничить число optimizer steps:

```powershell
& $py -m ionoreview.finetune --config training/local.json train --name smoke001 --max-steps 1
```

Такой запуск проверяет выполнение обучения и сохранение, но не подтверждает
качество предразметки. Диагностика и метрики доступны в папке запуска.
После получения новых принятых аннотаций повторите `prepare` и `inspect`, затем
создайте новый запуск с новым именем.

## Сравнение с базовой моделью

В примерах `$runs` должен совпадать с `run_root` выбранной конфигурации:

```powershell
$runs = Join-Path $HOME '.cache/ionoreview-training/runs'
& $py -m ionoreview.finetune --config training/local.json predict-set --split validation --out "$runs/baseline-val"
& $py -m ionoreview.finetune --config training/local.json evaluate --split validation --predictions "$runs/baseline-val"
& $py -m ionoreview.finetune --config training/local.json predict-set --split validation --adapter "$runs/round001/adapter" --out "$runs/round001-val"
& $py -m ionoreview.finetune --config training/local.json evaluate --split validation --predictions "$runs/round001-val"
```

База и адаптер сравниваются на одной части данных с одинаковыми настройками.
Оценка вычисляет семантические IoU/Dice для полных исходных изображений,
объединяя перекрывающиеся фрагменты. Пустые классы не повышают macro IoU.
Невалидный JSON считается ошибкой и пустым предсказанием; его доля выводится
отдельно. Неполная папка предсказаний не оценивается.

Эти метрики не являются instance AP и сами по себе не подтверждают физическую
интерпретацию мод. Сохраняйте фактические ответы модели для разбора ошибок.
После фиксации настроек проведите итоговую оценку, заменив `validation` на `test`.
Не используйте результаты теста для повторной подгонки этой же модели.

## Предложения для редактора

Укажите имя набора в `datasets` и идентификатор записи из его манифеста:

```powershell
& $py -m ionoreview.finetune --config training/local.json predict --pack my-set --case image_0001 --adapter "$runs/round001/adapter" --out "$runs/review-example"
```

Команда создаёт `proposal.labelme.json`, не изменяя `annotations`. Откройте тот же
случай в редакторе и используйте **Импорт разметки LabelMe…**. Проверьте границы,
классы и группы: перекрывающиеся фрагменты могут дать пересекающиеся предложения.
Автоматического принятия нет. При невалидных ответах JSON помечается как неполный.

Для пакетного предсказания на отдельном наборе:

```powershell
& $py -m ionoreview.finetune --config training/local.json predict-pack --pack-path datasets/blind-set --adapter "$runs/round001/adapter" --out "$runs/blind-proposals"
```

Этот режим загружает модель один раз для всего набора и не читает его ручные
аннотации. Для независимой проверки сохраняйте входной набор и предложения
модели отдельно от рабочего набора эксперта.

## MCP

Сервер `ionoreview.finetune.mcp_server` предоставляет операции подготовки,
обучения и предразметки. Для его процесса нужно то же Python-окружение, что
для CLI. Пример конфигурации клиента — [`mcp.example.json`](mcp.example.json).
Замените placeholders абсолютными путями к окружению и корню проекта.

MCP читает основной `training/config.json`. Перед запуском сервера настройте
его для своей среды; CLI-файл `training/local.json` сам по себе не меняет
конфигурацию MCP. Пример подключения не устанавливает сервер глобально
и не меняет настройки других MCP-клиентов.

Доступные инструменты:

- `training_dataset_status` — состав активного снимка;
- `prepare_training_data`, `inspect_training_data` — подготовка и проверка;
- `start_finetune(run_name, max_steps=0)` — запуск обучения в очереди;
- `propose_ionogram(pack, case_id, run_name)` — предразметка в очереди;
- `training_job_status(job_id)` — состояние и пути к результатам и журналу.

Пустой `run_name` у предразметки означает базовую модель. Если задано имя запуска,
адаптер должен существовать: скрытой замены на базовую модель нет. Тяжёлые задачи
выполняются отдельными процессами; MCP возвращает пути и счётчики, а не изображения
или весь текст генерации. Предложения модели остаются непроверенными данными.

## Экспорт модели

Адаптер используется напрямую через CLI или MCP. Для отдельной HF-копии
базовые веса можно объединить с адаптером:

```powershell
& $py -m ionoreview.finetune --config training/local.json merge --adapter "$runs/round001/adapter" --out "$runs/round001-merged-hf"
```

Результат содержит vision encoder и остаётся моделью Hugging Face. Для LM Studio
потребуется отдельная совместимая конвертация, включая визуальный projector.
Адаптеры, веса и датасеты не входят в сборку Windows-редактора.

## Проверка кода

```powershell
& $py -m pip install pytest
& $py -m pytest tests/test_finetune.py -q
```

Описание используемых API: [Qwen3.5 в Transformers](https://huggingface.co/docs/transformers/model_doc/qwen3_5),
[PEFT LoRA](https://huggingface.co/docs/peft/developer_guides/lora),
[bitsandbytes для Windows/CUDA](https://huggingface.co/docs/bitsandbytes/v0.50.2/en/installation).
