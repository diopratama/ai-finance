from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import re

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.db import (
    Budget,
    BudgetGroup,
    Category,
    FinancialProfile,
    Transaction,
    User,
    Wallet,
    ensure_user_default_groups,
    get_db,
)

router = APIRouter(prefix="/budgets", tags=["Budgets & Categories"])

DEFAULT_GROUP_ORDER = [
    "LIVING NEEDS",
    "LIFE STYLE",
    "ZAKAT DAN SEDEKAH",
    "PREDICTABLE SAVING",
]

SINKING_GROUP_NAMES = {
    "PREDICTABLE SAVING",
    "PREDICTABLE SAVINGS",
    "SINKING FUND",
    "TABUNGAN TERJADWAL",
}

AUTO_CATEGORY_KEYWORDS = {
    "Tagihan & Utilitas": [
        "kpr", "pdam", "internet", "wifi", "listrik", "pln", "ipl", "air", "pulsa", "kartu kredit", "art", "cicilan",
    ],
    "Transportasi": [
        "bensin", "mobil", "motor", "tol", "parkir", "pajak mobil", "pajak motor", "service", "grab", "gojek",
    ],
    "Pendidikan": [
        "sekolah", "les", "ngaji", "spp", "kuliah", "kursus", "buku", "pendidikan",
    ],
    "Belanja": [
        "belanja", "bulanan", "cash bulanan", "rumah tangga", "groceries", "pasar",
    ],
    "Hiburan & Rekreasi": [
        "netflix", "google", "spotify", "youtube", "jajan", "liburan", "rekreasi", "hiburan", "staycation",
    ],
    "Kesehatan": [
        "vitamin", "bpjs", "obat", "kesehatan", "dokter", "asuransi",
    ],
    "Investasi": [
        "investasi", "saham", "reksadana", "emas", "sukuk", "rdn", "umrah", "qurban", "pelunasan", "tabungan", "arisan",
    ],
    "Makanan & Minuman": [
        "makan", "minum", "kopi", "katering",
    ],
}


def get_current_month_key() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


def normalize_month_key(month_key: Optional[str]) -> str:
    if not month_key:
        return get_current_month_key()
    mk = month_key.strip()
    if not re.match(r"^\d{4}-(0[1-9]|1[0-2])$", mk):
        raise HTTPException(status_code=400, detail="Format bulan harus YYYY-MM (contoh: 2026-11)")
    return mk


def previous_month_key(month_key: str) -> str:
    year, month = [int(p) for p in month_key.split("-")]
    if month == 1:
        return f"{year - 1:04d}-12"
    return f"{year:04d}-{month - 1:02d}"


def is_sinking_group(group_type: str) -> bool:
    return group_type.strip().upper() in SINKING_GROUP_NAMES


def resolve_auto_category(
    db: Session,
    user_id: str,
    item_name: str,
    group_type: str,
    explicit_category_id: Optional[str] = None,
) -> Optional[Category]:
    if explicit_category_id:
        cat = db.query(Category).filter(
            Category.id == explicit_category_id,
            (Category.is_system == True) | (Category.user_id == user_id),
        ).first()
        if cat:
            return cat

    categories = db.query(Category).filter(
        (Category.is_system == True) | (Category.user_id == user_id)
    ).all()
    by_lower_name = {c.name.lower(): c for c in categories}

    # Exact match against custom or system category
    if item_name.strip().lower() in by_lower_name:
        return by_lower_name[item_name.strip().lower()]

    combined = f"{item_name} {group_type}".lower()
    for sys_name, keywords in AUTO_CATEGORY_KEYWORDS.items():
        if any(kw in combined for kw in keywords):
            matched = by_lower_name.get(sys_name.lower())
            if matched:
                return matched

    return by_lower_name.get("lain-lain")


def _tx_in_month(tx: Transaction, month_key: str) -> bool:
    if not tx.transaction_date:
        return False
    return tx.transaction_date.strftime("%Y-%m") == month_key


def compute_budget_spent_map(
    budgets: List[Budget],
    transactions: List[Transaction],
    month_key: str,
) -> Dict[str, float]:
    """
    Computes exact spending per budget row in `month_key` without double counting:
    1. Any EXPENSE transaction in `month_key` with `tx.budget_id == b.id` counts toward `b`.
    2. Legacy fallback: if `tx.budget_id is None` and `tx.category_id == b.category_id`,
       count it ONLY when `b` is the sole budget row mapped to `b.category_id` in `month_key`
       (or `b.name == b.category.name`), avoiding double counting across multiple items sharing a category.
    """
    month_expenses = [
        t for t in transactions
        if t.type == "EXPENSE" and _tx_in_month(t, month_key)
    ]

    cat_counts: Dict[str, int] = {}
    for b in budgets:
        if b.category_id:
            cat_counts[b.category_id] = cat_counts.get(b.category_id, 0) + 1

    spent_map: Dict[str, float] = {b.id: 0.0 for b in budgets}
    budget_ids = set(spent_map.keys())

    for tx in month_expenses:
        if tx.budget_id and tx.budget_id in budget_ids:
            spent_map[tx.budget_id] += tx.amount_in_base
        elif not tx.budget_id and tx.category_id:
            # Find sole or exact-category-named row
            candidates = [b for b in budgets if b.category_id == tx.category_id]
            if len(candidates) == 1:
                only_b = candidates[0]
                if not only_b.is_sinking_fund:
                    spent_map[only_b.id] += tx.amount_in_base
            elif len(candidates) > 1:
                exact = next(
                    (b for b in candidates if b.category and (b.name or "").strip().lower() == b.category.name.lower()),
                    None,
                )
                if exact and not exact.is_sinking_fund:
                    spent_map[exact.id] += tx.amount_in_base

    return spent_map


