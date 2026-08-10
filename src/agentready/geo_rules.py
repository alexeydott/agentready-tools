from __future__ import annotations

from pathlib import Path


def rules_template(language: str = "ru") -> str:
    if language == "en":
        return """# AI Search / GEO project rules

These rules are project policy for humans and coding agents. They do not claim to be ranking factors.

## Before changes
- Produce a plan and list every file that will be changed before mass edits.
- Preserve the current canonical URL policy and existing security controls.

## Crawl and indexing
- Keep important public pages HTTP 200 and indexable; do not add `noindex` accidentally.
- Maintain one authoritative canonical URL per page.
- Keep `robots.txt` and `sitemap.xml` valid.
- Explicitly decide policy for OAI-SearchBot, ChatGPT-User, GPTBot, Claude-SearchBot, Claude-User, ClaudeBot, PerplexityBot, Perplexity-User and Google-Extended.
- Treat Google-Extended as a robots-only product policy token. Google documents no separate HTTP request User-Agent, so do not fabricate a live probe or expect it in access logs.
- A robots allow is not proof of access: verify WAF/CDN/server behaviour and inspect real crawler logs.

## Structured data
- For articles use Article/TechArticle/BlogPosting with headline, datePublished, dateModified, mainEntityOfPage and author.
- Link entities through stable `@id` values; link author to a Person entity.
- Person should use `sameAs` for real profiles where appropriate.
- Add BreadcrumbList for navigational structure.
- Add FAQPage only for genuine visible questions and answers; never manufacture FAQ solely for markup.
- Parse/validate JSON-LD after every change.

## Dates
- `datePublished` is immutable after initial publication unless correcting a factual mistake.
- Change `dateModified` only when meaningful page content changes, not for layout/meta-only changes.
- Show publication/update dates visibly in the page in addition to structured data.
- Use Git history as a verification reference, not as an excuse to fabricate freshness.

## Citation-ready content
- Prefer concrete facts, numbers, limits, versions, prices, dates and conditions over vague claims.
- Include complete commands/code where the command itself answers the user.
- Use comparison tables when a structured comparison is genuinely useful.
- Make important paragraphs understandable when quoted out of context.
- Put the direct answer before the explanation when the query has a direct answer.
- Cover the user's intent, but do not stuff keywords or mass-generate thin pages.

## IndexNow publication workflow
1. Deploy the updated page and the IndexNow key file first.
2. Verify the public key file.
3. Preview the list of changed URLs.
4. Use the global endpoint by default or select Yandex explicitly; do not combine a named provider with a custom endpoint.
5. A non-root keyLocation authorizes only URLs under its directory.
6. Submit only verified URLs after deployment.
7. Treat HTTP 200/202 as receipt/acceptance, not a guarantee of indexing or ranking.

## Google Indexing API
- Use only for JobPosting or BroadcastEvent embedded in VideoObject; it is not a general URL-submission API.
- Assign no Google Cloud project IAM role to the service account; add it as a delegated owner of the matching Search Console property.
- Use google-auth with the indexing-only OAuth scope; never log or commit credentials.
- Preview URL_UPDATED eligibility before explicit submission. For URL_DELETED, require an explicit supported-type assertion because the page may already be gone.
- Treat HTTP 200 and notification metadata as submission history, not proof of crawl or indexing.

## Verification commands
```bash
agentready scan https://example.com/page/ --preset ai-search
agentready scan https://example.com/page/ --preset ai-search --lang ru --format html -o geo-report.html
agentready indexnow verify https://example.com YOUR_KEY
agentready indexnow git --repo . --base-url https://example.com --content-root site --from-ref HEAD~1 --to-ref HEAD
agentready google-indexing publish https://example.com/jobs/42
agentready logs ai-bots /var/log/nginx/access.log
```

## Explicit non-goals
- `llms.txt` may be kept as an agent/content directory, but do not treat it as a proven GEO ranking lever.
- Schema.org reduces ambiguity; do not describe it as an automatic ranking multiplier.
- Do not optimize keyword density.
- Do not generate large numbers of low-value pages merely to target query variants.
"""
    return """# Правила проекта для AI-поиска / GEO

Эти правила — политика проекта для людей и coding agents. Они не объявляются факторами ранжирования.

## Перед изменениями
- Перед массовыми правками сначала составить план и перечислить все изменяемые файлы.
- Сохранять принятую политику canonical URL и существующие меры безопасности.

## Краулинг и индексирование
- Важные публичные страницы должны возвращать HTTP 200 и не получать `noindex` случайно.
- На странице должен быть один авторитетный canonical URL.
- Поддерживать корректные `robots.txt` и `sitemap.xml`.
- Явно определить политику для OAI-SearchBot, ChatGPT-User, GPTBot, Claude-SearchBot, Claude-User, ClaudeBot, PerplexityBot, Perplexity-User и Google-Extended.
- Считать Google-Extended robots-only токеном политики продукта. По документации Google у него нет отдельного HTTP User-Agent, поэтому не создавать фиктивную live-проверку и не ожидать его в access logs.
- Разрешение в robots.txt не доказывает фактический доступ: проверять WAF/CDN/веб-сервер и реальные журналы запросов краулеров.

## Структурированные данные
- Для статей использовать Article/TechArticle/BlogPosting с headline, datePublished, dateModified, mainEntityOfPage и author.
- Связывать сущности стабильными `@id`; автора связывать с сущностью Person.
- Для Person по возможности указывать `sameAs` на реальные профили.
- Добавлять BreadcrumbList для структуры навигации.
- FAQPage применять только к реальным видимым вопросам и ответам; не придумывать FAQ ради разметки.
- После каждой правки парсить и валидировать JSON-LD.

## Даты
- `datePublished` после публикации не менять, кроме исправления фактической ошибки.
- `dateModified` менять только при содержательном изменении страницы, а не при правках вёрстки или метаданных.
- Даты публикации/обновления должны быть видны пользователю, а не находиться только в structured data.
- Git-историю использовать как проверяемый ориентир, а не как оправдание искусственной «свежести».

## Цитируемый контент
- Предпочитать конкретные факты, числа, лимиты, версии, цены, даты и условия расплывчатым формулировкам.
- Если ответом служит команда или код — приводить их полностью.
- Использовать таблицы, когда сравнение действительно полезно.
- Важные абзацы должны сохранять смысл, если их вырвать из окружающего контекста.
- Для вопроса с прямым ответом сначала давать ответ, затем объяснение.
- Закрывать интент пользователя, но не заниматься keyword stuffing и массовой генерацией пустых страниц.

## Публикация через IndexNow
1. Сначала развернуть обновлённую страницу и файл ключа IndexNow.
2. Проверить публичную доступность файла ключа.
3. Просмотреть список изменённых URL до отправки.
4. По умолчанию использовать глобальный endpoint либо явно выбрать Yandex; не сочетать именованный provider с custom endpoint.
5. Нерутовый keyLocation разрешает только URL внутри своей директории.
6. После деплоя отправлять только проверенные URL.
7. HTTP 200/202 означает приём уведомления, а не гарантию индексации или позиции.

## Google Indexing API
- Использовать только для JobPosting или BroadcastEvent внутри VideoObject; это не API для отправки произвольных URL.
- Не назначать сервисному аккаунту IAM-роль проекта Google Cloud; добавить его delegated owner соответствующего ресурса Search Console.
- Использовать google-auth с OAuth scope только для indexing; не логировать и не коммитить credentials.
- Перед явной отправкой URL_UPDATED проверять eligibility. Для URL_DELETED требовать явное указание поддерживаемого типа, поскольку страница уже может отсутствовать.
- Считать HTTP 200 и notification metadata историей отправки, а не доказательством обхода или индексации.

## Команды проверки
```bash
agentready scan https://example.com/page/ --preset ai-search --lang ru
agentready scan https://example.com/page/ --preset ai-search --lang ru --format html -o geo-report.html
agentready indexnow verify https://example.com YOUR_KEY
agentready indexnow git --repo . --base-url https://example.com --content-root site --from-ref HEAD~1 --to-ref HEAD
agentready google-indexing publish https://example.com/jobs/42
agentready logs ai-bots /var/log/nginx/access.log
```

## Что не считать целью
- `llms.txt` можно держать как каталог для агентов, но не считать доказанным рычагом GEO-ранжирования.
- Schema.org уменьшает неоднозначность; не описывать разметку как автоматический множитель позиций.
- Не оптимизировать «плотность ключей».
- Не создавать массово малополезные страницы только ради вариантов запросов.
"""


def write_rules(path: str | Path, *, language: str = "ru", overwrite: bool = False) -> Path:
    p = Path(path)
    if p.exists() and not overwrite:
        raise ValueError(f"rules file already exists: {p}")
    p.write_text(rules_template(language), encoding="utf-8")
    return p
