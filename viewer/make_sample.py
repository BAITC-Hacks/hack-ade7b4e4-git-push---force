"""Create a deterministic synthetic fixture, not a pipeline result."""

import json
import math
from pathlib import Path


def make_sample() -> dict:
    ids = [str(900000000000000001 + i) for i in range(12)]
    roles = [
        ("consolidator", "Точка консолидации", "#d62728", "Демонстрационное правило: входящих контрагентов ≥ 3."),
        ("transit", "Транзит", "#e6a328", "Демонстрационное правило: есть вход и выход; выход / вход от 0,8 до 1,2."),
        ("distributor", "Распределение", "#9467bd", "Демонстрационное правило: исходящих контрагентов ≥ 3."),
        ("terminal", "Конечный получатель", "#2a9d8f", "Демонстрационное правило: вход > 0, выход = 0, колено < 4."),
        ("coordinator", "Координирующий узел", "#247bb0", "Демонстрационное правило: связь с ≥ 2 кластерами, вход > 0 и выход > 0."),
        ("peripheral", "Периферия", "#94a3b8", "Другие признаки не выявлены либо узел на границе выгрузки."),
    ]
    routes = [(0,3,50000),(1,3,75000),(2,3,25000),(3,4,150000),(4,5,140000),
              (5,6,60000),(5,7,40000),(5,8,40000),(6,9,30000),(9,10,20000),(8,9,20000)]
    depths = [0,0,0,1,2,3,3,3,4,3,4,0]
    assigned = ["peripheral"]*3 + ["consolidator","transit","distributor","coordinator","terminal","peripheral","coordinator","peripheral","peripheral"]
    edges = [dict(source=ids[s],target=ids[t],sum_kzt=float(amount),n_tx=1+i%3,depth=depths[t]) for i,(s,t,amount) in enumerate(routes)]
    nodes = []
    for i,gid in enumerate(ids):
        inc = [e for e in edges if e["target"] == gid]
        out = [e for e in edges if e["source"] == gid]
        in_kzt = sum(e["sum_kzt"] for e in inc)
        out_kzt = sum(e["sum_kzt"] for e in out)
        score = round((len(inc)+len(out))/6, 3)
        nodes.append(dict(id=gid,role=assigned[i],role_score=0.7 if assigned[i] != "peripheral" else 0.3,
                          cluster_id=i//4,priority_score=score,rank=None,is_seed=depths[i]==0,depth=depths[i],
                          in_deg=len(inc),out_deg=len(out),in_kzt=float(in_kzt),out_kzt=float(out_kzt),
                          in_tx=sum(e["n_tx"] for e in inc),out_tx=sum(e["n_tx"] for e in out),
                          pass_through=round(out_kzt/in_kzt,3) if in_kzt else None,
                          seeds_upstream=3 if 3 <= i <= 10 else 0,
                          evidence=f"Демонстрационная гипотеза: входящих контрагентов {len(inc)}, исходящих {len(out)}; вход {in_kzt:.0f} ₸, выход {out_kzt:.0f} ₸.",
                          why="",flags=["cutoff_depth4"] if depths[i]==4 else ["isolated_seed"] if i==11 else [],
                          x=round(math.cos(i*math.tau/12)*380,2),y=round(math.sin(i*math.tau/12)*280,2)))
    top=[]
    for rank,n in enumerate(sorted(nodes,key=lambda n:(-n["priority_score"],n["id"])),1):
        n["rank"]=rank
        n["why"]=f"Демонстрационный приоритет: {n['in_deg']+n['out_deg']} направленных связей; оценка {n['priority_score']}. Проверить контекст переводов."
        top.append(dict(rank=rank,gid=n["id"],role=n["role"],priority_score=n["priority_score"],why=n["why"]))
    clusters=[]
    for cid in range(3):
        members=[n for n in nodes if n["cluster_id"]==cid]
        member_ids={n["id"] for n in members}
        clusters.append(dict(cluster_id=cid,n_nodes=len(members),n_seed=sum(n["is_seed"] for n in members),
                             sum_kzt_internal=sum(e["sum_kzt"] for e in edges if e["source"] in member_ids and e["target"] in member_ids),
                             top_gids=[n["id"] for n in sorted(members,key=lambda n:n["rank"])[:2]],
                             hypothesis="Синтетическая группа для проверки интерфейса; требуется проверка связей."))
    return dict(meta=dict(generated_at="2026-09-23T13:00:00",n_nodes=len(nodes),n_edges=len(edges),
                          n_tx=sum(e["n_tx"] for e in edges),n_seed=sum(n["is_seed"] for n in nodes),
                          period="ДЕМОНСТРАЦИОННЫЕ ДАННЫЕ · 2026-07-01..2026-07-31",turnover_kzt=sum(e["sum_kzt"] for e in edges)),
                roles=[dict(key=k,label=l,color=c,rule=r) for k,l,c,r in roles],nodes=nodes,edges=edges,clusters=clusters,top=top)


if __name__ == "__main__":
    Path(__file__).with_name("sample_graph.json").write_text(json.dumps(make_sample(),ensure_ascii=False,indent=2),encoding="utf-8")
