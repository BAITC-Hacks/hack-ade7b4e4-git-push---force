"""Аналитическая справка: один самодостаточный HTML для аналитика и руководителя (печатается в PDF из браузера).

Итог сценария ТЗ: «перечень клиентов на углублённую проверку и запрос в правоохранительные органы».
Все числа берутся из результатов пайплайна, ничего не зашито.
"""
from __future__ import annotations

import html
from datetime import datetime
from pathlib import Path

import pandas as pd

from . import config as C
from .fmt import kzt, plural

CSS = """
*{box-sizing:border-box}body{margin:0;background:#f4f6f8;color:#1f2933;font:14px/1.5 system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif}
.page{max-width:1080px;margin:24px auto;background:#fff;padding:32px 40px;border-radius:12px;box-shadow:0 1px 3px rgba(0,0,0,.08)}
h1{font-size:24px;margin:0 0 4px}h2{font-size:18px;margin:28px 0 10px;padding-top:12px;border-top:1px solid #e4e7eb}
.sub{color:#616e7c;font-size:13px}.warn{background:#fff8e6;border:1px solid #f5d98b;border-radius:8px;padding:8px 12px;margin:14px 0;font-size:13px}
.kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:18px 0}.kpi{background:#f5f7fa;border-radius:10px;padding:12px 14px}
.kpi b{display:block;font-size:26px;line-height:1.2;color:#0f5132}.kpi span{font-size:12.5px;color:#52606d}
.flow{display:flex;align-items:stretch;gap:8px;margin:10px 0 4px;flex-wrap:wrap}.flow div{flex:1;min-width:150px;background:#eef6f1;border:1px solid #cfe5d8;border-radius:8px;padding:8px 10px;font-size:12.5px}
.flow div b{display:block;font-size:13px;margin-bottom:2px}.arrow{flex:0 0 auto!important;min-width:0!important;background:none!important;border:0!important;align-self:center;font-size:18px;color:#7b8794}
ul.key{margin:8px 0 0 18px;padding:0}ul.key li{margin:4px 0}
table{width:100%;border-collapse:collapse;font-size:12.5px}th{text-align:left;background:#f5f7fa;padding:6px 8px;font-weight:600;border-bottom:1px solid #d9e2ec}
td{padding:6px 8px;border-bottom:1px solid #eef2f7;vertical-align:top}td.n{text-align:right;white-space:nowrap}
.gid{font-family:ui-monospace,Consolas,monospace;font-size:12px;color:#1d4ed8;text-decoration:none;white-space:nowrap}
.role{display:inline-block;padding:1px 8px;border-radius:10px;color:#fff;font-size:11.5px;white-space:nowrap}
.muted{color:#7b8794;font-size:12px}footer{margin-top:28px;color:#7b8794;font-size:12px}
@media (max-width:700px){.page{margin:0;border-radius:0;padding:20px 16px}.kpis{grid-template-columns:repeat(2,minmax(0,1fr))}table{display:block;overflow-x:auto}.flow .arrow{display:none!important}}
@media print{body{background:#fff}.page{box-shadow:none;margin:0;max-width:none;padding:0 8mm}h2{break-after:avoid}tr{break-inside:avoid}}
"""


def _int(n: int) -> str:
    return f"{n:,}".replace(",", " ")


def _pct1(x: float) -> str:
    return f"{x * 100:.1f}".replace(".", ",") + "%"


def _period(p) -> str:
    """'2026-07-01..2026-07-31' -> 'с 01.07.2026 по 31.07.2026'; иначе как есть."""
    try:
        a, b = str(p).split("..")
        return (f"с {datetime.strptime(a, '%Y-%m-%d').strftime('%d.%m.%Y')} "
                f"по {datetime.strptime(b, '%Y-%m-%d').strftime('%d.%m.%Y')}")
    except ValueError:
        return str(p)


def _e(x) -> str:
    return html.escape(str(x))


def _gid(g) -> str:
    return f'<a class="gid" href="viewer.html#gid={_e(g)}">{_e(g)}</a>'


def _role(key: str) -> str:
    return f'<span class="role" style="background:{C.ROLE_COLOR[key]}">{_e(C.ROLE_LABEL[key])}</span>'


def _reasons(why: str) -> str:
    """Из why оставляем обоснование роли и причины места в топе, без повтора названия роли."""
    parts = why.split(". ", 1)
    return parts[1] if len(parts) > 1 else why


