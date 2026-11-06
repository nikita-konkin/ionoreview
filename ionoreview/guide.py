"""Labeling guide window: short mode-ladder rules with example ionograms, in both interface languages."""
from __future__ import annotations

from pathlib import Path
import tkinter as tk
from tkinter import ttk

from PIL import Image, ImageTk

from .theme import MUTED, SURFACE, TEXT

ASSETS = Path(__file__).resolve().parent / "assets" / "guide"

GUIDE = {
    "ru": (
        ("h", "Правила разметки мод"),
        ("p", "Метка обозначает физический тип отражения, а не положение следа в кадре. Сначала найдите "
              "полосу E, затем след 1F с носиком и только потом следующие моды. Цвета в режиме «Моды»: "
              "E / Es / 1E — оранжевый, 1F — синий, 2F — зелёный, остальные метки — серый пунктир."),
        ("h", "1. E-семейство (1E / E / Es)"),
        ("p", "Плоский широкополосный след с наименьшей групповой дальностью. На трассах chirp NIC1–NIC3 он лежит "
              "на 2640–2670 км и может тянуться до 25–30 МГц. Носика у него нет."),
        ("h", "2. Мода 1F"),
        ("p", "Первая F-мода выше E: след с носиком — местом, где нижний и верхний лучи смыкаются на MUF. "
              "По нашему соглашению низкая плоская часть на 2690–2710 км тоже относится к 1F."),
        ("img", "nose_and_e.png", "T031, NIC1. Оранжевым — полоса E (1E) на 2640–2670 км. Синим — 1F с носиком "
                                  "около 22 МГц. Серый пунктир — Interference."),
        ("h", "3. Моды 2F и 3F"),
        ("p", "Следующие моды. С номером скачка групповая дальность растёт, а MUF падает: MUF(1F) > MUF(2F) > MUF(3F)."),
        ("h", "4. Нижний след не обязательно 1F"),
        ("p", "Сначала проверьте, не плоский ли это след E. Типичная ошибка — E, названная 1F. Тогда вся лестница "
              "сдвигается: настоящая 1F получает метку 2F, а 2F — метку 3F."),
        ("img", "ladder_shifted.png", "Ошибка. Q030, NIC3, исходная разметка: плоский след E назван 1F, "
                                      "настоящая 1F — 2F, а 2F — 3F."),
        ("img", "ladder_correct.png", "Верно. Тот же кадр после исправления: 1E — плоский след, 1F — след "
                                      "с носиком, 2F — следующая мода выше."),
        ("h", "5. Одна маска — одна мода"),
        ("p", "Маска не должна охватывать одновременно полосу E и след 1F. Если она захватила обе, разделите её на две."),
        ("h", "6. Помехи, неясный сигнал, неясные кадры"),
        ("p", "Interference — вертикальные линии узкополосных станций и другие неионосферные отметки. "
              "Signal — только для действительно неясного сигнала. Если кадр нельзя разметить уверенно, "
              "поставьте статус «Неоднозначно» и напишите комментарий."),
        ("img", "reference.png", "S101, NIC3, принятая разметка: 1E, 1F с носиком и отметки Interference левее носика."),
        ("h", "7. Особые случаи"),
        ("p", "NIC0: полоса E лежит выше, около 2690–2710 км. Кадры из файлов lfm v2 (17, 18 и 24 октября): "
              "шкала дальности не откалибрована, поэтому судите по относительной лестнице мод, а не по абсолютным километрам."),
    ),
    "en": (
        ("h", "Mode labeling rules"),
        ("p", "A label names the physical type of reflection, not the position of a trace in the frame. First find "
              "the E band, then the 1F trace with its nose, and only then the higher modes. Colors in the “Modes” "
              "scheme: E / Es / 1E orange, 1F blue, 2F green, other labels grey dashed."),
        ("h", "1. E family (1E / E / Es)"),
        ("p", "A flat, wide-band trace with the smallest group range. On the chirp paths NIC1–NIC3 it lies at about "
              "2640–2670 km and can extend up to 25–30 MHz. It has no nose."),
        ("h", "2. The 1F mode"),
        ("p", "The first F mode above E: the trace with a nose, where the lower and upper rays meet at the MUF. "
              "By our convention the low flat part at about 2690–2710 km also belongs to 1F."),
        ("img", "nose_and_e.png", "T031, NIC1. Orange: the E band (1E) at 2640–2670 km. Blue: 1F with its nose "
                                  "near 22 MHz. Grey dashes: Interference."),
        ("h", "3. The 2F and 3F modes"),
        ("p", "The next modes. With the hop number the group range grows and the MUF falls: MUF(1F) > MUF(2F) > MUF(3F)."),
        ("h", "4. The lowest trace is not automatically 1F"),
        ("p", "First check whether it is the flat E trace. A typical error is E labelled as 1F. That shifts the whole "
              "ladder: the real 1F gets 2F, and the real 2F gets 3F."),
        ("img", "ladder_shifted.png", "Wrong. Q030, NIC3, original labels: the flat E trace is called 1F, "
                                      "the real 1F is 2F, and the real 2F is 3F."),
        ("img", "ladder_correct.png", "Right. The same frame after correction: 1E is the flat trace, 1F the trace "
                                      "with the nose, 2F the next mode above."),
        ("h", "5. One mask, one mode"),
        ("p", "A mask must not span both the E band and the 1F trace. If it does, split it into two."),
        ("h", "6. Interference, unclear signal, unclear frames"),
        ("p", "Interference: vertical lines from narrow-band stations and other non-ionospheric marks. "
              "Signal: only for genuinely unclear signal. If a frame cannot be labelled with confidence, "
              "set the status “Ambiguous” and write a comment."),
        ("img", "reference.png", "S101, NIC3, accepted labels: 1E, 1F with its nose, and Interference marks left of the nose."),
        ("h", "7. Special cases"),
        ("p", "NIC0: its E band is higher, at about 2690–2710 km. Frames from lfm v2 files (17, 18 and 24 October): "
              "the range axis is uncalibrated, so judge by the relative ladder of modes, not by absolute kilometres."),
    ),
}


