import pytest
from app.services.nlu_parser import parse_transaction_text


def test_nlu_transfer_and_topup_parsing():
    wallets = ["BCA", "GoPay", "Mandiri", "Jago", "Cash Dompet"]

    # 1. Topup with source wallet -> TRANSFER
    res1 = parse_transaction_text("topup gopay 100rb dari bca", user_wallets=wallets)
    assert res1["type"] == "TRANSFER"
    assert res1["amount"] == 100000.0
    assert res1["source_wallet_hint"] == "BCA"
    assert res1["target_wallet_hint"] == "GoPay"

    # 2. Transfer from source to target -> TRANSFER
    res2 = parse_transaction_text("transfer 500rb dari mandiri ke jago", user_wallets=wallets)
    assert res2["type"] == "TRANSFER"
    assert res2["amount"] == 500000.0
    assert res2["source_wallet_hint"] == "Mandiri"
    assert res2["target_wallet_hint"] == "Jago"

    # 3. Topup without source wallet -> INCOME
    res3 = parse_transaction_text("topup saldo gopay 1jt", user_wallets=wallets)
    assert res3["type"] == "INCOME"
    assert res3["amount"] == 1000000.0
    assert res3["target_wallet_hint"] == "GoPay"
    assert res3["source_wallet_hint"] is None

    # 4. Expense with payment wallet -> EXPENSE
    res4 = parse_transaction_text("kopi susu 25rb bayar gopay", user_wallets=wallets)
    assert res4["type"] == "EXPENSE"
    assert res4["amount"] == 25000.0
    assert res4["wallet_hint"] == "GoPay"