def build_report(df: pd.DataFrame, clusters: pd.DataFrame, top: pd.DataFrame, resilience: pd.DataFrame,
                 sensitivity: pd.DataFrame, requests: pd.DataFrame, meta: dict, out_path: Path) -> dict:
    n_seed, n_nodes = meta["n_seed"], meta["n_nodes"]
    roles = df["role"].value_counts()
    multi = clusters[(clusters["cluster_id"] != 0) & (clusters["n_seed"] > 1)].sort_values("max_priority", ascending=False)
    cut = int(df["cutoff"].sum())
    first = top.iloc[0]
    r1 = df.loc[first["gid"]]
    res = resilience[resilience["strategy"] == "priority"].set_index("removed_top_n")
    base_lcc = int(res["largest_component_before"].iloc[0])
    r20 = res.loc[20] if 20 in res.index else res.iloc[-1]
    overlap_min = int(round(float(sensitivity["top20_overlap"].min()) * 100))
    core = int(roles.get("coordinator", 0)), int(roles.get("consolidator", 0))

    kpis = [
        (f"{n_seed}", "известных участников на входе (seed)"),
        (_int(n_nodes), "клиентов в сети: роль, кластер и приоритет у каждого"),
        (f"{len(top)}", "клиентов в топе на проверку, у каждого обоснование"),
        (kzt(meta["turnover_kzt"]), "оборот сети за период"),
    ]
    key_points = [
        f"Ядро сети: {core[0]} {plural(core[0], 'координатор', 'координатора', 'координаторов')} и {core[1]} "
        f"{plural(core[1], 'точка', 'точки', 'точек')} консолидации. Первым проверять {_gid(first['gid'])}. "
        f"{_e(r1['evidence'])}",
        f"{len(multi)} {plural(len(multi), 'группа объединяет', 'группы объединяют', 'групп объединяют')} 2+ известных участника: "
        f"это кандидаты в организованные группы, их гипотезы ниже.",
        f"Проверка и блокировка топ-20 затрагивает {_pct1(float(r20['turnover_share_touched']))} оборота сети, "
        f"крупнейшая связная часть сокращается с {_int(base_lcc)} до {_int(int(r20['largest_component']))} клиентов.",
        f"На границе выборки (4-е колено) {_int(cut)} {plural(cut, 'клиент', 'клиента', 'клиентов')}: их не считаем "
        f"конечными получателями, по ним нужен запрос исходящих.",
        f"Список устойчив: если сдвинуть любой порог ролей на шаг, топ-20 сохраняется не меньше чем на {overlap_min}%.",
    ]

    top_rows = "".join(
        f"<tr><td class='n'>{int(t['rank'])}</td><td>{_gid(t['gid'])}</td><td>{_role(t['role'])}</td>"
        f"<td class='n'>{float(t['priority_score']):.2f}</td><td>{_e(_reasons(t['why']))}</td></tr>"
        for _, t in top.head(15).iterrows())
    cl_rows = "".join(
        f"<tr><td class='n'>{int(c['cluster_id'])}</td><td class='n'>{int(c['n_nodes'])}</td><td class='n'>{int(c['n_seed'])}</td>"
        f"<td class='n'>{_e(kzt(float(c['sum_kzt_internal'])))}</td>"
        f"<td>{' '.join(_gid(g) for g in str(c['top_gids']).split(';')[:3])}</td><td>{_e(c['hypothesis'])}</td></tr>"
        for _, c in multi.iterrows())
    req = requests.drop_duplicates(["gid", "gap"])
    req_rows = "".join(
        f"<tr><td>{_e(g)}</td><td>{_e(grp['request'].iloc[0])}</td>"
        f"<td>{' '.join(_gid(x) for x in grp['gid'].head(5))}</td><td class='n'>{len(grp)}</td></tr>"
        for g, grp in req.groupby("gap", sort=False))
    rules = C.role_rules()
    role_rows = "".join(
        f"<tr><td>{_role(k)}</td><td class='n'>{int(roles.get(k, 0))}</td><td>{_e(rules[k])}</td></tr>" for k in C.ROLES)

    page = f"""<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Аналитическая справка: граф денег</title><style>{CSS}</style></head><body><div class="page">
<h1>Аналитическая справка по сети переводов</h1>
<div class="sub">Период {_e(_period(meta['period']))} · {n_seed} seed, {_int(meta['n_edges'])} {plural(meta['n_edges'], 'связь', 'связи', 'связей')}, {_int(meta['n_tx'])} {plural(meta['n_tx'], 'транзакция', 'транзакции', 'транзакций')} ·
сформировано {datetime.now().strftime('%d.%m.%Y %H:%M')} командой <code>python -m pipeline</code></div>
<div class="warn">Роли и приоритеты являются <b>гипотезами для проверки</b>, а не выводами о виновности. Данные: только
исходящие внутрибанковские переводы от 5 000 ₸ на 4 колена, без атрибутов клиентов.</div>
<div class="kpis">{''.join(f'<div class="kpi"><b>{_e(v)}</b><span>{_e(t)}</span></div>' for v, t in kpis)}</div>
<div class="flow"><div><b>Данные</b>3 parquet: связи, узлы, транзакции</div><div class="arrow">→</div>
<div><b>Метрики</b>вход и выход, суммы, пропуск, seed выше по потоку, посредничество, время, циклы</div><div class="arrow">→</div>
<div><b>Роли и приоритет</b>6 ролей по правилам с порогами, кластеры Louvain, приоритет 0..1</div><div class="arrow">→</div>
<div><b>Результат</b>3 CSV, схема сети, эта справка, AI-ассистент</div></div>
<h2>Главное</h2><ul class="key">{''.join(f'<li>{p}</li>' for p in key_points)}</ul>
<h2>Кого проверять первым</h2>
<table><tr><th>№</th><th>gid</th><th>Роль</th><th>Приоритет</th><th>Почему</th></tr>{top_rows}</table>
<p class="muted">Полный список: top_nodes.csv (топ-{len(top)}) и nodes_roles.csv (все {_int(n_nodes)} клиентов). Клик по gid открывает клиента на схеме сети.</p>
<h2>Группы с несколькими известными участниками</h2>
<table><tr><th>Кластер</th><th>Клиентов</th><th>Seed</th><th>Оборот внутри</th><th>Ключевые клиенты</th><th>Гипотеза</th></tr>{cl_rows}</table>
<h2>Какие данные запросить дальше</h2>
<table><tr><th>Пробел в данных</th><th>Запрос</th><th>Клиенты (первые 5)</th><th>Всего</th></tr>{req_rows}</table>
<p class="muted">Подробно по каждому клиенту: next_requests.csv.</p>
<h2>Роли и правила</h2>
<table><tr><th>Роль</th><th>Клиентов</th><th>Правило (проверяется сверху вниз)</th></tr>{role_rows}</table>
<h2>Ограничения</h2><ul class="key">
<li>Видны только исходящие переводы от seed на 4 колена: входящие извне выборки и полный баланс клиента не известны.</li>
<li>Переводы меньше 5 000 ₸, межбанковские, наличные и криптовалюта не видны.</li>
<li>Разметки ролей нет: правила экспертные, их устойчивость проверена сдвигом порогов (sensitivity.csv).</li>
<li>Для клиентов 4-го колена оценка «пересылает дальше» статистическая, по похожим клиентам 1-3 колена.</li></ul>
<footer>Граф денег · HackAlem AI, кейс Freedom · команда git push --force. Воспроизведение: <code>python -m pipeline --data data --out out</code>.</footer>
</div></body></html>"""
    Path(out_path).write_text(page, encoding="utf-8")
    return {
        "top1": str(first["gid"]),
        "n_groups": int(len(multi)),
        "share20": _pct1(float(r20["turnover_share_touched"])),
        "lcc_before": _int(base_lcc),
        "lcc_after": _int(int(r20["largest_component"])),
        "overlap": overlap_min,
        "cutoff": cut,
    }