def images(code):
    return [block[1] for block in GUIDE[code] if block[0] == "img"]


class Guide:
    """Scrollable window that shows the rules of the chosen language and can switch language while open."""

    def __init__(self, root, code, place):
        self.window = tk.Toplevel(root)
        self.window.minsize(560, 420)
        self.window.transient(root)
        place(self.window, 880, 740)
        self.pictures = []
        scroll = ttk.Scrollbar(self.window, orient="vertical")
        scroll.pack(side="right", fill="y")
        self.text = tk.Text(self.window, wrap="word", padx=22, pady=16, bg=SURFACE, fg=TEXT, relief="flat",
                            highlightthickness=0, cursor="arrow", yscrollcommand=scroll.set)
        self.text.pack(fill="both", expand=True)
        scroll.config(command=self.text.yview)
        self.text.tag_configure("h", font=("Segoe UI", 13, "bold"), spacing1=16, spacing3=5)
        self.text.tag_configure("p", font=("Segoe UI", 11), spacing3=6)
        self.text.tag_configure("cap", font=("Segoe UI", 9), foreground=MUTED, spacing1=3, spacing3=12)
        self.text.tag_configure("pic", spacing1=8, lmargin1=0)
        self.render(code)

    def exists(self):
        return bool(self.window.winfo_exists())

    def lift(self):
        self.window.lift()

    def render(self, code):
        self.window.title("Правила разметки — ИоноРазметка" if code == "ru" else "Labeling guide — IonoReview")
        self.pictures = []
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        for block in GUIDE[code]:
            if block[0] == "img":
                picture = ImageTk.PhotoImage(Image.open(ASSETS / block[1]))
                self.pictures.append(picture)
                self.text.image_create("end", image=picture)
                self.text.insert("end", "\n", "pic")
                self.text.insert("end", block[2] + "\n", "cap")
            else:
                self.text.insert("end", block[1] + "\n", block[0])
        self.text.configure(state="disabled")
        self.text.yview_moveto(0)
