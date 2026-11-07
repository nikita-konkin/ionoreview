"""User-facing reference shared by the Rules window and its coverage test."""

HELP_TEXT = """ПРИЁМКА ИОНОГРАММ

Создать проект из H5… — выбрать папку исходных H5/LFS (с подпапками), затем
папку назначения. Создаётся отдельный проект: PNG в images, матрицы NPZ с
физическими осями в arrays, разметка в annotations. Проект открывается автоматически.
Неподходящие файлы пропускаются; причины записываются в manifest.json.
Отмена останавливает обработку после текущего файла и сохраняет готовую часть.
Исходники не изменяются. Готовый проект открывается через Открыть папку….

Верхняя панель: меню Файл содержит Открыть папку… (Ctrl+O), Каталог…,
Сохранить набор как…, Импорт разметки LabelMe… и Экспорт принятых…. Каталог…
открывает список наборов; в нём доступна Открыть другую папку…. Меню Язык
переключает интерфейс, справку и руководство между русским и английским
(выбор запоминается в настройках набора). Правила разметки открывают руководство
с примерами кадров, Справка — это описание всех кнопок. Можно выбрать весь
комплект dataset либо вложенную
папку images/annotations готового набора - программа найдёт его manifest.json.
Архив только с JSON не содержит самих изображений: для просмотра нужен полный
набор с manifest.json, images, arrays и annotations.
Полоса рядом с названием показывает долю принятых случаев. Кнопка Все пути ▾
раскрывает пути измерения и последнего экспорта; PNG и результат JSON видны всегда.
В наборах для слепой ручной проверки автоматические подсказки и их импорт
отключаются настройкой набора; разрешение кластеризации указано в задании.

Разметка считается проверенной только после явного принятия экспертом. Просмотр,
масштабирование, перемещение и изменение контраста не меняют координаты объектов
или статус. Геометрическая правка принятой маски возвращает случай в ожидание.

ИНСТРУМЕНТЫ НАД ГРАФИКОМ

Выбор / вершины — выберите объект в списке либо щёлкните внутри полигона.
У выбранного объекта видны белые вершины: перетаскивайте их левой кнопкой мыши.
Перетаскивание внутри маски сдвигает её целиком, сохраняя форму. Маска не выходит
за границы исходного изображения. При переносе двигать всю группу — сдвигать
сразу все полигоны с тем же непустым group_id. Один перенос отменяется через
Отмена / Ctrl+Z. Простой щелчок без переноса не изменяет статус принятия.

Выделение — протяните рамку вокруг нескольких масок или кандидатов. Выбираются
контуры, пересекающие рамку. Ctrl или Shift добавляет рамку к текущему выделению.
В режиме выбора Ctrl/Shift + щелчок добавляет или исключает отдельный контур.
В списке Объекты также работают Ctrl и Shift. Ctrl+A на графике выбирает всё.

После выделения прямо на графике появляется меню меток. Нажмите 1F, 2F, E,
Es, 1E, 3F, Signal или Interference: метку получат все выделенные полигоны за
одно действие. Выделенные кандидаты при этом добавляются как редактируемая
разметка; остальные остаются в предпросмотре. Вся группа расширяет выделение
на все части выбранной группы/кластера. Снять выделение убирает подсветку и меню.
Правый щелчок по выделению повторно открывает меню; при рисовании полигона он,
как прежде, замыкает его. Меню не меняет метки до нажатия кнопки класса.

Полигон — рисование нового объекта текущего класса. Каждый щелчок добавляет
вершину. Незавершённые белые линии ещё не являются сохранённой маской.

Область — приближение прямоугольника. Нажмите и протяните левой кнопкой вокруг
нужного участка. После отпускания программа покажет его и вернёт инструмент
выбора. Разметка при этом не меняется.

Замкнуть — завершить полигон минимум из трёх точек. Аналоги: Enter при фокусе
на графике или правая кнопка мыши. Точки должны охватывать полосу видимого эха.

Убрать точку — удалить последнюю вершину незамкнутого полигона. Можно нажимать
повторно. Аналоги: Backspace на графике и Ctrl+Z во время рисования. Готовые
полигоны эта кнопка не удаляет. Когда незавершённых точек нет, кнопка отключена.

Маски — показать или скрыть наложение разметки для проверки исходного сигнала.

МАСШТАБ И ДАЛЬНОСТЬ

Весь кадр — показать весь сохранённый диапазон частот и дальности.

Вокруг масок — приблизить выбранный полигон с полями. Если ничего не выбрано,
показать все маски полезного сигнала. При отсутствии масок используйте Область
или задайте границы дальности вручную.

+ / − — приблизить или отдалить график относительно его центра.

Дальность, км — нижняя и верхняя границы отображения. Показать применяет их;
Enter в любом из двух полей делает то же. Допустима десятичная точка или запятая.
Например, 2700–2800 км. Окно вне измеренного диапазона не применяется.

Список диапазонов — предустановки 1000–5000, 1500–2000, 2000–2500, 2500–3000,
2700–3100, 3000–3500, 3500–4000, 4500–5000 км. Выбор сразу меняет только дальность,
сохраняя текущий диапазон частот. Числовые поля показывают применённые границы.

Колесо над графиком — масштабирование возле курсора. Shift + колесо меняет
только дальность. Средняя кнопка мыши с перетаскиванием сдвигает вид. Панели,
кнопки и шрифты при масштабировании графика остаются на месте. Увеличение
показывает исходные пиксели без сглаживания и не добавляет разрешения измерений.

Шкала дБ — два ползунка границ цветовой шкалы. Меняется только отображение.
Прозрачность — интенсивность заливки масок; контуры остаются видны.
Цвета — «Моды»: ионограмма в оттенках серого, E/Es/1E оранжевым, 1F синим,
2F зелёным, остальные метки серым пунктиром; «Turbo» — прежняя палитра.
Подписи — названия классов слева от масок.
Справа под графиком показаны частота и дальность под курсором.

ЛЕВАЯ ПАНЕЛЬ

Изображения — список случаев и их статусов. Выбор открывает случай. Правки
предыдущего сохраняются при переходе. Полоса прокрутки и колесо над свободной
областью формы прокручивают форму; над списком — сам список.
При запуске открывается последний сохранённый случай; если его ещё нет,
выбирается первая ожидающая ионограмма.

Эксперт — имя человека, принимающего текущую разметку. Это запись об авторе
проверки, не электронная подпись. Без имени принятие недоступно.

Объекты — полигоны текущего изображения. Указаны класс, число вершин и группа.
Выбор объекта выделяет его на графике. Signal — полезный сигнал без установленной
физической моды. Доступны также 1E, 1F, 2F и Interference (помеха).

Сменить класс — присвоить всем выделенным объектам класс из выпадающего списка.
Меняется только выделение. Для назначения класса всей группе сначала нажмите
Вся группа в меню на графике. Если выбранная часть группы получает другой класс,
программа отделяет её в новую группу, сохраняя метки остальных частей.
Дополнительно доступны E, Es, 3F. Согласуйте смысл E и 1E перед обучением,
чтобы один физический класс не получил две разные метки.

Удалить — удалить все выбранные полигоны или отклонить выбранные кандидаты.
Аналог: Delete на графике.
Действие можно отменить кнопкой Отмена или Ctrl+Z.

Группа… — задать общий номер для отдельных полигонов одного экземпляра моды.
Одинаковый номер означает части одного объекта. 0 убирает группировку. Разные
физические моды нельзя объединять только из-за общего класса Signal.

Отмена — отменить последнее изменение геометрии, класса или группы. При рисовании
сначала убирает последнюю незавершённую точку. Аналог: Ctrl+Z. После перехода
к другому изображению память отмены очищается; прежние сохранённые версии
остаются в папке history.

Полезный сигнал отсутствует — явная отрицательная разметка. Нужна для принятия
случая без масок сигнала. Несовместима с наличием полигонов сигнала.

Замечание эксперта — пояснение к проверке. Для исправления и неоднозначности
комментарий обязателен. Классы физических мод и спорные участки подтверждает
эксперт. Черновик ассистента или модели сам по себе эталоном не считается.

РЕШЕНИЯ И СОХРАНЕНИЕ

Принять и далее — сохранить разметку со статусом accepted и открыть следующий
случай. Требуется имя эксперта и маски сигнала либо явная отметка его отсутствия.
Аналог: Ctrl+Enter. Только принятые случаи попадут в экспорт.

На исправление и далее — статус changes, требуется комментарий.
Неоднозначно и далее — статус ambiguous, требуется комментарий.
Оба решения сохраняют запись и переходят дальше; они не попадают в экспорт.

← Назад / Далее → — перейти между ионограммами без принятия. Имеющиеся правки
сохраняются. Незамкнутый полигон нужно закончить или отменить.

Сохранить — записать текущие изменения и остаться на изображении. Аналог: Ctrl+S.
Сохраняются полигоны, имя, комментарий и текущий статус. Файлы измерений не меняются.
Предыдущая сохранённая версия попадает в history. Конфликт версий при одновременной
работе двух окон не позволяет молча перезаписать чужие правки.

Esc — отменить весь незавершённый полигон или рамку приближения. Если нужно убрать
только одну точку, используйте Backspace или Убрать точку.

ПУТИ ВНИЗУ ОКНА

Исходник — полный путь исходного HDF5/LFS либо открытой картинки на диске данных.
PNG для разметки — фактическое изображение из подготовленного локального набора.
Результат JSON — точный путь текущей аннотации; файл появится при сохранении.
Последний экспорт — папка последнего выполненного экспорта этого набора.
Копировать — скопировать соответствующий полный путь в буфер обмена.
Открыть папку — открыть расположение соответствующего файла в Проводнике.
Поля доступны для выделения и копирования, но не меняют расположение файлов.

ИМПОРТ И ЭКСПОРТ

Каталог… — открыть библиотеку подготовленных партий на диске N. Поиск работает
по станции, типу и дате. Выберите строку и нажмите Открыть набор либо дважды
щёлкните по ней. Пилот с уже принятой разметкой хранится отдельной первой партией.

Открыть папку… — выбрать готовый набор с manifest.json или папку обычных PNG,
JPEG, BMP, TIFF. Для обычных изображений затем выберите место рабочей папки:
в ней создаются копии PNG, manifest.json и отдельные аннотации. Исходники
сохраняются. Читаются файлы выбранной папки, без вложенных каталогов; максимум
1000 изображений в одной партии. Ошибки чтения записываются в manifest.json.
Соседние JSON LabelMe с тем же именем автоматически импортируются как черновики,
если размеры и классы поддерживаются. Прежние исходные JSON не меняются.
У обычных картинок нет числовой оси: координаты и кластеризация в пикселях.
Если PNG содержит подписи и поля, выделите инструментом Область сам график.

Сохранить набор как… — выбрать место новой копии всего рабочего набора:
изображения, аннотации, история, настройки. Программа переключится на копию.
Так можно сменить рабочий путь результатов. Существующие наборы не заменяются.

АВТОМАТИЧЕСКАЯ ПРЕДВАРИТЕЛЬНАЯ РАЗМЕТКА

Авторазметка… — открыть параметры кластеризации.
Авто (DBSCAN) — количество групп определяется плотностью точек; одиночные
точки могут быть отнесены к шуму. Вручную (K-means) — задайте число групп
в поле Число, от 1 до 30. Это число пространственных кластеров, не число
физических мод. Перед K-means отсеиваются неплотные шумовые точки. После фильтра
минимального размера кластеров может стать меньше. Группы показаны разными
цветами, подпись K1/K2 и т.д. наносится один раз на группу. Один кластер может
состоять из нескольких разорванных полигонов; это не дополнительные кластеры.

Порог — выделяет сильные точки матрицы. Для измерений это дБ исходного
загрузчика; для обычных картинок — яркость 0–255, без физического смысла SNR.
На цветных PNG серые/белые поля исключаются из признака яркости. Качество
такой обработки нужно проверять, особенно для непривычной цветовой палитры.

Связь по частоте / дальности задаёт масштаб расстояний DBSCAN в МГц и км.
Для картинок без осей масштабы заданы в пикселях x/y. K-means использует
эти же масштабы признаков. Минимум соседей относится только к DBSCAN.
Минимум точек и минимальная полоса/ширина отсекают маленькие группы и узкие
вертикальные помехи. Слабые полезные следы тоже могут отсеяться — подбирайте порог.

Только видимая область ограничивает расчёт текущим приближением; без отметки
обрабатывается вся исходная матрица. Положение границ берётся до начала расчёта.
Найти кластеры — запустить расчёт в фоне; интерфейс остаётся доступным.
При переходе к другому кадру результаты прежнего расчёта отбрасываются.
Закрыть параметры закрывает только окно настройки, расчёт продолжается.

Оранжевые кандидаты K1, K2 и т.д. ещё не являются масками и не экспортируются.
Добавить кластеры — добавить их как Signal к существующим объектам. Прежние
маски сохраняются. Разметка получает статус ожидания и требует проверки.
Части одного кластера получают общую группу. Границы расширены на один исходный
пиксель для редактирования тонких следов. Между ветвями не следует заполнять фон.
Скрыть кандидаты убирает предпросмотр, не удаляя существующую разметку.

Затем удалите помехи, поправьте вершины или перенесите маски и назначьте
классы 1F, 2F, 1E, E и т.д. Соприкасающиеся моды могут попасть в один кластер,
а разорванная мода — в несколько. Для разделения уменьшите расстояния связи
либо удалите неверный полигон и нарисуйте правильные части. Для объединения
задайте общую группу. Физические метки алгоритм сам не устанавливает.

Импорт разметки LabelMe… — выбрать JSON кандидата для текущего PNG и указать
его автора или название модели. Размеры и имя изображения должны совпадать,
координаты — исходные пиксели PNG с началом в левом верхнем углу. Только полигоны.
Импорт заменяет текущие объекты, сохраняя прежнюю версию, и всегда возвращает
случай в ожидание экспертной проверки. Нормализованные координаты и рамки
предварительно преобразуют в согласованный формат.

Экспорт принятых… — выбрать родительскую папку. В ней создаётся новая папка
accepted_<дата-время> с принятыми PNG, JSON LabelMe, NPZ с числовыми осями
и манифестом. Существующий экспорт не перезаписывается. Разделение train,
validation, test сохраняется. Тестовые данные нельзя использовать как примеры
для настройки локальной модели. Экспорт сам по себе модель не обучает.

Справка — открыть это описание. Закрыть справку — закрыть только окно помощи.
Правила разметки — открыть окно с короткими правилами отличия E, 1F, 2F и 3F и
примерами кадров: верная лестница мод и типичная ошибка со сдвигом лестницы.
Язык — выбрать русский или английский язык интерфейса, справки и руководства.
Обычное закрытие главного окна сохраняет текущие правки; незавершённый полигон
потребует завершить или отменить.
"""

