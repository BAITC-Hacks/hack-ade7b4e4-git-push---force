from app.router import choose_tier


def test_simple_task_goes_fast():
    assert choose_tier("classify", "длинный текст " * 100).tier == "fast"


def test_short_question_goes_fast():
    assert choose_tier("answer", "Операция T-DEMO-2 в порядке?").tier == "fast"


def test_complex_question_goes_smart():
    r = choose_tier("answer", "Посчитай платёж: 1 500 000 тенге на 24 месяца под 24%. Можно одобрить?")
    assert r.tier == "smart"
    assert r.reason


def test_kazakh_markers():
    assert choose_tier("answer", "Неге? Салыстыр екі нұсқаны және есепте").tier == "smart"
