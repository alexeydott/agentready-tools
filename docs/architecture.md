# Архитектура AgentReady Tools

## Назначение

AgentReady Tools — пакетный Python-аудитор сайтов с несколькими тонкими
точками входа: CLI, опциональным FastAPI-сервером, MCP-фасадом и локальным
dashboard. Все эти поверхности используют общие модели, правила проверок и
ограничения безопасности; транспортный слой не дублирует логику аудита.

## Слои и границы

```text
CLI / FastAPI / MCP / Dashboard
              |
   scanner / seo_scanner / mobile_scanner / AuditService / jobs_v2
              |
 checks, crawler, discovery, page_parser, protocols, seo/
              |
 Fetcher + EgressPolicy + target/http + config + security
              |
 report, report_v2, *_report, i18n, exports, agentfindings
```

- **Транспорт:** `cli.py`, `server.py`, `mcp_server.py` и browser dashboard
  проверяют входные данные и вызывают прикладные сервисы. В них не размещаются
  правила проверок и сетевые обходы.
- **Прикладная оркестрация:** `scanner.py`, `seo_scanner.py`,
  `mobile_scanner.py`, `audit_service.py` и `jobs_v2.py` координируют bounded
  выполнение, профили, жизненный цикл запуска и формирование проекций.
- **Домен проверок:** `checks.py`, `protocols/`, `seo/`, `mobile_checks.py`,
  `interaction.py` и связанные модели создают типизированные факты и findings.
- **Сбор данных и безопасность:** `Fetcher`, `EgressPolicy`, `target.py`,
  `http.py`, `crawler.py`, `discovery.py`, `robots.py` и `sitemap.py` задают
  ограничения URL, времени, размера ответа, редиректов и области обхода.
- **Представление:** `report.py`, `report_v2.py`, SEO/mobile-рендереры,
  `i18n.py`, `exports.py` и `agentfindings.py` преобразуют результаты в
  локализованные отчёты и машинные проекции, не выполняя аудит заново.

## Потоки выполнения v2

1. Точка входа валидирует URL, профиль и ограничения.
2. `AuditService` компилирует bounded-план и создаёт `AuditRunContext`.
3. `Fetcher` и `EgressPolicy` получают только разрешённые публичные ресурсы;
   crawler ведёт frontier, coverage и `run_id`.
4. Парсеры и доменные правила создают типизированные evidence/findings.
5. `report_v2.py` формирует каноническую проекцию с coverage, fingerprints,
   diff/export и совместимыми идентификаторами.
6. `QueryService` предоставляет bounded-инвентарь страниц, ссылок, ресурсов,
   findings и метрик; произвольные SQL-запросы наружу не выдаются.

Provider enrichment uses the same `MetricRecord` and `QueryService` path. A
provider job may add timestamped observed metrics or an unavailable state, but
it never enters the core score calculation. The dashboard, CLI inventory
command, HTTP inventory endpoint, and MCP `run_inventory_v2` are thin adapters
over this one projection.

v2 — единственный публичный контракт. Новые режимы добавляются по шаблону
`*_models`, `*_checks`, `*_scoring`, `*_report`, `*_scanner` с тонкими
CLI/FastAPI/MCP-адаптерами. Product v1 routes, schemas и baseline adapters не
поддерживаются и не должны получать новую функциональность.

## Dashboard и AI

Dashboard — локальный browser-клиент. Он получает локализованный отчёт через
API, строит bounded AI-контекст из результата и передаёт его в AI assistant
вместе с явно выбранными skills/MCP-инструментами. Prompt library, chat
состояние и выбор инструментов относятся к runtime-данным и не импортируются
ядром аудита. Секреты хранятся в OS vault; в browser storage восстанавливаются
только несекретные настройки и redacted metadata.

## Правила изменений

- Новую проверку размещать в доменном модуле и покрывать типизированными
  тестами; транспортные адаптеры должны только подключать её.
- Сетевой код использовать только через общие bounded Fetcher/EgressPolicy;
  не добавлять независимые HTTP-вызовы в report/dashboard/MCP.
- Новые публичные форматы фиксировать в v2 contract manifest, документации и
  regression-тестах; не добавлять v1 aliases.
- Не смешивать локализованный текст с машинными идентификаторами findings.
- Не включать `.ai-factory`, `.agents`, `.codex`, `AGENTS.md` и другие AI-
  context-файлы в исходные публикации или удалённые коммиты.

Подробнее о командах сборки и проверках см. [Development](development.md), о
контрактах и форматах — [Reporting](reporting.md) и [Integrations](integrations.md).