HELP_TEXT_EN = """REVIEWING IONOGRAMS

Create project from H5… — choose a folder of H5/LFS soundings (subfolders included),
then a destination folder. A separate project is created: PNG in images, NPZ
matrices with physical axes in arrays, annotations in annotations. The project
opens automatically. Unsuitable files are skipped and their reasons are written
to manifest.json. Cancel stops after the current file and keeps the finished part.
Source files are never changed. Reopen the project later with Open folder….

Top bar: the File menu holds Open folder… (Ctrl+O), Catalog…, Save pack as…,
Import LabelMe annotations… and Export accepted…. Catalog… opens the list of
packs; there you can also choose Open another folder…. The Language menu
switches the interface, this help and the guide between Russian and English;
the choice is remembered in the pack settings. Labeling guide opens the rules
with example frames; Help is this description of every button. You may pick a
whole dataset or a nested images/annotations folder of a ready pack: the program
finds its manifest.json. An archive that holds only JSON has no images: to view it
you need the full pack with manifest.json, images, arrays and annotations.
The bar next to the title shows the share of accepted cases. All paths ▾ reveals
the measurement and last-export paths; the PNG and result JSON are always visible.
In packs for blind manual review, automatic hints and their import are switched
off by the pack setting; the task states whether clustering is allowed.

A labelling counts as reviewed only after the expert explicitly accepts it. Viewing,
zooming, panning and contrast changes never alter object coordinates or status.
Editing the geometry of an accepted mask returns the case to pending.

TOOLS ABOVE THE PLOT

Select / vertices - pick an object in the list or click inside a polygon. A selected
object shows white vertices: drag them with the left mouse button. Dragging inside
a mask moves it as a whole, keeping its shape. A mask never leaves the image.
Move the whole group when dragging moves every polygon with the same non-empty
group_id. One move is undone with Undo / Ctrl+Z. A plain click without a move does
not change the acceptance status.

Multi-select - drag a frame around several masks or candidates. Outlines that
intersect the frame are chosen. Ctrl or Shift adds the frame to the current
selection. In select mode Ctrl/Shift + click adds or removes one outline. The
Objects list also supports Ctrl and Shift. Ctrl+A on the plot selects everything.

After a selection a label menu appears right on the plot. Press 1F, 2F, E, Es,
1E, 3F, Signal or Interference: all selected polygons get that label in one
action. Selected candidates are added as editable labelling; the others stay in
preview. Whole group widens the selection to every part of the chosen group/cluster.
Clear selection removes the highlight and the menu. A right click on a selection
opens the menu again; while drawing a polygon it closes the polygon as before.
The menu changes no label until a class button is pressed.

Polygon - draw a new object of the current class. Each click adds a vertex. Unfinished
white lines are not yet a saved mask.

Zoom area - zoom to a rectangle. Press and drag with the left button around the
region you need. After release the program shows it and returns to the select tool.
The labelling does not change.

Close polygon - finish a polygon of at least three points. Alternatives: Enter with
the plot focused, or the right mouse button. The points must enclose the band of the
visible echo.

Remove point - delete the last vertex of an unclosed polygon. May be pressed
repeatedly. Alternatives: Backspace on the plot and Ctrl+Z while drawing. Finished
polygons are not deleted by this button. With no unfinished points the button is disabled.

Masks - show or hide the labelling overlay to inspect the raw signal.

ZOOM AND RANGE

Whole frame - show the entire stored frequency and range span.

Around masks - zoom to the selected polygon with margins. With nothing selected, show
all useful-signal masks. With no masks use Zoom area or enter range limits by hand.

+ / − - zoom in or out around the centre of the plot.

Range, km - lower and upper limits of the display. Show applies them; Enter in
either field does the same. A decimal point or comma is accepted. For example
2700-2800 km. A window outside the measured span is not applied.

Range list - presets 1000-5000, 1500-2000, 2000-2500, 2500-3000, 2700-3100,
3000-3500, 3500-4000, 4500-5000 km. A choice changes only the range and keeps the
current frequency span. The numeric fields show the applied limits.

Wheel over the plot - zoom near the cursor. Shift + wheel changes only the range.
The middle mouse button with dragging pans the view. Panels, buttons and fonts stay
in place while the plot zooms. Zooming shows the original pixels without smoothing
and adds no measurement resolution.

dB scale - two sliders for the colour scale limits. Only the display changes.
Opacity - the fill intensity of masks; outlines stay visible.
Colors - "Modes": the ionogram in greys, E/Es/1E orange, 1F blue, 2F green, other
labels grey dashed; "Turbo": the previous palette.
Captions - class names to the left of the masks.
The frequency and range under the cursor are shown at the right below the plot.

LEFT PANEL

Ionograms - the list of cases and their statuses. A choice opens the case. Edits to the
previous one are saved on navigation. The scrollbar and the wheel over a free area of
the form scroll the form; over a list they scroll the list itself.
At start the last saved case opens; if there is none, the first pending ionogram is chosen.

Expert - the name of the person accepting the current labelling. It is a record of
the reviewer, not an electronic signature. Without a name acceptance is unavailable.

Objects - polygons of the current image. Class, vertex count and group are shown.
Choosing an object highlights it on the plot. Signal is a useful signal without an
established physical mode. 1E, 1F, 2F and Interference are also available.

Change class - give all selected objects the class from the drop-down list. Only the
selection changes. To give a class to a whole group, first press Whole group in the
plot menu. If a chosen part of a group gets another class, the program splits it into
a new group and keeps the labels of the other parts.
E, Es and 3F are also available. Agree on the meaning of E and 1E before training so that
one physical class does not get two different labels.

Delete - delete every selected polygon or reject the selected candidates.
Alternative: Delete on the plot. The action can be undone with Undo or Ctrl+Z.

Group… - set a shared number for separate polygons of one mode instance. The same
number means parts of one object. 0 removes grouping. Different physical modes must
not be merged merely because they share the class Signal.

Undo - undo the last change of geometry, class or group. While drawing, it first removes
the last unfinished point. Alternative: Ctrl+Z. After moving to another image the undo
memory is cleared; earlier saved versions stay in the history folder.

No useful signal - an explicit negative labelling. Needed to accept a case without signal
masks. Incompatible with signal polygons.

Expert note - the explanation of the review. A comment is required for needs-changes and
ambiguous. The classes of physical modes and disputed areas are confirmed by the expert.
An assistant or model draft is never a reference by itself.

DECISIONS AND SAVING

Accept and next - save the labelling with status accepted and open the next case. Needs
the expert name and signal masks or an explicit mark of their absence.
Alternative: Ctrl+Enter. Only accepted cases reach the export.

Needs changes, next - status changes, a comment is required.
Ambiguous, next - status ambiguous, a comment is required.
Both decisions save the record and move on; they do not reach the export.

← Back / Next → - move between ionograms without accepting. Existing edits are saved.
An unclosed polygon must be finished or cancelled.

Save - write the current changes and stay on the image. Alternative: Ctrl+S. Polygons,
name, comment and the current status are saved. Measurement files do not change.
The previous saved version goes to history. A version conflict between two windows
working at once never silently overwrites someone else's edits.

Esc - cancel the whole unfinished polygon or zoom frame. To remove only one point use
Backspace or Remove point.

PATHS AT THE BOTTOM OF THE WINDOW

Source - the full path of the source HDF5/LFS or of an opened picture on the data disk.
PNG for labeling - the actual image from the prepared local pack.
Result JSON - the exact path of the current annotation; the file appears on saving.
Last export - the folder of the last export of this pack.
Copy - copy the corresponding full path to the clipboard.
Open folder - open the location of the corresponding file in Explorer.
The fields can be selected and copied but do not change where files live.

IMPORT AND EXPORT

Catalog… - open the library of prepared batches on disk N. Search works by station,
type and date. Choose a row and press Open pack, or double-click it. The pilot with
already accepted labelling is kept as a separate first batch.

Open folder… - choose a ready pack with manifest.json or a folder of ordinary PNG,
JPEG, BMP, TIFF files. For ordinary images then choose the place of the working folder:
it receives copies of the PNG files, manifest.json and separate annotations. The
originals are kept. Files of the chosen folder are read, without nested folders; at
most 1000 images per batch. Read errors are written to manifest.json.
Neighbouring LabelMe JSON files with the same name are imported automatically as
drafts if sizes and classes are supported. The original JSON files do not change.
Ordinary pictures have no numeric axis: coordinates and clustering are in pixels.
If a PNG contains captions and margins, select the plot itself with Zoom area.

Save pack as… - choose the place for a new copy of the whole working pack: images,
annotations, history, settings. The program switches to the copy. This is how to change
the working path of the results. Existing packs are not replaced.

AUTOMATIC PRELIMINARY LABELLING

Auto-label… - open the clustering parameters.
Auto (DBSCAN) - the number of groups follows the density of points; single points may be
treated as noise. Manual (K-means) - set the number of groups in the Count field, from 1
to 30. This is the number of spatial clusters, not of physical modes. Before K-means the
sparse noise points are dropped. After the minimum-size filter there may be fewer
clusters. Groups are shown in different colours, the caption K1/K2 etc. is drawn once per
group. One cluster may consist of several broken polygons; those are not extra clusters.

Threshold - selects the strong points of the matrix. For measurements it is the dB of the
source loader; for ordinary pictures it is brightness 0-255, without SNR meaning.
On colour PNG files grey/white margins are excluded from the brightness feature. The
quality of such processing must be checked, especially for an unfamiliar colour palette.

Link along frequency / range sets the DBSCAN distance scale in MHz and km. For pictures
without axes the scales are pixels x/y. K-means uses the same feature scales. The
minimum of neighbours applies to DBSCAN only. Minimum points and minimum bandwidth/width
cut off small groups and narrow vertical interference. Weak useful traces may drop out
as well - tune the threshold.

Visible area only limits the computation to the current zoom; without the tick the whole
source matrix is processed. The limits are taken before the computation starts.
Find clusters - start the computation in the background; the interface stays usable.
On moving to another frame the results of the earlier computation are discarded.
Close parameters closes only the settings window; the computation continues.

Orange candidates K1, K2 etc. are not masks yet and are not exported.
Add clusters - add them as Signal to the existing objects. Earlier masks are kept.
The labelling becomes pending and needs review. Parts of one cluster get a shared group.
Boundaries are widened by one source pixel to edit thin traces. Do not fill the
background between branches.
Hide candidates removes the preview without deleting the existing labelling.

Then delete interference, correct vertices or move masks and assign the classes 1F, 2F,
1E, E and so on. Touching modes may land in one cluster, a broken mode in several.
To separate them reduce the link distances or delete the wrong polygon and draw the right
parts. To merge, set a shared group. The algorithm never sets physical labels itself.

Import LabelMe annotations… - choose a candidate JSON for the current PNG and give its
author or model name. Sizes and the image name must match, coordinates are source PNG
pixels with the origin at the top left corner. Polygons only. The import replaces the
current objects, keeps the earlier version, and always returns the case to pending expert
review. Normalised coordinates and boxes are converted to the agreed format first.

Export accepted… - choose a parent folder. It gets a new folder accepted_<date-time> with
the accepted PNG files, LabelMe JSON, NPZ with numeric axes and the manifest. An existing
export is never overwritten. The train, validation and test split is kept. Test data must
not be used as examples for tuning a local model. The export itself does not train a model.

Help - open this description. Close help - close only the help window.
Labeling guide - open the rules for telling E, 1F, 2F and 3F apart, with example frames:
a correct mode ladder and the typical error of a shifted ladder.
Language - choose Russian or English for the interface, the help and the guide.
Closing the main window normally saves the current edits; an unfinished polygon must be
finished or cancelled first.
"""
