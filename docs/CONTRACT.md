# Контракт между частями проекта

Пайплайн (`pipeline/`) пишет файлы в `out/`. Экран (`viewer/`) и ассистент (`app/`) только читают их.
Если нужно новое поле, попросите Амирлана: поле добавит Claude в пайплайн.

## out/graph.json (главный файл для экрана и ассистента)
Все gid строки. Все суммы в тенге (KZT), числа с плавающей точкой.

```json
{
  "meta": {
    "generated_at": "2026-09-23T14:00:00",
    "n_nodes": 2248, "n_edges": 3119, "n_tx": 4840, "n_seed": 81,
    "period": "2026-07-01..2026-07-31", "turnover_kzt": 365890012.01
  },
  "roles": [
    {"key": "consolidator", "label": "Точка консолидации", "color": "#d62728",
     "rule": "человекочитаемое правило с порогами"}
  ],
  "nodes": [
    {
      "id": "100000003684369100",
      "role": "consolidator",
      "role_score": 0.87,
      "cluster_id": 3,
      "priority_score": 0.91,
      "rank": 1,
      "is_seed": true,
      "depth": 0,
      "in_deg": 24, "out_deg": 62,
      "in_kzt": 3848436.0, "out_kzt": 8588655.0,
      "in_tx": 30, "out_tx": 80,
      "pass_through": 2.23,
      "seeds_upstream": 5,
      "evidence": "короткое обоснование роли с числами, до 200 символов",
      "why": "обоснование приоритета (у узлов из топа), иначе пустая строка",
      "flags": ["cutoff_depth4", "fast_transit", "sync_inflow", "cycle", "isolated_seed"],
      "x": 12.3, "y": -4.5
    }
  ],
  "edges": [
    {"source": "100000003684369100", "target": "100000003037660100",
     "sum_kzt": 53000.0, "n_tx": 1, "depth": 1}
  ],
  "clusters": [
    {"cluster_id": 3, "n_nodes": 120, "n_seed": 7, "sum_kzt_internal": 12345678.0,
     "top_gids": ["...", "..."], "hypothesis": "гипотеза о назначении кластера"}
  ],
  "top": [
    {"rank": 1, "gid": "100000003684369100", "role": "consolidator",
     "priority_score": 0.91, "why": "обоснование"}
  ]
}
```

Поля `rank` и `why` есть у всех узлов: `rank` равен null, если узла нет в топе.
Поле `flags` всегда список (может быть пустым). `x`, `y` посчитаны заранее (seed=42), физику в браузере не включать.

## CSV (схема из ТЗ, лишние колонки разрешены)
- `out/nodes_roles.csv`: gid, role, role_score, cluster_id, priority_score, evidence (+ служебные метрики)
- `out/clusters.csv`: cluster_id, n_nodes, n_seed, sum_kzt_internal, top_gids, hypothesis
- `out/top_nodes.csv`: rank, gid, role, priority_score, why

## Экран (Напарник 1)
- `viewer/build.py` содержит функцию `build_viewer(graph_json: Path, out_html: Path) -> None`.
  Она собирает ОДИН самодостаточный файл `out/viewer.html`: внутри JS из `viewer/vendor/`, CSS и данные.
  Файл открывается двойным щелчком, без сервера и без интернета.
- Запуск отдельно: `python -m viewer.build --graph out/graph.json --out out/viewer.html`.
- Пайплайн вызывает `build_viewer` в конце. Если экран упал, пайплайн всё равно пишет CSV.
- Ссылка на узел: `viewer.html#gid=<gid>` открывает схему с выделенным узлом и его связями.

## Ассистент (Напарник 2)
- `app/main.py` (FastAPI) читает `out/graph.json` при старте (путь из env `GRAPH_JSON`, по умолчанию `out/graph.json`).
- `POST /api/ask` принимает `{"question": "..."}`, отдаёт
  `{"answer": "...", "gids": ["..."], "tools": ["..."], "meta": {...}}`.
- `GET /api/node/{gid}`: узел, его входящие и исходящие связи. `GET /viewer`: отдаёт `out/viewer.html`.
- Без API-ключа ассистент не падает: отвечает на типовые вопросы правилами или честно пишет, что LLM выключен.