def serialize_budget_item(b: Budget, spent_amount: float) -> Dict[str, Any]:
    limit_amt = float(b.limit_amount or 0.0)
    rollover = float(b.rollover_balance or 0.0)
    funded = float(b.funded_this_month or 0.0)
    sinking = bool(b.is_sinking_fund)
    item_name = (b.name or (b.category.name if b.category else "Pos Anggaran")).strip()
    grp = (b.group_type or "LIVING NEEDS").strip().upper()

    if sinking:
        accumulated = max(0.0, rollover + funded - spent_amount)
        # Progress for sinking fund this month: funded vs monthly budget target
        pct_used = min(100.0, round((funded / limit_amt) * 100, 1)) if limit_amt > 0 else 0.0
        remaining = round(max(0.0, limit_amt - funded), 2)
        is_over = spent_amount > (rollover + max(limit_amt, funded)) and spent_amount > 0
    else:
        accumulated = 0.0
        pct_used = min(100.0, round((spent_amount / limit_amt) * 100, 1)) if limit_amt > 0 else 0.0
        remaining = round(max(0.0, limit_amt - spent_amount), 2)
        is_over = spent_amount > limit_amt and limit_amt > 0

    return {
        "id": b.id,
        "name": item_name,
        "group_type": grp,
        "remark": b.remark or "",
        "limit_amount": round(limit_amt, 2),
        "spent_amount": round(spent_amount, 2),
        "remaining_amount": remaining,
        "percent_used": pct_used,
        "is_over_budget": is_over,
        "period": b.period,
        "month_key": b.month_key or get_current_month_key(),
        "is_sinking_fund": sinking,
        "rollover_balance": round(rollover, 2),
        "funded_this_month": round(funded, 2),
        "accumulated_balance": round(accumulated, 2),
        "sort_order": b.sort_order or 0,
        "wallet_id": b.wallet_id,
        "wallet": (
            {
                "id": b.wallet.id,
                "name": b.wallet.name,
                "type": b.wallet.type,
                "color": b.wallet.color,
                "balance": round(b.wallet.balance, 2),
            }
            if b.wallet and not b.wallet.is_archived
            else None
        ),
        "category_id": b.category_id,
        "category": (
            {
                "id": b.category.id,
                "name": b.category.name,
                "icon": b.category.icon,
                "color": b.category.color,
            }
            if b.category
            else None
        ),
    }


