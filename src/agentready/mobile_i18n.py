"""Russian localization for scanner-generated mobile-friendliness texts.

Mirrors ``seo_i18n``: check ``details`` and remediation summaries are produced
in English by the check implementations and translated here for Russian
reports. English reports keep the original strings.
"""
from __future__ import annotations

import re
from typing import Any

from .i18n import normalize_language

_SUMMARIES_RU: dict[str, str] = {
    "viewport-meta": 'Добавьте <meta name="viewport" content="width=device-width, initial-scale=1"> в <head> страницы.',
    "responsive-css": "Используйте медиа-запросы, относительные единицы (rem/em/%/vw) и flex/grid-макеты вместо фиксированной ширины в px.",
    "fixed-width-elements": "Избегайте фиксированной ширины в px у изображений и табличной вёрстки; используйте max-width:100% и адаптивные таблицы.",
    "touch-targets": "Обеспечьте размер мишеней касания не менее 48×48 CSS px и отступы не менее 8 px между соседними элементами.",
    "font-readability": "Задайте базовый размер шрифта не менее 16 CSS px и разрешите масштабирование (без user-scalable=no и maximum-scale=1).",
    "mobile-indexability": "Уберите директивы noindex/none, чтобы страница могла индексироваться для мобильного поиска.",
    "rendered-layout-overflow": "Исправьте контент шире мобильного viewport, чтобы не требовалась горизонтальная прокрутка.",
    "rendered-tap-targets": "Увеличьте размер мишеней касания минимум до 48×48 CSS px и добавьте отступы между соседними элементами.",
    "rendered-font-readability": "Задайте базовый шрифт не менее 16 CSS px и разрешите пользовательское масштабирование.",
}

_DETAIL_PATTERNS_RU: list[tuple[str, Any]] = [
    (r"^viewport meta declares width=device-width and initial-scale$", "viewport meta объявляет width=device-width и initial-scale"),
    (r"^viewport meta missing or incomplete \(need width=device-width and initial-scale\)$", "viewport meta отсутствует или неполный (нужны width=device-width и initial-scale)"),
    (r"^responsive CSS signals found \(media queries, relative units/flex/grid\)$", "найдены сигналы адаптивного CSS (медиа-запросы, относительные единицы/flex/grid)"),
    (r"^no clear responsive CSS signals \(media queries, relative units, flex/grid\) detected$", "явных сигналов адаптивного CSS (медиа-запросы, относительные единицы, flex/grid) не найдено"),
    (r"^no obvious fixed-width/table layout issues$", "явных проблем фиксированной ширины/табличной вёрстки нет"),
    (r"^(\d+) image\(s\) with fixed width attributes$", lambda m: f"изображений с фиксированной шириной: {m.group(1)}"),
    (r"^(\d+) table\(s\) detected \(tables often force horizontal scrolling\)$", lambda m: f"обнаружено таблиц: {m.group(1)} (таблицы часто вызывают горизонтальную прокрутку)"),
    (r"^(\d+) interactive elements detected; keep spacing and size adequate for touch$", lambda m: f"интерактивных элементов: {m.group(1)}; обеспечьте достаточные размер и отступы для касания"),
    (r"^no interactive elements detected$", "интерактивные элементы не обнаружены"),
    (r"^inline/style font-size below 12px detected$", "обнаружен font-size ниже 12px в style/inline-стилях"),
    (r"^viewport disables user scaling$", "viewport запрещает масштабирование пользователем"),
    (r"^font sizes appear readable and user scaling is allowed$", "размеры шрифта читаемы, масштабирование разрешено"),
    (r"^no mobile-blocking robots directives detected$", "блокирующих мобильную индексацию директив robots не обнаружено"),
    (r"^noindex/none directive detected$", "обнаружена директива noindex/none"),
    (r"^no horizontal overflow at (\d+)px viewport \(scrollWidth=(\d+)\)$", lambda m: f"нет горизонтального переполнения при viewport {m.group(1)}px (scrollWidth={m.group(2)})"),
    (r"^horizontal overflow at (\d+)px viewport: scrollWidth=(\d+) > clientWidth=(\d+)$", lambda m: f"горизонтальное переполнение при viewport {m.group(1)}px: scrollWidth={m.group(2)} > clientWidth={m.group(3)}"),
    (r"^(\d+) tap targets, (\d+) below 48px$", lambda m: f"мишеней касания: {m.group(1)}, меньше 48px: {m.group(2)}"),
    (r"^(\d+) tap targets sized adequately$", lambda m: f"мишеней касания с достаточным размером: {m.group(1)}"),
    (r"^no interactive elements rendered$", "интерактивные элементы не отрисованы"),
    (r"^computed body font size (\d+)px is below 16px$", lambda m: f"вычисленный размер шрифта {m.group(1)}px ниже 16px"),
    (r"^viewport blocks user scaling$", "viewport блокирует масштабирование пользователем"),
    (r"^computed font size is readable and user scaling is allowed$", "вычисленный размер шрифта читаем, масштабирование разрешено"),
    (r"^playwright not installed$", "Playwright не установлен"),
]


def _translate_detail(text: str) -> str:
    parts = [part.strip() for part in text.split("; ")]

    def _translate(part: str) -> str:
        for pattern, replacement in _DETAIL_PATTERNS_RU:
            match = re.match(pattern, part)
            if match:
                return replacement(match) if callable(replacement) else replacement
        return part

    whole = _translate(text.strip())
    if whole != text.strip():
        return whole
    return "; ".join(_translate(part) for part in parts)


def mobile_detail(text: str, lang: str) -> str:
    """Translate a scanner-generated mobile detail string for Russian reports."""
    if normalize_language(lang) != "ru":
        return text
    if re.search(r"(?:timed out|timeout|connection|certificate|DNS|SSL|TLS|refused|unreachable)", text, re.I):
        return "сетевая/протокольная ошибка: " + text
    return _translate_detail(text)


def mobile_summary(check_id: str, fallback: str, lang: str) -> str:
    """Return the localized remediation summary / recommendation action."""
    if normalize_language(lang) != "ru":
        return fallback
    return _SUMMARIES_RU.get(check_id, fallback)
