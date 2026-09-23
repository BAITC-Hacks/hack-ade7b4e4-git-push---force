"""Пороги и веса. Все правила ролей читаются отсюда, README и легенда экрана строятся из тех же чисел."""
from __future__ import annotations

SEED = 42  # детерминизм кластеризации и раскладки

# ---------------------------------------------------------------- пороги ролей
HUB_IN = 5            # coordinator: собирает минимум от 5 плательщиков ...
HUB_OUT = 5           # ... и рассылает минимум 5 получателям
COORD_FROM_CONS = 2   # coordinator: получает от 2+ точек консолидации
FAN_OUT = 10          # distributor: рассылает 10+ получателям
FAN_IN = 5            # consolidator: получает от 5+ плательщиков
FAN_IN_SEED = 3       # consolidator: или от 3+ плательщиков, из которых ...
SEED_PAYERS = 2       # ... минимум 2 seed
TRANSIT_LO = 0.8      # transit: отдаёт дальше от 80% ...
TRANSIT_HI = 1.2      # ... до 120% полученного (не seed)
TERMINAL_PT = 0.1     # terminal: дальше уходит не больше 10% полученного
TERMINAL_MIN_KZT = 100_000   # terminal: получил от 100 000 KZT ...
TERMINAL_MIN_PAYERS = 2      # ... или от 2+ плательщиков
FAST_DAYS = 2         # «сквозной транзит»: исходящий перевод в течение 2 дней после входящего
FAST_SHARE = 0.5      # флаг fast_transit: так ушло от 50% исходящей суммы
SYNC_PAYERS = 3       # флаг sync_inflow: 3+ разных плательщика в один день
CYCLE_MAX_LEN = 6     # возвратные потоки: циклы длиной до 6
ROUTE_MIN_TIMES = 2   # устойчивый маршрут A->B->C: повторился минимум 2 раза
MAX_DEPTH = 4         # глубина обхода выгрузки

# ---------------------------------------------------------------- приоритет
ROLE_WEIGHT = {
    "coordinator": 1.00,
    "consolidator": 0.80,
    "distributor": 0.70,
    "transit": 0.50,
    "terminal": 0.40,
    "peripheral": 0.10,
}
PRIORITY_WEIGHTS = {       # сумма 1.0
    "role": 0.35,          # роль из словаря
    "seeds": 0.20,         # сколько seed имеют путь к узлу
    "volume": 0.20,        # оборот узла (лог-шкала)
    "bridge": 0.15,        # посредничество (betweenness, процентиль)
    "signals": 0.10,       # временные и маршрутные признаки
}
SEED_DISCOUNT = 0.85       # seed уже известны следствию: фокус на новых узлах
TOP_N = 30                 # в top_nodes.csv (ТЗ: не меньше 20)
VOLUME_LO, VOLUME_HI = 5_000, 30_000_000   # границы лог-шкалы оборота, KZT

# ---------------------------------------------------------------- подписи
ROLE_LABEL = {
    "coordinator": "Координатор, кандидат в организаторы",
    "consolidator": "Точка консолидации",
    "distributor": "Распределитель (веер)",
    "transit": "Транзит",
    "terminal": "Конечный получатель",
    "peripheral": "Периферия",
}
ROLE_COLOR = {
    "coordinator": "#7b2cbf",
    "consolidator": "#d62828",
    "distributor": "#f77f00",
    "transit": "#1d8fe1",
    "terminal": "#2a9d8f",
    "peripheral": "#9aa5b1",
}
ROLES = list(ROLE_WEIGHT)


def role_rules() -> dict[str, str]:
    """Правила ролей человеческим языком. Порядок проверки сверху вниз, первое совпадение побеждает."""
    return {
        "coordinator": (f"Собирает от {HUB_IN}+ плательщиков и рассылает {HUB_OUT}+ получателям, "
                        f"или получает от {COORD_FROM_CONS}+ точек консолидации"),
        "distributor": f"Рассылает {FAN_OUT}+ получателям (веер)",
        "consolidator": (f"Получает от {FAN_IN}+ плательщиков, или от {FAN_IN_SEED}+ плательщиков, "
                         f"среди которых {SEED_PAYERS}+ seed"),
        "transit": (f"Не seed, отдаёт дальше {int(TRANSIT_LO * 100)}-{int(TRANSIT_HI * 100)}% полученного; "
                    f"флаг «сквозной», если {int(FAST_SHARE * 100)}%+ ушло за {FAST_DAYS} дня"),
        "terminal": (f"Колено 0-3 (не обрыв выборки), дальше уходит не больше {int(TERMINAL_PT * 100)}% полученного, "
                     f"получено от {TERMINAL_MIN_KZT:,} KZT или от {TERMINAL_MIN_PAYERS}+ плательщиков").replace(",", " "),
        "peripheral": ("Не подходит ни под одно правило. Сюда же узлы 4-го колена без исходящих: "
                       "это обрыв выгрузки, роль по данным не определить"),
    }