def compute_monthly_allocation_data(
    user: User,
    db: Session,
    month_key: Optional[str] = None,
) -> Dict[str, Any]:
    mk = normalize_month_key(month_key)
    prev_mk = previous_month_key(mk)

    budgets = (
        db.query(Budget)
        .filter(Budget.user_id == user.id, Budget.month_key == mk)
        .order_by(Budget.sort_order.asc(), Budget.created_at.asc())
        .all()
    )
    prev_count = (
        db.query(Budget)
        .filter(Budget.user_id == user.id, Budget.month_key == prev_mk)
        .count()
    )

    all_user_groups = [
        r[0]
        for r in db.query(Budget.group_type).filter(Budget.user_id == user.id).distinct().all()
        if r[0]
    ]

    wallets = (
        db.query(Wallet)
        .filter(Wallet.user_id == user.id, Wallet.is_archived == False)
        .order_by(Wallet.created_at.asc())
        .all()
    )
    transactions = db.query(Transaction).filter(Transaction.user_id == user.id).all()
    profile = db.query(FinancialProfile).filter(FinancialProfile.user_id == user.id).first()

    month_tx_income = sum(
        t.amount_in_base for t in transactions if t.type == "INCOME" and _tx_in_month(t, mk)
    )
    if profile and (profile.monthly_income or 0.0) > 0:
        reference_income = float(profile.monthly_income)
        income_source = "PROFILE"
    elif month_tx_income > 0:
        reference_income = float(month_tx_income)
        income_source = "TRANSACTIONS"
    else:
        reference_income = 0.0
        income_source = "UNSET"

    spent_map = compute_budget_spent_map(budgets, transactions, mk)
    serialized_items = [serialize_budget_item(b, spent_map.get(b.id, 0.0)) for b in budgets]

    # Group configuration and ordering from user's budget_groups table
    user_groups = ensure_user_default_groups(db, user.id)
    group_sinking_map = {g.name: g.is_sinking_fund for g in user_groups}
    ordered_group_names: List[str] = [g.name for g in user_groups]

    # Include any legacy group types from serialized items not yet in user_groups
    for item in serialized_items:
        if item["group_type"] not in ordered_group_names:
            ordered_group_names.append(item["group_type"])

    groups_out: List[Dict[str, Any]] = []
    for g_name in ordered_group_names:
        g_items = [it for it in serialized_items if it["group_type"] == g_name]
        is_sinking = group_sinking_map.get(
            g_name,
            is_sinking_group(g_name) or any(it["is_sinking_fund"] for it in g_items),
        )
        sub_budget = round(sum(it["limit_amount"] for it in g_items), 2)
        sub_spent = round(sum(it["spent_amount"] for it in g_items), 2)
        sub_accum = round(sum(it["accumulated_balance"] for it in g_items), 2)
        pct_income = round((sub_budget / reference_income) * 100, 2) if reference_income > 0 else 0.0
        groups_out.append({
            "group_type": g_name,
            "is_sinking_fund_group": is_sinking,
            "subtotal_budget": sub_budget,
            "subtotal_spent": sub_spent,
            "subtotal_accumulated": sub_accum,
            "income_percentage": pct_income,
            "items_count": len(g_items),
            "items": g_items,
        })

    # Per-wallet allocation & funding sufficiency summary
    wallet_allocations: List[Dict[str, Any]] = []
    for w in wallets:
        w_items = [it for it in serialized_items if it["wallet_id"] == w.id]
        total_monthly_budget = sum(it["limit_amount"] for it in w_items)
        sinking_rollover = sum(it["rollover_balance"] for it in w_items if it["is_sinking_fund"])
        sinking_held = sum(it["accumulated_balance"] for it in w_items if it["is_sinking_fund"])

        # Remaining commitment in this wallet:
        # - For regular monthly items: remaining unspent budget (max(0, limit - spent))
        # - For sinking fund items: rollover + max(limit, funded_this_month) - spent
        rem_commitment = 0.0
        for it in w_items:
            if it["is_sinking_fund"]:
                rem_commitment += max(
                    0.0,
                    it["rollover_balance"] + max(it["limit_amount"], it["funded_this_month"]) - it["spent_amount"],
                )
            else:
                rem_commitment += max(0.0, it["limit_amount"] - it["spent_amount"])

        cur_bal = float(w.balance or 0.0)
        shortfall = max(0.0, rem_commitment - cur_bal) if w_items else 0.0
        free_bal = max(0.0, cur_bal - rem_commitment)

        if not w_items:
            w_status = "IDLE"
        elif shortfall > 0.5:
            w_status = "SHORTFALL"
        else:
            w_status = "FUNDED"

        wallet_allocations.append({
            "wallet_id": w.id,
            "wallet_name": w.name,
            "wallet_type": w.type,
            "wallet_color": w.color,
            "current_balance": round(cur_bal, 2),
            "total_monthly_budget": round(total_monthly_budget, 2),
            "sinking_rollover_balance": round(sinking_rollover, 2),
            "sinking_fund_held": round(sinking_held, 2),
            "remaining_commitment": round(rem_commitment, 2),
            "free_unallocated_balance": round(free_bal, 2),
            "shortfall_amount": round(shortfall, 2),
            "status": w_status,
            "items_count": len(w_items),
        })

    unassigned_budget = round(
        sum(it["limit_amount"] for it in serialized_items if not it["wallet_id"]),
        2,
    )
    total_budget = round(sum(it["limit_amount"] for it in serialized_items), 2)
    total_spent = round(sum(it["spent_amount"] for it in serialized_items), 2)
    total_remaining = round(max(0.0, total_budget - total_spent), 2)
    allocated_pct = round((total_budget / reference_income) * 100, 2) if reference_income > 0 else 0.0
    unallocated_income = round(reference_income - total_budget, 2) if reference_income > 0 else 0.0

    return {
        "month_key": mk,
        "previous_month_key": prev_mk,
        "has_previous_month_template": prev_count > 0,
        "reference_income": round(reference_income, 2),
        "income_source": income_source,
        "group_presets": ordered_group_names,
        "groups": groups_out,
        "wallet_allocations": wallet_allocations,
        "unassigned_budget_total": unassigned_budget,
        "totals": {
            "total_budget": total_budget,
            "total_spent": total_spent,
            "total_remaining": total_remaining,
            "allocated_percentage": allocated_pct,
            "unallocated_income": unallocated_income,
            "items_count": len(serialized_items),
        },
    }


# ==================== REQUEST SCHEMAS ====================


class CreateCategoryRequest(BaseModel):
    name: str
    type: str = "EXPENSE"  # EXPENSE | INCOME
    color: str = "#f0b000"
    icon: str = "tag"


class UpdateCategoryRequest(BaseModel):
    name: Optional[str] = None
    type: Optional[str] = None
    color: Optional[str] = None
    icon: Optional[str] = None


class CreateBudgetRequest(BaseModel):
    name: Optional[str] = None
    group_type: str = "LIVING NEEDS"
    limit_amount: float
    remark: Optional[str] = None
    wallet_id: Optional[str] = None
    category_id: Optional[str] = None
    month_key: Optional[str] = None
    is_sinking_fund: Optional[bool] = None
    rollover_balance: float = 0.0
    funded_this_month: float = 0.0
    sort_order: Optional[int] = None
    period: str = "MONTHLY"


class UpdateBudgetRequest(BaseModel):
    name: Optional[str] = None
    group_type: Optional[str] = None
    limit_amount: Optional[float] = None
    remark: Optional[str] = None
    wallet_id: Optional[str] = None
    category_id: Optional[str] = None
    is_sinking_fund: Optional[bool] = None
    rollover_balance: Optional[float] = None
    funded_this_month: Optional[float] = None
    sort_order: Optional[int] = None


class BudgetGroupOut(BaseModel):
    id: str
    name: str
    is_sinking_fund: bool
    sort_order: int
    items_count: int = 0


class CreateBudgetGroupRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    is_sinking_fund: bool = False
    sort_order: Optional[int] = None


class UpdateBudgetGroupRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    is_sinking_fund: Optional[bool] = None
    sort_order: Optional[int] = None


class DeleteBudgetGroupRequest(BaseModel):
    action: str = Field("reassign", description="'reassign' or 'cascade'")
    reassign_to_id: Optional[str] = None
    reassign_to_name: Optional[str] = None


class RenameGroupRequest(BaseModel):
    old_group_type: str
    new_group_type: str
    month_key: Optional[str] = None
    is_sinking_fund: Optional[bool] = None


