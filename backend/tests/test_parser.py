import pytest
from app.services.nlu_parser import parse_indonesian_amount, parse_transaction_text


def test_indonesian_amount_slang():
    # 25k -> 25,000
    amt, curr = parse_indonesian_amount("ngopi 25k")
    assert amt == 25000.0
    assert curr == "IDR"

    # 50rb -> 50,000
    amt, curr = parse_indonesian_amount("bensin 50rb")
    assert amt == 50000.0

    # 1.5jt -> 1,500,000
    amt, curr = parse_indonesian_amount("service laptop 1.5jt")
    assert amt == 1500000.0

    # $15 -> 15.0 USD
    amt, curr = parse_indonesian_amount("langganan netflix $15")
    assert amt == 15.0
    assert curr == "USD"


def test_transaction_text_parsing():
    parsed = parse_transaction_text("beli kopi kenangan 28rb pake gopay", user_wallets=["Bank BCA", "GoPay", "Cash"])
    assert parsed["type"] == "EXPENSE"
    assert parsed["amount"] == 28000.0
    assert parsed["currency"] == "IDR"
    assert parsed["category_name"] == "Makanan & Minuman"
    assert parsed["wallet_hint"] == "GoPay"

    # Income parsing
    parsed_inc = parse_transaction_text("gaji masuk 15jt ke bca")
    assert parsed_inc["type"] == "INCOME"
    assert parsed_inc["amount"] == 15000000.0
    assert parsed_inc["category_name"] == "Gaji & Pendapatan"

