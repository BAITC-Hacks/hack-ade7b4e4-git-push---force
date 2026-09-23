from app.pii import luhn_ok, mask_pii


def test_masks_iin_card_phone_iban_email():
    text = ("ИИН 123456789012, карта 4111 1111 1111 1111, тел +7 (701) 234-56-78, "
            "IBAN KZ86125KZT5004100100, почта a.b@mail.kz")
    masked, found = mask_pii(text)
    assert "123456789012" not in masked
    assert "[КАРТА *1111]" in masked
    assert "234-56-78" not in masked
    assert "KZ86125KZT5004100100" not in masked
    assert "a.b@mail.kz" not in masked
    assert set(found) == {"ИИН", "КАРТА", "ТЕЛЕФОН", "IBAN", "EMAIL"}


def test_keeps_amounts_and_ids():
    text = "Перевод 450 000 тенге, операция T-DEMO-1, срок 24 месяца, 1 500 000 под 24%"
    masked, found = mask_pii(text)
    assert masked == text
    assert found == []


def test_non_luhn_16_digits_not_called_card():
    masked, found = mask_pii("номер 1234 5678 9012 3456")
    assert "КАРТА" not in found


def test_luhn():
    assert luhn_ok("4111111111111111")
    assert not luhn_ok("4111111111111112")