class UpdateReferenceIncomeRequest(BaseModel):
    monthly_income: float = Field(..., ge=0)


class CopyMonthRequest(BaseModel):
    target_month: str
    source_month: Optional[str] = None
    overwrite: bool = False


class PaydayTransferItem(BaseModel):
    to_wallet_id: str
    amount: float


class DistributePaydayRequest(BaseModel):
    source_wallet_id: str
    month_key: Optional[str] = None
    transfers: Optional[List[PaydayTransferItem]] = None
    mode: str = "SHORTFALL"  # SHORTFALL | FULL_BUDGET
    auto_fund_sinking: bool = True


class RecordBudgetActionRequest(BaseModel):
    mode: str = "EXPENSE"  # EXPENSE | FUND_SINKING
    amount: Optional[float] = None
    wallet_id: Optional[str] = None
    description: Optional[str] = None


# ==================== CATEGORY ENDPOINTS ====================


@router.get("/categories")
def list_categories(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Lists system and user-specific custom categories."""
    categories = (
        db.query(Category)
        .filter((Category.is_system == True) | (Category.user_id == current_user.id))
        .order_by(Category.is_system.desc(), Category.name.asc())
        .all()
    )
    return [
        {
            "id": c.id,
            "name": c.name,
            "icon": c.icon,
            "color": c.color,
            "type": c.type,
            "is_system": c.is_system,
        }
        for c in categories
    ]


@router.post("/categories")
def create_custom_category(
    req: CreateCategoryRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    clean_name = req.name.strip()
    if not clean_name:
        raise HTTPException(status_code=400, detail="Nama kategori tidak boleh kosong")

    cat_type = req.type.strip().upper()
    if cat_type not in ("EXPENSE", "INCOME"):
        raise HTTPException(status_code=400, detail="Tipe kategori harus EXPENSE atau INCOME")

    existing = (
        db.query(Category)
        .filter(
            ((Category.is_system == True) | (Category.user_id == current_user.id)),
            Category.name.ilike(clean_name),
            Category.type == cat_type,
        )
        .first()
    )
    if existing:
        return {
            "id": existing.id,
            "name": existing.name,
            "icon": existing.icon,
            "color": existing.color,
            "type": existing.type,
            "is_system": existing.is_system,
        }

    cat = Category(
        user_id=current_user.id,
        name=clean_name,
        type=cat_type,
        color=req.color or "#f0b000",
        icon=req.icon or "tag",
        is_system=False,
    )
    db.add(cat)
    db.commit()
    db.refresh(cat)
    return {
        "id": cat.id,
        "name": cat.name,
        "icon": cat.icon,
        "color": cat.color,
        "type": cat.type,
        "is_system": cat.is_system,
    }


@router.put("/categories/{category_id}")
def update_custom_category(
    category_id: str,
    req: UpdateCategoryRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    cat = db.query(Category).filter(
        Category.id == category_id,
        Category.user_id == current_user.id,
        Category.is_system == False,
    ).first()
    if not cat:
        raise HTTPException(status_code=404, detail="Kategori custom tidak ditemukan")

    if req.name is not None and req.name.strip():
        cat.name = req.name.strip()
    if req.type is not None and req.type.strip().upper() in ("EXPENSE", "INCOME"):
        cat.type = req.type.strip().upper()
    if req.color is not None and req.color.strip():
        cat.color = req.color.strip()
    if req.icon is not None and req.icon.strip():
        cat.icon = req.icon.strip()

    db.commit()
    db.refresh(cat)
    return {
        "id": cat.id,
        "name": cat.name,
        "icon": cat.icon,
        "color": cat.color,
        "type": cat.type,
        "is_system": cat.is_system,
    }


@router.delete("/categories/{category_id}")
def delete_custom_category(
    category_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    cat = db.query(Category).filter(
        Category.id == category_id,
        Category.user_id == current_user.id,
        Category.is_system == False,
    ).first()
    if not cat:
        raise HTTPException(status_code=404, detail="Kategori custom tidak ditemukan atau merupakan kategori sistem")

    db.delete(cat)
    db.commit()
    return {"message": "Kategori custom berhasil dihapus"}


# ==================== ALLOCATION & GROUP ENDPOINTS ====================


@router.get("/allocation")
def get_monthly_allocation(
    month: Optional[str] = Query(None, description="Format YYYY-MM"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Returns full spreadsheet-style monthly allocation, group subtotals & %, and per-wallet sufficiency."""
    return compute_monthly_allocation_data(current_user, db, month)


@router.put("/reference-income")
def update_reference_income(
    req: UpdateReferenceIncomeRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Updates user's monthly income reference in FinancialProfile for % allocation calculation."""
    profile = db.query(FinancialProfile).filter(FinancialProfile.user_id == current_user.id).first()
    if not profile:
        profile = FinancialProfile(user_id=current_user.id, monthly_income=req.monthly_income)
        db.add(profile)
    else:
        profile.monthly_income = req.monthly_income
    db.commit()
    return {"monthly_income": profile.monthly_income}


@router.get("/groups", response_model=List[BudgetGroupOut])
def get_budget_groups(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Returns all configured budget groups for the current user."""
    groups = ensure_user_default_groups(db, current_user.id)
    result = []
    for g in groups:
        count = db.query(Budget).filter(
            Budget.user_id == current_user.id,
            Budget.group_type == g.name,
        ).count()
        result.append(
            BudgetGroupOut(
                id=g.id,
                name=g.name,
                is_sinking_fund=g.is_sinking_fund,
                sort_order=g.sort_order,
                items_count=count,
            )
        )
    return result


@router.post("/groups", response_model=BudgetGroupOut, status_code=status.HTTP_201_CREATED)
def create_budget_group(
    req: CreateBudgetGroupRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Creates a new budget group for the user."""
    name_clean = req.name.strip().upper()
    if not name_clean:
        raise HTTPException(status_code=400, detail="Nama grup tidak boleh kosong")

    # Ensure defaults are initialized first
    ensure_user_default_groups(db, current_user.id)

    existing = db.query(BudgetGroup).filter(
        BudgetGroup.user_id == current_user.id,
        BudgetGroup.name == name_clean,
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"Grup dengan nama '{name_clean}' sudah ada")

    max_order = db.query(BudgetGroup).filter(BudgetGroup.user_id == current_user.id).count()
    group = BudgetGroup(
        user_id=current_user.id,
        name=name_clean,
        is_sinking_fund=req.is_sinking_fund or is_sinking_group(name_clean),
        sort_order=req.sort_order if req.sort_order is not None else max_order + 1,
    )
    db.add(group)
    db.commit()
    db.refresh(group)
    return BudgetGroupOut(
        id=group.id,
        name=group.name,
        is_sinking_fund=group.is_sinking_fund,
        sort_order=group.sort_order,
        items_count=0,
    )


@router.put("/groups/{group_id}", response_model=BudgetGroupOut)
def update_budget_group(
    group_id: str,
    req: UpdateBudgetGroupRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Updates group name, sinking fund behavior, or sort order and cascades to budget items."""
    group = db.query(BudgetGroup).filter(
        BudgetGroup.id == group_id,
        BudgetGroup.user_id == current_user.id,
    ).first()
    if not group:
        raise HTTPException(status_code=404, detail="Grup tidak ditemukan")

    old_name = group.name
    new_name = req.name.strip().upper() if req.name is not None and req.name.strip() else old_name

    if new_name != old_name:
        dup = db.query(BudgetGroup).filter(
            BudgetGroup.user_id == current_user.id,
            BudgetGroup.name == new_name,
            BudgetGroup.id != group_id,
        ).first()
        if dup:
            raise HTTPException(status_code=400, detail=f"Grup dengan nama '{new_name}' sudah ada")
        group.name = new_name

        # Cascade rename across all historical budget items of this user
        db.query(Budget).filter(
            Budget.user_id == current_user.id,
            Budget.group_type == old_name,
        ).update({"group_type": new_name}, synchronize_session=False)

    if req.is_sinking_fund is not None:
        group.is_sinking_fund = req.is_sinking_fund
        db.query(Budget).filter(
            Budget.user_id == current_user.id,
            Budget.group_type == group.name,
        ).update({"is_sinking_fund": req.is_sinking_fund}, synchronize_session=False)

    if req.sort_order is not None:
        group.sort_order = req.sort_order

    db.commit()
    db.refresh(group)

    count = db.query(Budget).filter(
        Budget.user_id == current_user.id,
        Budget.group_type == group.name,
    ).count()

    return BudgetGroupOut(
        id=group.id,
        name=group.name,
        is_sinking_fund=group.is_sinking_fund,
        sort_order=group.sort_order,
        items_count=count,
    )


@router.delete("/groups/{group_id}")
def delete_budget_group(
    group_id: str,
    action: str = Query("reassign", pattern="^(cascade|reassign)$"),
    reassign_to_id: Optional[str] = Query(None),
    reassign_to_name: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Deletes a budget group, with optional reassigning of its items or cascade deletion."""
    group = db.query(BudgetGroup).filter(
        BudgetGroup.id == group_id,
        BudgetGroup.user_id == current_user.id,
    ).first()
    if not group:
        raise HTTPException(status_code=404, detail="Grup tidak ditemukan")

    total_groups = db.query(BudgetGroup).filter(BudgetGroup.user_id == current_user.id).count()
    if total_groups <= 1:
        raise HTTPException(status_code=400, detail="Tidak dapat menghapus satu-satunya grup yang tersisa")

    group_name = group.name
    items_query = db.query(Budget).filter(
        Budget.user_id == current_user.id,
        Budget.group_type == group_name,
    )
    items_count = items_query.count()

    if items_count > 0:
        if action == "cascade":
            items_query.delete(synchronize_session=False)
        else:
            target_group = None
            if reassign_to_id:
                target_group = db.query(BudgetGroup).filter(
                    BudgetGroup.id == reassign_to_id,
                    BudgetGroup.user_id == current_user.id,
                    BudgetGroup.id != group_id,
                ).first()
            elif reassign_to_name:
                target_group = db.query(BudgetGroup).filter(
                    BudgetGroup.name == reassign_to_name.strip().upper(),
                    BudgetGroup.user_id == current_user.id,
                    BudgetGroup.id != group_id,
                ).first()
            if not target_group:
                target_group = db.query(BudgetGroup).filter(
                    BudgetGroup.user_id == current_user.id,
                    BudgetGroup.id != group_id,
                ).order_by(BudgetGroup.sort_order.asc()).first()
            if not target_group:
                raise HTTPException(status_code=400, detail="Tidak ada grup tujuan yang valid untuk pemindahan pos")

            items_query.update({
                "group_type": target_group.name,
                "is_sinking_fund": target_group.is_sinking_fund,
            }, synchronize_session=False)

    db.delete(group)
    db.commit()
    return {
        "success": True,
        "deleted_group_id": group_id,
        "deleted_group_name": group_name,
        "items_affected": items_count,
        "action_taken": action,
    }


@router.put("/groups/rename")
def rename_budget_group(
    req: RenameGroupRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    old_grp = req.old_group_type.strip().upper()
    new_grp = req.new_group_type.strip().upper()
    if not old_grp or not new_grp:
        raise HTTPException(status_code=400, detail="Nama grup TYPE tidak boleh kosong")

    # Sync with BudgetGroup entry if exists
    bg = db.query(BudgetGroup).filter(
        BudgetGroup.user_id == current_user.id,
        BudgetGroup.name == old_grp,
    ).first()
    if bg:
        bg.name = new_grp
        if req.is_sinking_fund is not None:
            bg.is_sinking_fund = req.is_sinking_fund

    q = db.query(Budget).filter(Budget.user_id == current_user.id, Budget.group_type == old_grp)
    if req.month_key:
        q = q.filter(Budget.month_key == normalize_month_key(req.month_key))

    rows = q.all()
    for b in rows:
        b.group_type = new_grp
        if req.is_sinking_fund is not None:
            b.is_sinking_fund = req.is_sinking_fund
        elif is_sinking_group(new_grp):
            b.is_sinking_fund = True
    db.commit()
    return {"updated_count": len(rows), "group_type": new_grp}


@router.post("/copy-month")
def copy_budgets_from_previous_month(
    req: CopyMonthRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Copies monthly budget template from source_month (default: month before target_month) into target_month.
    Regular items start fresh at 0; Sinking Fund items carry over accumulated balance into rollover_balance!
    """
    target_mk = normalize_month_key(req.target_month)
    source_mk = normalize_month_key(req.source_month) if req.source_month else previous_month_key(target_mk)

    source_budgets = (
        db.query(Budget)
        .filter(Budget.user_id == current_user.id, Budget.month_key == source_mk)
        .order_by(Budget.sort_order.asc(), Budget.created_at.asc())
        .all()
    )
    if not source_budgets:
        raise HTTPException(status_code=404, detail=f"Tidak ada pos anggaran pada bulan sumber ({source_mk})")

    transactions = db.query(Transaction).filter(Transaction.user_id == current_user.id).all()
    source_spent_map = compute_budget_spent_map(source_budgets, transactions, source_mk)

    if req.overwrite:
        db.query(Budget).filter(Budget.user_id == current_user.id, Budget.month_key == target_mk).delete()
        db.flush()

    existing_target = db.query(Budget).filter(Budget.user_id == current_user.id, Budget.month_key == target_mk).all()
    existing_keys = {
        ((b.group_type or "").upper(), (b.name or "").strip().lower())
        for b in existing_target
    }

    copied_count = 0
    for src in source_budgets:
        key = ((src.group_type or "LIVING NEEDS").upper(), (src.name or "").strip().lower())
        if key in existing_keys:
            continue

        prev_spent = source_spent_map.get(src.id, 0.0)
        new_rollover = 0.0
        if src.is_sinking_fund:
            new_rollover = max(
                0.0,
                float(src.rollover_balance or 0.0) + float(src.funded_this_month or 0.0) - prev_spent,
            )

        cloned = Budget(
            user_id=current_user.id,
            category_id=src.category_id,
            wallet_id=src.wallet_id,
            name=src.name,
            group_type=src.group_type,
            remark=src.remark,
            limit_amount=src.limit_amount,
            period=src.period,
            month_key=target_mk,
            is_sinking_fund=bool(src.is_sinking_fund),
            rollover_balance=round(new_rollover, 2),
            funded_this_month=0.0,
            sort_order=src.sort_order or 0,
        )
        db.add(cloned)
        copied_count += 1

    db.commit()
    return {
        "copied_count": copied_count,
        "source_month": source_mk,
        "target_month": target_mk,
        "allocation": compute_monthly_allocation_data(current_user, db, target_mk),
    }


@router.post("/distribute-payday")
def distribute_payday_allocations(
    req: DistributePaydayRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Executes batch TRANSFER transactions from payroll/source wallet to each Fund Location wallet,
    and optionally marks Sinking Fund items in those destination wallets as funded for the month.
    """
    mk = normalize_month_key(req.month_key)
    source_wallet = db.query(Wallet).filter(
        Wallet.id == req.source_wallet_id,
        Wallet.user_id == current_user.id,
        Wallet.is_archived == False,
    ).first()
    if not source_wallet:
        raise HTTPException(status_code=404, detail="Dompet sumber gaji tidak ditemukan")

    alloc_snapshot = compute_monthly_allocation_data(current_user, db, mk)

    planned_transfers: List[PaydayTransferItem] = []
    if req.transfers is not None:
        planned_transfers = [t for t in req.transfers if t.amount > 0 and t.to_wallet_id != source_wallet.id]
    else:
        for wa in alloc_snapshot["wallet_allocations"]:
            if wa["wallet_id"] == source_wallet.id:
                continue
            amt = wa["shortfall_amount"] if req.mode.upper() == "SHORTFALL" else wa["total_monthly_budget"]
            if amt > 0:
                planned_transfers.append(PaydayTransferItem(to_wallet_id=wa["wallet_id"], amount=amt))

    executed: List[Dict[str, Any]] = []
    funded_wallet_ids = {source_wallet.id}

    for item in planned_transfers:
        dest_w = db.query(Wallet).filter(
            Wallet.id == item.to_wallet_id,
            Wallet.user_id == current_user.id,
            Wallet.is_archived == False,
        ).first()
        if not dest_w or item.amount <= 0:
            continue

        source_wallet.balance -= item.amount
        dest_w.balance += item.amount
        funded_wallet_ids.add(dest_w.id)

        tx = Transaction(
            user_id=current_user.id,
            wallet_id=source_wallet.id,
            to_wallet_id=dest_w.id,
            type="TRANSFER",
            amount=round(item.amount, 2),
            currency=source_wallet.currency,
            amount_in_base=round(item.amount, 2),
            description=f"Distribusi Gajian ({mk}) ke {dest_w.name}",
            raw_source="WEB",
            transaction_date=datetime.now(timezone.utc),
        )
        db.add(tx)
        executed.append({
            "to_wallet_id": dest_w.id,
            "to_wallet_name": dest_w.name,
            "amount": round(item.amount, 2),
        })

    if req.auto_fund_sinking:
        sinking_rows = db.query(Budget).filter(
            Budget.user_id == current_user.id,
            Budget.month_key == mk,
            Budget.is_sinking_fund == True,
            Budget.wallet_id.in_(list(funded_wallet_ids)),
        ).all()
        for sb in sinking_rows:
            if (sb.funded_this_month or 0.0) < sb.limit_amount:
                sb.funded_this_month = sb.limit_amount

    db.commit()
    return {
        "message": f"Distribusi gajian berhasil dieksekusi ke {len(executed)} dompet",
        "transfers_executed": executed,
        "allocation": compute_monthly_allocation_data(current_user, db, mk),
    }


@router.post("/{budget_id}/record")
def record_budget_action(
    budget_id: str,
    req: RecordBudgetActionRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    1-click action on a budget row:
    - mode="EXPENSE": logs an EXPENSE linked to this budget_id and deducts its Fund Location wallet.
    - mode="FUND_SINKING": marks/adds funded_this_month on a Sinking Fund item.
    """
    budget = db.query(Budget).filter(Budget.id == budget_id, Budget.user_id == current_user.id).first()
    if not budget:
        raise HTTPException(status_code=404, detail="Pos anggaran tidak ditemukan")

    mode = req.mode.strip().upper()
    amt = req.amount if (req.amount is not None and req.amount > 0) else budget.limit_amount
    if amt <= 0:
        raise HTTPException(status_code=400, detail="Nominal harus lebih besar dari 0")

    if mode == "FUND_SINKING":
        budget.is_sinking_fund = True
        budget.funded_this_month = round(amt, 2)
        db.commit()
        db.refresh(budget)
        transactions = db.query(Transaction).filter(Transaction.user_id == current_user.id).all()
        mk = budget.month_key or get_current_month_key()
        spent_map = compute_budget_spent_map([budget], transactions, mk)
        return {
            "mode": "FUND_SINKING",
            "item": serialize_budget_item(budget, spent_map.get(budget.id, 0.0)),
        }

    # EXPENSE mode
    target_wallet_id = req.wallet_id or budget.wallet_id
    target_wallet = None
    if target_wallet_id:
        target_wallet = db.query(Wallet).filter(
            Wallet.id == target_wallet_id,
            Wallet.user_id == current_user.id,
            Wallet.is_archived == False,
        ).first()
    if not target_wallet:
        target_wallet = (
            db.query(Wallet)
            .filter(Wallet.user_id == current_user.id, Wallet.is_archived == False)
            .order_by(Wallet.is_default.desc(), Wallet.created_at.asc())
            .first()
        )
    if not target_wallet:
        raise HTTPException(status_code=400, detail="Buat minimal satu dompet terlebih dahulu untuk mencatat pengeluaran")

    target_wallet.balance -= amt
    item_label = budget.name or (budget.category.name if budget.category else "Pos Anggaran")

    tx = Transaction(
        user_id=current_user.id,
        wallet_id=target_wallet.id,
        category_id=budget.category_id,
        budget_id=budget.id,
        type="EXPENSE",
        amount=round(amt, 2),
        currency=target_wallet.currency,
        amount_in_base=round(amt, 2),
        description=(req.description or "").strip() or f"Realisasi {item_label}",
        raw_source="WEB",
        transaction_date=datetime.now(timezone.utc),
    )
    db.add(tx)
    db.commit()
    db.refresh(budget)

    transactions = db.query(Transaction).filter(Transaction.user_id == current_user.id).all()
    mk = budget.month_key or get_current_month_key()
    spent_map = compute_budget_spent_map([budget], transactions, mk)
    return {
        "mode": "EXPENSE",
        "transaction_id": tx.id,
        "wallet_balance": round(target_wallet.balance, 2),
        "item": serialize_budget_item(budget, spent_map.get(budget.id, 0.0)),
    }


# ==================== CORE CRUD ENDPOINTS ====================


@router.get("")
def list_budgets(
    month: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    mk = normalize_month_key(month)
    budgets = (
        db.query(Budget)
        .filter(Budget.user_id == current_user.id, Budget.month_key == mk)
        .order_by(Budget.sort_order.asc(), Budget.created_at.asc())
        .all()
    )
    transactions = db.query(Transaction).filter(Transaction.user_id == current_user.id).all()
    spent_map = compute_budget_spent_map(budgets, transactions, mk)
    return [serialize_budget_item(b, spent_map.get(b.id, 0.0)) for b in budgets]


@router.post("")
def create_budget(
    req: CreateBudgetRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if req.limit_amount < 0:
        raise HTTPException(status_code=400, detail="Nominal anggaran tidak boleh negatif")

    mk = normalize_month_key(req.month_key)
    grp = (req.group_type or "LIVING NEEDS").strip().upper() or "LIVING NEEDS"

    wallet_id = req.wallet_id or None
    if wallet_id:
        wallet = db.query(Wallet).filter(Wallet.id == wallet_id, Wallet.user_id == current_user.id).first()
        if not wallet:
            raise HTTPException(status_code=404, detail="Dompet Fund Location tidak ditemukan")

    # Determine item name & category
    raw_name = (req.name or "").strip()
    cat = resolve_auto_category(db, current_user.id, raw_name, grp, req.category_id)
    if not raw_name:
        if not cat:
            raise HTTPException(status_code=400, detail="Nama pos anggaran wajib diisi")
        raw_name = cat.name

    # Legacy behavior if caller only passed category_id without name: update existing row for that category in mk
    if not req.name and req.category_id:
        existing = db.query(Budget).filter(
            Budget.user_id == current_user.id,
            Budget.month_key == mk,
            Budget.category_id == req.category_id,
            Budget.name == raw_name,
        ).first()
        if existing:
            existing.limit_amount = req.limit_amount
            if wallet_id is not None:
                existing.wallet_id = wallet_id
            db.commit()
            db.refresh(existing)
            transactions = db.query(Transaction).filter(Transaction.user_id == current_user.id).all()
            spent_map = compute_budget_spent_map([existing], transactions, mk)
            return serialize_budget_item(existing, spent_map.get(existing.id, 0.0))

    sinking = req.is_sinking_fund if req.is_sinking_fund is not None else is_sinking_group(grp)
    if req.sort_order is not None:
        sort_order = req.sort_order
    else:
        count_in_group = db.query(Budget).filter(
            Budget.user_id == current_user.id,
            Budget.month_key == mk,
            Budget.group_type == grp,
        ).count()
        sort_order = count_in_group + 1

    budget = Budget(
        user_id=current_user.id,
        category_id=cat.id if cat else None,
        wallet_id=wallet_id,
        name=raw_name,
        group_type=grp,
        remark=(req.remark or "").strip() or None,
        limit_amount=req.limit_amount,
        period=req.period.upper(),
        month_key=mk,
        is_sinking_fund=bool(sinking),
        rollover_balance=req.rollover_balance or 0.0,
        funded_this_month=req.funded_this_month or 0.0,
        sort_order=sort_order,
    )
    db.add(budget)
    db.commit()
    db.refresh(budget)

    transactions = db.query(Transaction).filter(Transaction.user_id == current_user.id).all()
    spent_map = compute_budget_spent_map([budget], transactions, mk)
    return serialize_budget_item(budget, spent_map.get(budget.id, 0.0))


@router.put("/{budget_id}")
def update_budget(
    budget_id: str,
    req: UpdateBudgetRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    budget = db.query(Budget).filter(Budget.id == budget_id, Budget.user_id == current_user.id).first()
    if not budget:
        raise HTTPException(status_code=404, detail="Pos anggaran tidak ditemukan")

    payload = req.model_dump(exclude_unset=True)
    if "name" in payload and payload["name"] is not None:
        clean_name = payload["name"].strip()
        if clean_name:
            budget.name = clean_name
    if "group_type" in payload and payload["group_type"] is not None:
        clean_grp = payload["group_type"].strip().upper()
        if clean_grp:
            budget.group_type = clean_grp
            if "is_sinking_fund" not in payload and is_sinking_group(clean_grp):
                budget.is_sinking_fund = True
    if "limit_amount" in payload and payload["limit_amount"] is not None:
        budget.limit_amount = max(0.0, float(payload["limit_amount"]))
    if "remark" in payload:
        budget.remark = (payload["remark"] or "").strip() or None
    if "wallet_id" in payload:
        wid = payload["wallet_id"] or None
        if wid:
            w = db.query(Wallet).filter(Wallet.id == wid, Wallet.user_id == current_user.id).first()
            if not w:
                raise HTTPException(status_code=404, detail="Dompet Fund Location tidak ditemukan")
        budget.wallet_id = wid
    if "category_id" in payload:
        cid = payload["category_id"] or None
        if cid:
            cat = db.query(Category).filter(
                Category.id == cid,
                (Category.is_system == True) | (Category.user_id == current_user.id),
            ).first()
            if not cat:
                raise HTTPException(status_code=404, detail="Kategori tidak ditemukan")
        budget.category_id = cid
    if "is_sinking_fund" in payload and payload["is_sinking_fund"] is not None:
        budget.is_sinking_fund = bool(payload["is_sinking_fund"])
    if "rollover_balance" in payload and payload["rollover_balance"] is not None:
        budget.rollover_balance = max(0.0, float(payload["rollover_balance"]))
    if "funded_this_month" in payload and payload["funded_this_month"] is not None:
        budget.funded_this_month = max(0.0, float(payload["funded_this_month"]))
    if "sort_order" in payload and payload["sort_order"] is not None:
        budget.sort_order = int(payload["sort_order"])

    db.commit()
    db.refresh(budget)

    mk = budget.month_key or get_current_month_key()
    transactions = db.query(Transaction).filter(Transaction.user_id == current_user.id).all()
    spent_map = compute_budget_spent_map([budget], transactions, mk)
    return serialize_budget_item(budget, spent_map.get(budget.id, 0.0))


@router.delete("/{budget_id}")
def delete_budget(budget_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    budget = db.query(Budget).filter(Budget.id == budget_id, Budget.user_id == current_user.id).first()
    if not budget:
        raise HTTPException(status_code=404, detail="Budget not found")
    db.delete(budget)
    db.commit()
    return {"message": "Budget deleted successfully"}