INDEX_CSS = """
*{box-sizing:border-box}body{margin:0;background:#f4f6f8;color:#1f2933;font:15px/1.55 system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif}
.w{max-width:840px;margin:40px auto;background:#fff;border-radius:12px;padding:32px 36px;box-shadow:0 1px 3px rgba(0,0,0,.08)}
h1{margin:0 0 6px;font-size:26px;line-height:1.25}h2{font-size:17px;margin:26px 0 6px}.sub{color:#616e7c;font-size:14px}
.kpis{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin:20px 0}.kpi{background:#f5f7fa;border-radius:10px;padding:12px 14px}
.kpi b{display:block;font-size:26px;line-height:1.2;color:#0f5132}.kpi span{display:block;font-size:12.5px;line-height:1.4;color:#52606d}
.btns{display:flex;gap:12px;margin:22px 0;flex-wrap:wrap}
.btn{display:inline-block;padding:12px 18px;border-radius:8px;background:#146c43;color:#fff;text-decoration:none;font-weight:600}
.btn.alt{background:#e8f3ec;color:#0f5132}ul{padding-left:18px;margin:6px 0}li{margin:7px 0}a{color:#1d4ed8}
code{background:#f5f7fa;padding:1px 5px;border-radius:4px;font-size:13px}
.gid{font-family:ui-monospace,Consolas,monospace;font-size:13px;text-decoration:none;white-space:nowrap}
.warn{background:#fff8e6;border:1px solid #f5d98b;border-radius:8px;padding:8px 12px;font-size:13px;margin-top:18px}
@media (max-width:640px){.w{margin:0;border-radius:0;padding:22px 16px}.kpis{grid-template-columns:repeat(2,minmax(0,1fr))}h1{font-size:22px}}
"""


