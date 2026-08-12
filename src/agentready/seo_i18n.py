"""Russian localization for scanner-generated SEO texts.

Check ``details``, recommendation ``action`` and remediation ``summary`` strings
are produced in English by the check implementations. This module translates
them for Russian reports using per-check phrase maps and regex patterns with
dynamic values. English reports keep the original strings.
"""
from __future__ import annotations

import re
from typing import Any

from .i18n import normalize_language

# Remediation summaries / recommendation actions per check id.
_SUMMARIES_RU: dict[str, str] = {
    "page-available": "Убедитесь, что публичный URL отдаёт HTML с HTTP 200 без блокировки CDN, WAF или авторизацией.",
    "page-metadata": "Добавьте уникальный информативный title, meta description и один понятный H1.",
    "page-indexability": "Уберите случайные директивы noindex и оставьте страницу публично доступной для обхода.",
    "canonical": "Опубликуйте один canonical link, совпадающий с выбранным публичным URL, если нет осознанной стратегии дублей.",
    "robots-sitemap": "Опубликуйте корректный robots.txt и обнаруживаемую XML-карту сайта.",
    "favicon": "Добавьте доступный favicon через link rel=\"icon\" и проверьте его HTTP-ответ.",
    "jsonld": "Исправьте синтаксис JSON-LD и проверьте итоговые структурированные данные.",
    "title-length": "Держите title в диапазоне 30–60 символов, чтобы он не обрезался и не был расплывчатым в выдаче.",
    "description-length": "Напишите meta description длиной 70–160 символов, обобщающее ценность страницы.",
    "multiple-metadata": "Оставьте ровно один <title> и один meta description; дубли путают поисковые системы.",
    "metadata-collisions": "Разведите title, H1 и meta description: title — для сниппета, H1 — заголовок страницы, description — краткое описание.",
    "metadata-special-chars": "Уберите эмодзи и декоративные спецсимволы из title и meta description — в выдаче они могут быть удалены или искажены.",
    "image-alt": "Добавьте описательные alt-атрибуты контентным изображениям; пустой alt оставляйте только декоративным.",
    "mixed-content": "Загружайте все изображения, скрипты и стили по HTTPS; браузеры блокируют или помечают смешанный контент.",
    "https-scheme": "Отдавайте сайт по HTTPS с валидным сертификатом; HTTPS — базовый сигнал безопасности и ранжирования.",
    "url-format": "Используйте короткие URL в нижнем регистре без процентного кодирования; избегайте смешанного регистра и лишних параметров.",
    "meta-refresh": "Замените meta refresh на серверный 301-редирект; meta refresh медленнее и ослабляет ссылочные сигналы.",
    "insecure-links": "Обновите ссылки на HTTPS-версии; ссылки со страниц HTTPS на HTTP ослабляют сигналы безопасности.",
    "content-size": "Публикуйте содержательный текст, держите HTML лёгким и поддерживайте здоровое соотношение текста к разметке.",
    "response-time": "Сократите время ответа сервера ниже ~800 мс за счёт кэширования, быстрого бэкенда и CDN.",
    "content-quality": "Замените заглушки lorem ipsum реальным контентом и удалите Flash — оба являются негативными сигналами качества.",
    "microdata": "Добавьте структурированную разметку Schema.org (предпочтительно JSON-LD), описывающую сущность страницы.",
    "hreflang": "Исправьте аннотации hreflang: валидные ISO-коды, абсолютные URL, без дублей, со ссылкой на текущую страницу.",
    "broken-links": "Исправьте или удалите ссылки на страницы с 4xx/5xx, чтобы краулеры не упирались в тупики.",
    "redirect-chains": "Ведите ссылки сразу на финальные URL; многошаговые цепочки редиректов тратят краул-бюджет и размывают сигналы.",
    "duplicate-metadata": "Дайте каждой индексируемой странице уникальные title и meta description, чтобы страницы не конкурировали между собой.",
    "internal-nofollow": "Уберите rel=nofollow с внутренних ссылок, если нет осознанной причины политики обхода.",
    "link-counts": "Разбейте страницы с избыточным числом ссылок; очень длинные списки ссылок размывают ценность каждой ссылки и удобство.",
    "insecure-links-pages": "Обновите HTTP-ссылки на всех обойдённых проблемных страницах до HTTPS-версий.",
    "ga-no-traffic": "Страница не получает измеряемого трафика; оцените её ценность, внутреннюю перелинковку и индексируемость.",
    "ga-bounce-rate": "Разберитесь, почему большинство визитов завершается отказом: несоответствие контента намерению, медленная загрузка или слабая перелинковка.",
    "crawl-coverage": "Увеличьте лимит обхода или устраните ошибки загрузки, чтобы покрытие сайта было полным.",
    "ga-nonindexed-traffic": "Примите осознанное решение: индексировать страницу или скрыть её; трафик на noindex-страницу — сигнал смешанных намерений.",
    "gsc-no-clicks": "Улучшите сниппет (title/description) и позиции по запросам с показами без кликов.",
    "gsc-no-impressions": "Страница невидима в поиске; проверьте индексируемость, внутренние ссылки и покрытие sitemap.",
    "gsc-nonindexed-impressions": "Страница с noindex всё ещё получает показы; приведите директиву индексирования в соответствие с намерением.",
}

# Detail-string translations: (regex, replacement template) evaluated in order.
_DETAIL_PATTERNS_RU: list[tuple[str, Any]] = [
    (r"^page is not HTTP 200 HTML$", "страница не является HTML с HTTP 200"),
    (r"^Crawl classified as partial_limit; fetched (\d+) URL\(s\)\.$", lambda m: f"обход частичный: достигнут лимит страниц; загружено URL: {m.group(1)}"),
    (r"^Crawl classified as partial_error; fetched (\d+) URL\(s\)\.$", lambda m: f"обход частичный: ошибки загрузки; загружено URL: {m.group(1)}"),
    (r"^Crawl classified as complete_within_scope; fetched (\d+) URL\(s\)\.$", lambda m: f"обход завершён в пределах области; загружено URL: {m.group(1)}"),
    (r"^selected page returned HTTP 200 HTML$", "выбранная страница вернула HTTP 200 HTML"),
    (r"^HTTP (\d+)$", lambda m: f"HTTP {m.group(1)}"),
    (r"^expected HTML content type, got (.+)$", lambda m: f"ожидался HTML Content-Type, получено: {m.group(1)}"),
    (r"^missing title$", "отсутствует title"),
    (r"^missing meta description$", "отсутствует meta description"),
    (r"^expected one H1, found (\d+)$", lambda m: f"ожидался один H1, найдено: {m.group(1)}"),
    (r"^title, meta description and exactly one H1 are present$", "title, meta description и ровно один H1 присутствуют"),
    (r"^noindex directive detected$", "обнаружена директива noindex"),
    (r"^no noindex directive detected$", "директива noindex не обнаружена"),
    (r"^one canonical matches the selected URL$", "один canonical совпадает с выбранным URL"),
    (r"^canonical is missing, duplicated or points elsewhere$", "canonical отсутствует, дублируется или указывает на другой адрес"),
    (r"^robots\.txt and a valid XML sitemap are available$", "robots.txt и корректная XML-карта сайта доступны"),
    (r"^robots\.txt must be HTTP 200 with User-agent and a valid XML sitemap must be discoverable$", "robots.txt должен отдавать HTTP 200 с User-agent, а корректная XML-карта сайта должна быть обнаруживаемой"),
    (r"^favicon is reachable$", "favicon доступен"),
    (r"^favicon was not found$", "favicon не найден"),
    (r"^no JSON-LD blocks found; structured data is optional and depends on page type$", "блоки JSON-LD не найдены; структурированные данные опциональны и зависят от типа страницы"),
    (r"^(\d+) invalid JSON-LD block\(s\)$", lambda m: f"некорректных блоков JSON-LD: {m.group(1)}"),
    (r"^valid JSON-LD found \((.+)\)$", lambda m: f"найден корректный JSON-LD ({m.group(1)})"),
    (r"^title length is (\d+) chars$", lambda m: f"длина title: {m.group(1)} символов"),
    (r"^title is too short \((\d+) chars; recommended 30-60\)$", lambda m: f"title слишком короткий ({m.group(1)} символов; рекомендуется 30–60)"),
    (r"^title is too long \((\d+) chars; recommended 30-60\)$", lambda m: f"title слишком длинный ({m.group(1)} символов; рекомендуется 30–60)"),
    (r"^meta description length is (\d+) chars$", lambda m: f"длина meta description: {m.group(1)} символов"),
    (r"^meta description is too short \((\d+) chars; recommended 70-160\)$", lambda m: f"meta description слишком короткое ({m.group(1)} символов; рекомендуется 70–160)"),
    (r"^meta description is too long \((\d+) chars; recommended 70-160\)$", lambda m: f"meta description слишком длинное ({m.group(1)} символов; рекомендуется 70–160)"),
    (r"^exactly one title and one meta description tag$", "ровно один title и один meta description"),
    (r"^multiple (\d+) title tags and (\d+) meta description tags found$", lambda m: f"найдено дублей: title — {m.group(1)}, meta description — {m.group(2)}"),
    (r"^multiple (.+)$", lambda m: f"обнаружено несколько: {m.group(1)}"),
    (r"^title is identical to H1$", "title совпадает с H1"),
    (r"^title is identical to meta description$", "title совпадает с meta description"),
    (r"^title, H1 and description are distinct$", "title, H1 и description различны"),
    (r"^emoji/special symbols in title$", "эмодзи/спецсимволы в title"),
    (r"^emoji/special symbols in meta description$", "эмодзи/спецсимволы в meta description"),
    (r"^no emoji or unusual special characters in metadata$", "эмодзи и необычные спецсимволы в метаданных отсутствуют"),
    (r"^all (\d+) images have alt text$", lambda m: f"все изображения ({m.group(1)}) имеют alt-текст"),
    (r"^(\d+) of (\d+) images missing alt text$", lambda m: f"у {m.group(1)} из {m.group(2)} изображений нет alt-текста"),
    (r"^no images on the page$", "на странице нет изображений"),
    (r"^all subresources use HTTPS$", "все подресурсы используют HTTPS"),
    (r"^(\d+) insecure http:// subresource\(s\), e\.g\. (.+)$", lambda m: f"небезопасных http:// подресурсов: {m.group(1)}, например {m.group(2)}"),
    (r"^page is not served over HTTPS$", "страница не отдаётся по HTTPS"),
    (r"^page is served over HTTPS$", "страница отдаётся по HTTPS"),
    (r"^URL contains uppercase letters$", "URL содержит заглавные буквы"),
    (r"^URL is very long \((\d+) chars\)$", lambda m: f"URL очень длинный ({m.group(1)} символов)"),
    (r"^URL contains percent-encoded characters$", "URL содержит процентное кодирование"),
    (r"^URL format is clean \(lowercase, reasonable length, no encoding\)$", "формат URL чистый (нижний регистр, разумная длина, без кодирования)"),
    (r"^no meta refresh redirect$", "meta refresh редирект отсутствует"),
    (r"^meta refresh found: (.+)$", lambda m: f"найден meta refresh: {m.group(1)}"),
    (r"^no HTTPS→HTTP links$", "ссылок HTTPS → HTTP нет"),
    (r"^(\d+) link\(s\) point from HTTPS to HTTP, e\.g\. (.+)$", lambda m: f"ссылок с HTTPS на HTTP: {m.group(1)}, например {m.group(2)}"),
    (r"^page is not served over HTTPS$", "страница не отдаётся по HTTPS"),
    (r"^very little text content \((\d+) chars\)$", lambda m: f"очень мало текстового контента ({m.group(1)} символов)"),
    (r"^HTML is very large \((\d+) KB\)$", lambda m: f"HTML очень большой ({m.group(1)} КБ)"),
    (r"^low text/HTML ratio \(([\d.]+%)\)$", lambda m: f"низкое соотношение текста к HTML ({m.group(1)})"),
    (r"^content size, HTML weight and text ratio are reasonable$", "объём контента, вес HTML и доля текста в норме"),
    (r"^server responded in (\d+) ms$", lambda m: f"сервер ответил за {m.group(1)} мс"),
    (r"^server responded in (\d+) ms \(above (\d+) ms\)$", lambda m: f"сервер ответил за {m.group(1)} мс (выше порога {m.group(2)} мс)"),
    (r"^lorem ipsum placeholder text found$", "найден текст-заглушка lorem ipsum"),
    (r"^Flash content \(object/embed\) found$", "найден Flash-контент (object/embed)"),
    (r"^no placeholder text or legacy Flash content$", "текстов-заглушек и устаревшего Flash-контента нет"),
    (r"^structured markup present \(microdata itemscope and/or JSON-LD\)$", "структурированная разметка присутствует (microdata itemscope и/или JSON-LD)"),
    (r"^no microdata or JSON-LD structured markup found$", "микроразметка и JSON-LD не найдены"),
    (r"^no hreflang annotations \(single-language page\)$", "аннотации hreflang отсутствуют (одноязычная страница)"),
    (r"^valid hreflang set with (\d+) annotation\(s\)$", lambda m: f"корректный набор hreflang: аннотаций — {m.group(1)}"),
    (r"^invalid language code\(s\): (.+)$", lambda m: f"некорректные коды языков: {m.group(1)}"),
    (r"^duplicate language codes$", "дублирующиеся коды языков"),
    (r"^(\d+) relative hreflang link\(s\)$", lambda m: f"относительных ссылок hreflang: {m.group(1)}"),
    (r"^no hreflang link to the current URL$", "нет hreflang-ссылки на текущий URL"),
    (r"^all (\d+) crawled pages are reachable$", lambda m: f"все обойдённые страницы ({m.group(1)}) доступны"),
    (r"^(\d+) broken page\(s\): (.+)$", lambda m: f"битых страниц: {m.group(1)}: {m.group(2)}"),
    (r"^no multi-hop redirect chains$", "многошаговых цепочек редиректов нет"),
    (r"^(\d+) page\(s\) reached via redirect chains: (.+)$", lambda m: f"страниц достигнуто через цепочки редиректов: {m.group(1)}: {m.group(2)}"),
    (r"^titles and descriptions are unique across crawled pages$", "title и description уникальны среди обойдённых страниц"),
    (r"^(\d+) duplicate title\(s\) across pages$", lambda m: f"дублирующихся title между страницами: {m.group(1)}"),
    (r"^(\d+) duplicate meta description\(s\) across pages$", lambda m: f"дублирующихся meta description между страницами: {m.group(1)}"),
    (r"^no internal nofollow links$", "внутренних nofollow-ссылок нет"),
    (r"^(\d+) internal nofollow link\(s\) on (\d+) page\(s\)$", lambda m: f"внутренних nofollow-ссылок: {m.group(1)} на страницах: {m.group(2)}"),
    (r"^no page exceeds (\d+) links$", lambda m: f"ни одна страница не превышает {m.group(1)} ссылок"),
    (r"^(\d+) page\(s\) with many links: (.+)$", lambda m: f"страниц с большим числом ссылок: {m.group(1)}: {m.group(2)}"),
    (r"^no insecure HTTP links across (\d+) crawled pages$", lambda m: f"небезопасных HTTP-ссылок среди обойдённых страниц ({m.group(1)}) нет"),
    (r"^(\d+) page\(s\) with insecure HTTP links: (.+)$", lambda m: f"страниц с небезопасными HTTP-ссылками: {m.group(1)}: {m.group(2)}"),
    (r"^no GA4 sessions recorded for this page in the last 28 days$", "за последние 28 дней у страницы нет сеансов GA4"),
    (r"^page has recorded GA4 sessions$", "у страницы есть зафиксированные сеансы GA4"),
    (r"^GA4 bounce rate is (\d+)%$", lambda m: f"показатель отказов GA4: {m.group(1)}%"),
    (r"^GA4 bounce rate is (\d+)% \(above (\d+)%\)$", lambda m: f"показатель отказов GA4: {m.group(1)}% (выше {m.group(2)}%)"),
    (r"^page has recorded clicks in Search Console$", "у страницы есть клики в Search Console"),
    (r"^page has impressions but zero clicks \((\d+) impressions\)$", lambda m: f"у страницы есть показы, но ноль кликов (показов: {m.group(1)})"),
    (r"^page has impressions in Search Console$", "у страницы есть показы в Search Console"),
    (r"^page has no impressions in the last 28 days$", "у страницы нет показов за последние 28 дней"),
    (r"^page is indexable$", "страница индексируема"),
    (r"^page is not indexable but still receives traffic$", "страница не индексируема, но всё ещё получает трафик"),
    (r"^page is not indexable and receives no traffic$", "страница не индексируема и не получает трафик"),
    (r"^page is not indexable but still receives impressions$", "страница не индексируема, но всё ещё получает показы"),
    (r"^page is not indexable and has no impressions$", "страница не индексируема и не получает показы"),
    (r"^GA4 property not configured$", "GA4 property не настроен"),
    (r"^Search Console site not configured$", "сайт Search Console не настроен"),
    (r"^no GA4 data for this page$", "нет данных GA4 для этой страницы"),
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


def seo_detail(text: str, lang: str) -> str:
    """Translate a scanner-generated SEO detail string for Russian reports."""
    if normalize_language(lang) != "ru":
        return text
    if re.search(r"(?:timed out|timeout|connection|certificate|DNS|SSL|TLS|refused|unreachable)", text, re.IGNORECASE):
        return "сетевая/протокольная ошибка: " + text
    return _translate_detail(text)


def seo_summary(check_id: str, fallback: str, lang: str) -> str:
    """Return the localized remediation summary / recommendation action."""
    if normalize_language(lang) != "ru":
        return fallback
    return _SUMMARIES_RU.get(check_id, fallback)