def build_index(meta: dict, n_top: int, out_path: Path, facts: dict | None = None) -> None:
    """Главная страница демо. Цифры берутся из результатов пайплайна (facts возвращает build_report)."""
    f = facts or {}
    kpis = [(_int(meta["n_nodes"]), "клиентов в сети: у каждого роль, кластер и приоритет"),
            (str(n_top), "клиентов в списке на проверку, у каждого обоснование")]
    if "n_groups" in f:
        n = int(f["n_groups"])
        kpis.append((str(n), f"{plural(n, 'группа', 'группы', 'групп')} с 2+ известными участниками"))
    if "share20" in f:
        kpis.append((f["share20"], "оборота сети затрагивает проверка топ-20"))
    roles = ", ".join(C.ROLE_LABEL[k].split(",")[0].lower() for k in C.ROLES)
    items = [
        f"<b>Роли по прозрачным правилам.</b> {len(C.ROLES)} ролей: {_e(roles)}. У каждого клиента evidence с цифрами, "
        f"все пороги в одном файле.",
        "<b>Приоритет с объяснением.</b> Сумма пяти компонент с весами: роль, сколько известных участников ведут к клиенту, "
        "оборот, посредничество, временные сигналы."
        + (f" Первым проверять {_gid(f['top1'])}." if "top1" in f else ""),
        "<b>Сценарий «Что если заблокировать».</b> На схеме сети можно исключить топ-5, 10, 20 или любого клиента из карточки"
        + (f". Блокировка топ-20 сокращает крупнейшую связную часть сети с {f['lcc_before']} до {f['lcc_after']} клиентов."
           if "lcc_after" in f else "."),
    ]
    if "overlap" in f:
        items.append(f"<b>Проверка устойчивости.</b> Если сдвинуть любой порог ролей на шаг, топ-20 сохраняется "
                     f"не меньше чем на {f['overlap']}%.")
    if "cutoff" in f:
        c = int(f["cutoff"])
        items.append(f"<b>Граница выборки.</b> На 4-м колене {_int(c)} {plural(c, 'клиент', 'клиента', 'клиентов')} "
                     f"без исходящих в выгрузке. Их не записываем в конечные получатели: по ним нужен запрос исходящих "
                     f"переводов (next_requests.csv).")
    items += [
        "<b>AI-ассистент</b> (запускается локально с ключом API): отвечает на вопросы по сети через инструменты графа, "
        "каждый gid в ответе проверяется кодом, готовит черновик служебной записки.",
        "<b>Масштаб.</b> Синтетический граф той же схемы в 175 тыс. узлов проходит основной расчёт за 71 с. "
        "Замер и план до 1 млн узлов в README.",
    ]
    page = f"""<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Граф денег</title><style>{INDEX_CSS}</style></head><body><div class="w">
<h1>Граф денег: кого проверять первым</h1>
<div class="sub">HackAlem AI, трек «Финансы», кейс Freedom · команда git push --force</div>
<p>Инструмент для AML-аналитика. На входе известные участники ({meta['n_seed']} seed) и сеть их переводов {_e(_period(meta['period']))}.
На выходе у каждого клиента роль, кластер и приоритет с числовым обоснованием, список на проверку и готовые запросы данных.</p>
<div class="kpis">{''.join(f'<div class="kpi"><b>{_e(v)}</b><span>{_e(t)}</span></div>' for v, t in kpis)}</div>
<div class="btns"><a class="btn" href="viewer.html">Схема сети</a><a class="btn alt" href="report.html">Аналитическая справка</a></div>
<h2>Что внутри</h2><ul>{''.join(f'<li>{x}</li>' for x in items)}</ul>
<h2>Выгрузки по схеме ТЗ</h2>
<p><a href="nodes_roles.csv">nodes_roles.csv</a> · <a href="clusters.csv">clusters.csv</a> · <a href="top_nodes.csv">top_nodes.csv</a> ·
<a href="next_requests.csv">next_requests.csv</a></p>
<p>Воспроизвести локально: <code>python -m pip install -r requirements.txt</code>, затем
<code>python -m pipeline --data data --out out</code>. Код и README в репозитории команды.</p>
<div class="warn">Роли и приоритеты являются гипотезами для проверки, а не выводами о виновности. Данные обезличены
организаторами и используются только в рамках хакатона.</div>
</div></body></html>"""
    Path(out_path).write_text(page, encoding="utf-8")
