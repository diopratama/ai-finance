"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  Plus,
  Target,
  Layers,
  ArrowRightLeft,
  ArrowLeftRight,
  Copy,
  ChevronLeft,
  ChevronRight,
  CheckCircle2,
  AlertTriangle,
  Wallet as WalletIcon,
  Sparkles,
  Edit2,
  Trash2,
  Check,
  TrendingDown,
  PiggyBank,
  FolderPlus,
  Coins,
  Settings2,
  Folder,
  AlertCircle,
  X,
} from "lucide-react";
import {
  getBudgetAllocation,
  getWallets,
  getCategories,
  createBudget,
  updateBudget,
  deleteBudget,
  renameBudgetGroup,
  copyPreviousMonthBudgets,
  distributePaydayToWallets,
  recordBudgetAction,
  updateReferenceIncome,
  createWallet,
  createCustomCategory,
  getBudgetGroups,
  createBudgetGroup,
  updateBudgetGroup,
  deleteBudgetGroup,
} from "@/lib/api";
import {
  Budget,
  MonthlyAllocationResponse,
  Wallet,
  Category,
  BudgetGroupSummary,
  WalletAllocationSummary,
  BudgetGroupItem,
} from "@/lib/types";
import { formatCurrency } from "@/lib/utils";

function getMonthNameID(monthKey: string): string {
  const [y, m] = monthKey.split("-");
  const monthNames = [
    "Januari", "Februari", "Maret", "April", "Mei", "Juni",
    "Juli", "Agustus", "September", "Oktober", "November", "Desember",
  ];
  const idx = parseInt(m, 10) - 1;
  return `${monthNames[idx] || m} ${y}`;
}

function shiftMonth(monthKey: string, delta: number): string {
  const [y, m] = monthKey.split("-").map(Number);
  const d = new Date(Date.UTC(y, m - 1 + delta, 1));
  return d.toISOString().slice(0, 7);
}

export default function BudgetsAllocationPage() {
  const [monthKey, setMonthKey] = useState<string>(() => new Date().toISOString().slice(0, 7));
  const [allocation, setAllocation] = useState<MonthlyAllocationResponse | null>(null);
  const [wallets, setWallets] = useState<Wallet[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [viewMode, setViewMode] = useState<"table" | "cards">("table");

  // Modals state
  const [showItemModal, setShowItemModal] = useState<boolean>(false);
  const [editingItem, setEditingItem] = useState<Budget | null>(null);
  const [showPaydayModal, setShowPaydayModal] = useState<boolean>(false);
  const [showIncomeModal, setShowIncomeModal] = useState<boolean>(false);
  const [showRenameGroupModal, setShowRenameGroupModal] = useState<string | null>(null);
  const [showCustomCatModal, setShowCustomCatModal] = useState<boolean>(false);
  const [showQuickWalletModal, setShowQuickWalletModal] = useState<boolean>(false);
  const [recordActionModal, setRecordActionModal] = useState<{
    item: Budget;
    mode: "EXPENSE" | "FUND_SINKING" | "TRANSFER_ALLOCATION";
  } | null>(null);
  const [actionSourceWalletId, setActionSourceWalletId] = useState("");

  // Group Management States
  const [budgetGroups, setBudgetGroups] = useState<BudgetGroupItem[]>([]);
  const [showManageGroupsModal, setShowManageGroupsModal] = useState<boolean>(false);
  const [showAddGroupModal, setShowAddGroupModal] = useState<boolean>(false);
  const [editingGroup, setEditingGroup] = useState<BudgetGroupItem | null>(null);
  const [editingGroupName, setEditingGroupName] = useState<string>("");
  const [editingGroupIsSinking, setEditingGroupIsSinking] = useState<boolean>(false);
  const [deletingGroup, setDeletingGroup] = useState<(BudgetGroupItem & { items_count: number }) | null>(null);
  const [deleteAction, setDeleteAction] = useState<"reassign" | "cascade">("reassign");
  const [deleteReassignToId, setDeleteReassignToId] = useState<string>("");
  const [groupFormName, setGroupFormName] = useState<string>("");
  const [groupFormIsSinking, setGroupFormIsSinking] = useState<boolean>(false);

  // Form states - Budget Item
  const [formName, setFormName] = useState("");
  const [formGroup, setFormGroup] = useState("LIVING NEEDS");
  const [formLimit, setFormLimit] = useState("");
  const [formRemark, setFormRemark] = useState("");
  const [formWalletId, setFormWalletId] = useState("");
  const [formCategoryId, setFormCategoryId] = useState("");
  const [formIsSinking, setFormIsSinking] = useState(false);

  // Form state - Reference Income
  const [referenceIncomeInput, setReferenceIncomeInput] = useState("");

  // Form state - Rename Group
  const [newGroupName, setNewGroupName] = useState("");

  // Form state - Payday Distribution
  const [sourceWalletId, setSourceWalletId] = useState("");
  const [paydayMode, setPaydayMode] = useState<"SHORTFALL" | "FULL_BUDGET">("SHORTFALL");
  const [autoFundSinking, setAutoFundSinking] = useState(true);

  // Form state - Quick Category
  const [customCatName, setCustomCatName] = useState("");
  const [customCatType, setCustomCatType] = useState<"EXPENSE" | "INCOME">("EXPENSE");

  // Form state - Quick Wallet
  const [quickWalletName, setQuickWalletName] = useState("");
  const [quickWalletType, setQuickWalletType] = useState("BANK");

  // Form state - Record action
  const [actionAmount, setActionAmount] = useState("");
  const [actionDesc, setActionDesc] = useState("");
  const [actionWalletId, setActionWalletId] = useState("");

  // Inline add state per group
  const [inlineGroup, setInlineGroup] = useState<string | null>(null);
  const [inlineName, setInlineName] = useState("");
  const [inlineLimit, setInlineLimit] = useState("");
  const [inlineWalletId, setInlineWalletId] = useState("");

  const refreshData = async (targetMonth = monthKey) => {
    setLoading(true);
    try {
      const [allocRes, wRes, cRes, gRes] = await Promise.all([
        getBudgetAllocation(targetMonth),
        getWallets(targetMonth),
        getCategories(),
        getBudgetGroups(),
      ]);
      setAllocation(allocRes);
      setWallets(wRes.wallets);
      setCategories(cRes);
      setBudgetGroups(gRes);
      setReferenceIncomeInput(allocRes.reference_income.toString());
      if (wRes.wallets.length > 0 && !sourceWalletId) {
        setSourceWalletId(wRes.wallets[0].id);
      }
    } catch (err) {
      console.error("Failed loading budget allocation:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refreshData(monthKey);
  }, [monthKey]);

  // Group Action Handlers
  const handleCreateGroup = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!groupFormName.trim()) return;
    try {
      const created = await createBudgetGroup({
        name: groupFormName.trim().toUpperCase(),
        is_sinking_fund: groupFormIsSinking,
      });
      setGroupFormName("");
      setGroupFormIsSinking(false);
      setShowAddGroupModal(false);
      setFormGroup(created.name);
      if (created.is_sinking_fund) setFormIsSinking(true);
      await refreshData(monthKey);
    } catch (err: any) {
      alert(err.message || "Gagal membuat grup baru");
    }
  };

  const handleUpdateGroup = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editingGroup || !editingGroupName.trim()) return;
    try {
      await updateBudgetGroup(editingGroup.id, {
        name: editingGroupName.trim().toUpperCase(),
        is_sinking_fund: editingGroupIsSinking,
      });
      setEditingGroup(null);
      await refreshData(monthKey);
    } catch (err: any) {
      alert(err.message || "Gagal memperbarui grup");
    }
  };

  const handleDeleteGroup = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!deletingGroup) return;
    try {
      await deleteBudgetGroup(deletingGroup.id, {
        action: deleteAction,
        reassign_to_id: deleteAction === "reassign" ? deleteReassignToId : undefined,
      });
      setDeletingGroup(null);
      await refreshData(monthKey);
    } catch (err: any) {
      alert(err.message || "Gagal menghapus grup");
    }
  };

  const handleStartEditGroup = (groupType: string) => {
    const found = budgetGroups.find((g) => g.name.toUpperCase() === groupType.toUpperCase());
    if (found) {
      setEditingGroup(found);
      setEditingGroupName(found.name);
      setEditingGroupIsSinking(found.is_sinking_fund);
    } else {
      setShowRenameGroupModal(groupType);
      setNewGroupName(groupType);
    }
  };

  const handleStartDeleteGroup = (groupType: string, itemsCount = 0) => {
    const found = budgetGroups.find((g) => g.name.toUpperCase() === groupType.toUpperCase());
    if (found) {
      setDeletingGroup({ ...found, items_count: itemsCount });
      const otherGroup = budgetGroups.find((g) => g.id !== found.id);
      if (otherGroup) setDeleteReassignToId(otherGroup.id);
      setDeleteAction("reassign");
    } else {
      alert("Grup ini merupakan grup bawaan sementara dan dapat dikelola setelah dibuat di daftar grup.");
    }
  };

  const handleOpenNewItem = (defaultGroup = "LIVING NEEDS") => {
    setEditingItem(null);
    setFormName("");
    setFormGroup(defaultGroup);
    setFormLimit("");
    setFormRemark(defaultGroup === "PREDICTABLE SAVING" ? "Sinking Fund" : "");
    setFormWalletId(wallets[0]?.id || "");
    setFormCategoryId("");
    setFormIsSinking(defaultGroup === "PREDICTABLE SAVING");
    setShowItemModal(true);
  };

  const handleEditItem = (item: Budget) => {
    setEditingItem(item);
    setFormName(item.name);
    setFormGroup(item.group_type);
    setFormLimit(item.limit_amount.toString());
    setFormRemark(item.remark || "");
    setFormWalletId(item.wallet_id || "");
    setFormCategoryId(item.category_id || "");
    setFormIsSinking(item.is_sinking_fund);
    setShowItemModal(true);
  };

  const handleSaveItem = async (e: React.FormEvent) => {
    e.preventDefault();
    const limit = parseFloat(formLimit);
    if (!formName.trim() || isNaN(limit) || limit < 0) return;

    if (editingItem) {
      await updateBudget(editingItem.id, {
        name: formName.trim(),
        group_type: formGroup.trim().toUpperCase(),
        limit_amount: limit,
        remark: formRemark.trim() || undefined,
        wallet_id: formWalletId || null,
        category_id: formCategoryId || null,
        is_sinking_fund: formIsSinking,
      });
    } else {
      await createBudget({
        name: formName.trim(),
        group_type: formGroup.trim().toUpperCase(),
        limit_amount: limit,
        remark: formRemark.trim() || undefined,
        wallet_id: formWalletId || null,
        category_id: formCategoryId || null,
        month_key: monthKey,
        is_sinking_fund: formIsSinking,
      });
    }

    setShowItemModal(false);
    refreshData(monthKey);
  };

  const handleInlineAdd = async (groupName: string) => {
    const limit = parseFloat(inlineLimit);
    if (!inlineName.trim() || isNaN(limit) || limit <= 0) return;

    await createBudget({
      name: inlineName.trim(),
      group_type: groupName.trim().toUpperCase(),
      limit_amount: limit,
      wallet_id: inlineWalletId || (wallets[0]?.id || null),
      month_key: monthKey,
      is_sinking_fund: groupName.toUpperCase() === "PREDICTABLE SAVING",
    });

    setInlineName("");
    setInlineLimit("");
    setInlineGroup(null);
    refreshData(monthKey);
  };

  const handleDeleteItem = async (id: string) => {
    if (confirm("Hapus baris alokasi anggaran ini?")) {
      await deleteBudget(id);
      refreshData(monthKey);
    }
  };

  const handleCopyMonth = async () => {
    if (confirm(`Salin template anggaran dari bulan sebelumnya ke ${getMonthNameID(monthKey)}? Sinking Fund akan otomatis mengakumulasi saldo tersisa!`)) {
      await copyPreviousMonthBudgets({ target_month: monthKey });
      refreshData(monthKey);
    }
  };

  const handleSaveIncome = async (e: React.FormEvent) => {
    e.preventDefault();
    const amt = parseFloat(referenceIncomeInput);
    if (isNaN(amt) || amt < 0) return;
    await updateReferenceIncome(amt);
    setShowIncomeModal(false);
    refreshData(monthKey);
  };

  const handleRenameGroup = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!showRenameGroupModal || !newGroupName.trim()) return;
    await renameBudgetGroup({
      old_group_type: showRenameGroupModal,
      new_group_type: newGroupName.trim().toUpperCase(),
      month_key: monthKey,
    });
    setShowRenameGroupModal(null);
    setNewGroupName("");
    refreshData(monthKey);
  };

  const handleExecutePayday = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!sourceWalletId) return;
    await distributePaydayToWallets({
      source_wallet_id: sourceWalletId,
      month_key: monthKey,
      mode: paydayMode,
      auto_fund_sinking: autoFundSinking,
    });
    setShowPaydayModal(false);
    refreshData(monthKey);
  };

  const handleExecuteAction = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!recordActionModal) return;
    const amt = parseFloat(actionAmount);
    await recordBudgetAction(recordActionModal.item.id, {
      mode: recordActionModal.mode,
      amount: !isNaN(amt) && amt > 0 ? amt : undefined,
      wallet_id: actionWalletId || recordActionModal.item.wallet_id || undefined,
      source_wallet_id: recordActionModal.mode === "TRANSFER_ALLOCATION" ? (actionSourceWalletId || undefined) : undefined,
      description: actionDesc.trim() || undefined,
    });
    setRecordActionModal(null);
    setActionAmount("");
    setActionDesc("");
    setActionSourceWalletId("");
    refreshData(monthKey);
  };

  const handleCreateCustomCat = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!customCatName.trim()) return;
    const newCat = await createCustomCategory({
      name: customCatName.trim(),
      type: customCatType,
      color: "#f0b000",
      icon: "tag",
    });
    setFormCategoryId(newCat.id);
    setCustomCatName("");
    setShowCustomCatModal(false);
    const updated = await getCategories();
    setCategories(updated);
  };

  const handleCreateQuickWallet = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!quickWalletName.trim()) return;
    const newW = await createWallet({
      name: quickWalletName.trim(),
      type: quickWalletType.trim().toUpperCase(),
      balance: 0,
      currency: "IDR",
      color: "#f0b000",
    });
    setFormWalletId(newW.id);
    setQuickWalletName("");
    setShowQuickWalletModal(false);
    const updated = await getWallets(monthKey);
    setWallets(updated.wallets);
  };

  return (
    <div className="space-y-8 max-w-7xl mx-auto">
      {/* Top Header & Navigation */}
      <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-bold tracking-tight text-foreground">
              Alokasi Anggaran Bulanan
            </h1>
            <span className="text-[10px] uppercase font-bold bg-accent text-[#8a6300] dark:text-[#f0b000] border border-[#f0b000]/30 px-2 py-0.5 rounded">
              Zero-Based &bull; Fund Location
            </span>
          </div>
          <p className="text-xs sm:text-sm text-muted-foreground mt-1">
            Model alokasi gaji bulanan bergaya <em>spreadsheet</em>: hubungkan pos belanja &amp; Sinking Fund ke dompet nyata Anda.
          </p>
        </div>

        {/* Month Selector + View Switcher + Primary Actions */}
        <div className="flex flex-wrap items-center gap-2.5">
          {/* Month Stepper */}
          <div className="flex items-center rounded-xl bg-card border border-border p-1 shadow-sm">
            <button
              type="button"
              onClick={() => setMonthKey((prev) => shiftMonth(prev, -1))}
              className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-secondary transition-colors"
              title="Bulan Sebelumnya"
            >
              <ChevronLeft className="w-4 h-4" />
            </button>
            <span className="px-3 text-xs font-bold text-foreground font-mono">
              {getMonthNameID(monthKey)}
            </span>
            <button
              type="button"
              onClick={() => setMonthKey((prev) => shiftMonth(prev, 1))}
              className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-secondary transition-colors"
              title="Bulan Berikutnya"
            >
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>

          {/* Copy from Previous Month */}
          <button
            type="button"
            onClick={handleCopyMonth}
            className="flex items-center gap-1.5 px-3 py-2 rounded-xl text-xs font-semibold bg-card border border-border hover:bg-accent text-foreground transition-colors shadow-sm"
            title="Salin template pos dari bulan lalu"
          >
            <Copy className="w-3.5 h-3.5 text-[#8a6300] dark:text-[#f0b000]" />
            <span className="hidden sm:inline">Salin Bulan Lalu</span>
          </button>

          {/* View Toggle */}
          <div className="grid grid-cols-2 p-1 rounded-xl bg-secondary border border-border text-xs font-semibold">
            <button
              type="button"
              onClick={() => setViewMode("table")}
              className={`px-3 py-1 rounded-lg transition-colors ${
                viewMode === "table"
                  ? "bg-primary text-primary-foreground font-bold shadow-sm"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              Tabel Spreadsheet
            </button>
            <button
              type="button"
              onClick={() => setViewMode("cards")}
              className={`px-3 py-1 rounded-lg transition-colors ${
                viewMode === "cards"
                  ? "bg-primary text-primary-foreground font-bold shadow-sm"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              Kartu Visual
            </button>
          </div>

          {/* Manage Groups Button */}
          <button
            type="button"
            onClick={() => setShowManageGroupsModal(true)}
            className="flex items-center gap-1.5 px-3 py-2 rounded-xl text-xs font-semibold bg-card border border-border hover:bg-accent text-foreground transition-colors shadow-sm"
            title="Kelola Grup TYPE (Tambah, Edit, Hapus)"
          >
            <Settings2 className="w-3.5 h-3.5 text-[#8a6300] dark:text-[#f0b000]" />
            <span className="hidden sm:inline">Kelola Grup</span>
          </button>

          {/* Payday Assistant Button */}
          <button
            type="button"
            onClick={() => setShowPaydayModal(true)}
            className="flex items-center gap-1.5 px-3.5 py-2 rounded-xl text-xs font-bold bg-accent hover:bg-[#f0b000]/25 text-[#8a6300] dark:text-[#f0b000] border border-[#f0b000]/40 transition-colors shadow-sm"
          >
            <Sparkles className="w-3.5 h-3.5" />
            <span>⚡ Distribusi Gajian</span>
          </button>

          {/* New Item Button */}
          <button
            type="button"
            onClick={() => handleOpenNewItem("LIVING NEEDS")}
            className="flex items-center gap-1.5 px-4 py-2 rounded-xl text-xs font-bold bg-primary hover:bg-primary/90 text-primary-foreground transition-colors shadow-md shadow-[#f0b000]/20"
          >
            <Plus className="w-4 h-4" />
            <span>+ Pos Anggaran</span>
          </button>
        </div>
      </div>

      {/* Stats Bar */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Reference Income */}
        <div className="p-4 rounded-2xl bg-card border border-border shadow-sm flex items-center justify-between">
          <div>
            <span className="text-[11px] font-medium text-muted-foreground uppercase tracking-wider">
              Penghasilan Acuan Bulan Ini
            </span>
            <div className="text-xl font-bold text-foreground mt-0.5">
              {formatCurrency(allocation?.reference_income || 0, "IDR")}
            </div>
            <span className="text-[10px] text-muted-foreground">
              Sumber: {allocation?.income_source === "PROFILE" ? "Profil Finansial" : allocation?.income_source === "TRANSACTIONS" ? "Pemasukan Riil" : "Belum diatur"}
            </span>
          </div>
          <button
            type="button"
            onClick={() => setShowIncomeModal(true)}
            className="p-2 rounded-xl bg-secondary hover:bg-accent text-foreground text-xs font-semibold border border-border"
            title="Ubah Angka Gaji Acuan"
          >
            <Settings2 className="w-4 h-4 text-[#8a6300] dark:text-[#f0b000]" />
          </button>
        </div>

        {/* Total Budget */}
        <div className="p-4 rounded-2xl bg-card border border-border shadow-sm">
          <span className="text-[11px] font-medium text-muted-foreground uppercase tracking-wider">
            Total Anggaran Teralokasi
          </span>
          <div className="text-xl font-bold text-foreground mt-0.5">
            {formatCurrency(allocation?.totals.total_budget || 0, "IDR")}
          </div>
          <span className="text-[11px] text-[#8a6300] dark:text-[#f0b000] font-semibold">
            {allocation?.totals.allocated_percentage || 0}% dari Penghasilan
          </span>
        </div>

        {/* Realization / Spent */}
        <div className="p-4 rounded-2xl bg-card border border-border shadow-sm">
          <span className="text-[11px] font-medium text-muted-foreground uppercase tracking-wider">
            Realisasi Pengeluaran
          </span>
          <div className="text-xl font-bold text-rose-600 dark:text-rose-400 mt-0.5">
            {formatCurrency(allocation?.totals.total_spent || 0, "IDR")}
          </div>
          <span className="text-[10px] text-muted-foreground">
            Sisa Budget Belum Terpakai: {formatCurrency(allocation?.totals.total_remaining || 0, "IDR")}
          </span>
        </div>

        {/* Unallocated Income */}
        <div className="p-4 rounded-2xl bg-card border border-border shadow-sm">
          <span className="text-[11px] font-medium text-muted-foreground uppercase tracking-wider">
            Sisa Gaji Belum Teralokasi
          </span>
          <div className={`text-xl font-bold mt-0.5 ${
            (allocation?.totals.unallocated_income || 0) < 0
              ? "text-rose-600 dark:text-rose-400"
              : "text-emerald-600 dark:text-emerald-400"
          }`}>
            {formatCurrency(allocation?.totals.unallocated_income || 0, "IDR")}
          </div>
          <span className="text-[10px] text-muted-foreground">
            {(allocation?.totals.unallocated_income || 0) === 0
              ? "🎯 Zero-Based Budgeting Sempurna!"
              : (allocation?.totals.unallocated_income || 0) > 0
              ? "Alokasikan ke Sinking Fund atau Investasi"
              : "⚠️ Anggaran melebihi total penghasilan"}
          </span>
        </div>
      </div>

      {/* Fund Location (Dompet Terhubung) Sufficiency Bar */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <WalletIcon className="w-4 h-4 text-[#8a6300] dark:text-[#f0b000]" />
            <h2 className="text-sm font-bold text-foreground">
              Rekap Kebutuhan per Dompet (Fund Location)
            </h2>
          </div>
          <Link
            href="/wallets"
            className="text-xs font-semibold text-[#8a6300] dark:text-[#f0b000] hover:underline"
          >
            Kelola Dompet &rarr;
          </Link>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          {allocation?.wallet_allocations.map((wa) => {
            const isShortfall = wa.status === "SHORTFALL";
            const isFunded = wa.status === "FUNDED";

            return (
              <div
                key={wa.wallet_id}
                className="p-4 rounded-2xl bg-card border border-border shadow-sm flex flex-col justify-between space-y-3"
              >
                <div className="flex items-start justify-between">
                  <div className="flex items-center gap-2.5">
                    <span
                      className="w-3.5 h-3.5 rounded-full shrink-0"
                      style={{ backgroundColor: wa.wallet_color }}
                    />
                    <div>
                      <div className="text-sm font-bold text-foreground">{wa.wallet_name}</div>
                      <div className="text-[10px] text-muted-foreground uppercase">{wa.wallet_type}</div>
                    </div>
                  </div>
                  <span
                    className={`text-[10px] font-bold px-2 py-0.5 rounded-full border ${
                      isShortfall
                        ? "bg-rose-500/10 text-rose-600 dark:text-rose-400 border-rose-500/30"
                        : isFunded
                        ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/30"
                        : "bg-secondary text-muted-foreground border-border"
                    }`}
                  >
                    {isShortfall ? "Kurang Saldo" : isFunded ? "Funded (Aman)" : "Idle"}
                  </span>
                </div>

                <div className="space-y-1 text-xs">
                  <div className="flex justify-between text-muted-foreground">
                    <span>Saldo Aktual:</span>
                    <strong className="text-foreground">{formatCurrency(wa.current_balance)}</strong>
                  </div>
                  <div className="flex justify-between text-muted-foreground">
                    <span>Alokasi Bulan Ini:</span>
                    <span className="font-semibold text-foreground">{formatCurrency(wa.total_monthly_budget)}</span>
                  </div>
                  {wa.sinking_fund_held > 0 && (
                    <div className="flex justify-between text-amber-700 dark:text-amber-400 text-[11px]">
                      <span>Sinking Fund Mengendap:</span>
                      <span className="font-semibold">{formatCurrency(wa.sinking_fund_held)}</span>
                    </div>
                  )}
                  {isShortfall && (
                    <div className="flex justify-between text-rose-600 dark:text-rose-400 font-bold pt-1 border-t border-border">
                      <span>Perlu Ditransfer:</span>
                      <span>+{formatCurrency(wa.shortfall_amount)}</span>
                    </div>
                  )}
                </div>

                {isShortfall && (
                  <button
                    type="button"
                    onClick={() => {
                      setShowPaydayModal(true);
                    }}
                    className="w-full py-1.5 rounded-lg bg-rose-500/10 hover:bg-rose-500/20 text-rose-600 dark:text-rose-400 border border-rose-500/30 text-[11px] font-bold transition-colors"
                  >
                    Transfer Kebutuhan Gajian
                  </button>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* Main Budget Structure: Spreadsheet Table View (Default) */}
      {viewMode === "table" ? (
        <div className="rounded-3xl bg-card border border-border shadow-sm overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs sm:text-sm">
              <thead className="bg-secondary/70 text-muted-foreground uppercase text-[11px] font-bold border-b border-border">
                <tr>
                  <th className="py-3 px-4">TYPE</th>
                  <th className="py-3 px-4">CATEGORY / POS</th>
                  <th className="py-3 px-4 text-right">BUDGET</th>
                  <th className="py-3 px-4 text-right">REALISASI / TERKUMPUL</th>
                  <th className="py-3 px-4">REMARK</th>
                  <th className="py-3 px-4">FUND LOCATION</th>
                  <th className="py-3 px-4 text-right">SUB TOTAL &amp; %</th>
                  <th className="py-3 px-4 text-center">AKSI</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {allocation?.groups.map((group) => {
                  const isSinkingGroup = group.is_sinking_fund_group;

                  return (
                    <tr key={group.group_type} className="contents">
                      {/* Group Header Row */}
                      <tr className="bg-secondary/40 font-bold border-t-2 border-border">
                        <td colSpan={2} className="py-3 px-4">
                          <div className="flex items-center gap-2">
                            <span className="text-xs uppercase tracking-wider text-[#8a6300] dark:text-[#f0b000]">
                              {group.group_type}
                            </span>
                            {isSinkingGroup && (
                              <span className="text-[10px] px-2 py-0.5 rounded-full bg-amber-500/10 text-amber-700 dark:text-amber-400 border border-amber-500/30">
                                Sinking Fund (Rollover)
                              </span>
                            )}
                            <button
                              type="button"
                              onClick={() => handleStartEditGroup(group.group_type)}
                              className="text-muted-foreground hover:text-foreground p-1 rounded hover:bg-secondary transition-colors"
                              title="Edit Grup TYPE"
                            >
                              <Edit2 className="w-3.5 h-3.5" />
                            </button>
                            <button
                              type="button"
                              onClick={() => handleStartDeleteGroup(group.group_type, group.items_count)}
                              className="text-muted-foreground hover:text-rose-500 p-1 rounded hover:bg-secondary transition-colors"
                              title="Hapus Grup TYPE"
                            >
                              <Trash2 className="w-3.5 h-3.5" />
                            </button>
                          </div>
                        </td>
                        <td className="py-3 px-4 text-right font-mono font-bold text-foreground">
                          {formatCurrency(group.subtotal_budget)}
                        </td>
                        <td className="py-3 px-4 text-right font-mono font-bold text-muted-foreground">
                          {isSinkingGroup
                            ? formatCurrency(group.subtotal_accumulated)
                            : formatCurrency(group.subtotal_spent)}
                        </td>
                        <td colSpan={2} className="py-3 px-4 text-xs text-muted-foreground">
                          {group.items_count} Pos Terdaftar
                        </td>
                        <td className="py-3 px-4 text-right font-mono font-bold text-[#8a6300] dark:text-[#f0b000]">
                          {formatCurrency(group.subtotal_budget)}
                          <div className="text-[10px] text-muted-foreground font-normal">
                            {group.income_percentage}% gaji
                          </div>
                        </td>
                        <td className="py-3 px-4 text-center">
                          <button
                            type="button"
                            onClick={() => {
                              setInlineGroup(group.group_type);
                              setInlineName("");
                              setInlineLimit("");
                              setInlineWalletId(wallets[0]?.id || "");
                            }}
                            className="px-2 py-1 rounded-lg bg-secondary hover:bg-accent text-[11px] font-semibold border border-border"
                          >
                            + Tambah Pos
                          </button>
                        </td>
                      </tr>

                      {/* Empty Group Notice */}
                      {group.items.length === 0 && (
                        <tr className="border-b border-border/50 text-muted-foreground text-xs italic">
                          <td colSpan={8} className="py-3 px-8 text-center text-muted-foreground">
                            Belum ada pos anggaran di grup ini. Gunakan tombol &quot;+ Tambah Pos&quot; di kanan untuk mulai.
                          </td>
                        </tr>
                      )}

                      {/* Group Item Rows */}
                      {group.items.map((item) => (
                        <tr key={item.id} className="hover:bg-secondary/30 transition-colors">
                          <td className="py-2.5 px-4 text-muted-foreground text-xs pl-8">
                            &bull;
                          </td>
                          <td className="py-2.5 px-4 font-semibold text-foreground">
                            <div className="flex items-center gap-2">
                              <span>{item.name}</span>
                              {item.is_sinking_fund && (
                                <span className="text-[9px] uppercase px-1.5 py-0.2 rounded bg-amber-500/10 text-amber-700 dark:text-amber-400 border border-amber-500/30">
                                  Sinking
                                </span>
                              )}
                              {item.category && (
                                <span className="text-[10px] text-muted-foreground">
                                  ({item.category.name})
                                </span>
                              )}
                            </div>
                          </td>
                          <td className="py-2.5 px-4 text-right font-mono text-foreground">
                            {formatCurrency(item.limit_amount)}
                          </td>
                          <td className="py-2.5 px-4 text-right font-mono">
                            {item.is_sinking_fund ? (
                              <div>
                                <span className="font-semibold text-emerald-600 dark:text-emerald-400">
                                  {formatCurrency(item.accumulated_balance)}
                                </span>
                                <div className="text-[10px] text-muted-foreground">
                                  (Rollover {formatCurrency(item.rollover_balance)} + Sisih {formatCurrency(item.funded_this_month)})
                                </div>
                              </div>
                            ) : (
                              <div>
                                <span className={item.is_over_budget ? "text-rose-600 dark:text-rose-400 font-bold" : "text-foreground"}>
                                  {formatCurrency(item.spent_amount)}
                                </span>
                                <div className="text-[10px] text-muted-foreground">
                                  Sisa: {formatCurrency(item.remaining_amount)} ({item.percent_used}%)
                                </div>
                              </div>
                            )}
                          </td>
                          <td className="py-2.5 px-4 text-xs text-muted-foreground">
                            {item.remark || "—"}
                          </td>
                          <td className="py-2.5 px-4">
                            {item.is_same_as_payroll ? (
                              <div className="flex flex-col gap-0.5">
                                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-[#f0b000]/15 border border-[#f0b000]/30 text-[10px] font-bold text-[#8a6300] dark:text-[#f0b000] w-fit">
                                  ⭐ Rekening Gajian
                                </span>
                                <span className="text-[10px] text-muted-foreground">{item.wallet?.name || "Langsung Tanpa Transfer"}</span>
                              </div>
                            ) : item.wallet ? (
                              <div className="flex flex-col gap-1">
                                <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-secondary border border-border text-xs font-semibold text-foreground w-fit">
                                  <span
                                    className="w-2 h-2 rounded-full"
                                    style={{ backgroundColor: item.wallet.color }}
                                  />
                                  {item.wallet.name}
                                </span>
                                {item.funding_status === "FUNDED" && (
                                  <span className="text-[10px] text-emerald-600 dark:text-emerald-400 font-bold bg-emerald-500/10 px-1.5 py-0.5 rounded-md border border-emerald-500/20 w-fit">
                                    ✓ Funded
                                  </span>
                                )}
                                {item.funding_status === "PARTIAL" && (
                                  <span className="text-[10px] text-amber-600 dark:text-amber-400 font-bold bg-amber-500/10 px-1.5 py-0.5 rounded-md border border-amber-500/20 w-fit">
                                    Sebagian ({formatCurrency(item.funded_this_month)})
                                  </span>
                                )}
                                {item.funding_status === "UNFUNDED" && (
                                  <span className="text-[10px] text-rose-600 dark:text-rose-400 font-bold bg-rose-500/10 px-1.5 py-0.5 rounded-md border border-rose-500/20 w-fit">
                                    Belum Ditransfer
                                  </span>
                                )}
                              </div>
                            ) : (
                              <span className="text-xs text-muted-foreground italic">Belum Dipilih</span>
                            )}
                          </td>
                          <td className="py-2.5 px-4 text-right text-xs text-muted-foreground">
                            {/* Subtotal shown at group level */}
                            —
                          </td>
                          <td className="py-2.5 px-4 text-center">
                            <div className="flex items-center justify-center gap-1 flex-wrap">
                              {!item.is_same_as_payroll && item.wallet_id && (
                                <button
                                  type="button"
                                  onClick={() => {
                                    setRecordActionModal({ item, mode: "TRANSFER_ALLOCATION" });
                                    setActionAmount(
                                      (item.unfunded_amount !== undefined && item.unfunded_amount > 0
                                        ? item.unfunded_amount
                                        : item.limit_amount
                                      ).toString()
                                    );
                                    setActionSourceWalletId(
                                      allocation?.payroll_wallet_id ||
                                        wallets.find((w) => w.is_default)?.id ||
                                        wallets[0]?.id ||
                                        ""
                                    );
                                    setActionDesc(`Transfer Alokasi Pos ${item.name}`);
                                  }}
                                  className="px-2 py-1 rounded-lg bg-primary/10 hover:bg-primary/20 text-[#8a6300] dark:text-[#f0b000] border border-[#f0b000]/30 text-[10px] font-bold flex items-center gap-1"
                                  title="Transfer dana pos dari Rekening Gajian ke dompet ini"
                                >
                                  <ArrowLeftRight className="w-3 h-3" />
                                  <span>Transfer Pos</span>
                                </button>
                              )}
                              {item.is_sinking_fund ? (
                                <>
                                  <button
                                    type="button"
                                    onClick={() => {
                                      setRecordActionModal({ item, mode: "FUND_SINKING" });
                                      setActionAmount(item.limit_amount.toString());
                                      setActionDesc(`Sisihkan ${item.name}`);
                                    }}
                                    className="px-2 py-1 rounded-lg bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-600 dark:text-emerald-400 border border-emerald-500/30 text-[10px] font-bold"
                                    title="Tandai Sisihkan Bulan Ini"
                                  >
                                    Sisihkan
                                  </button>
                                  <button
                                    type="button"
                                    onClick={() => {
                                      setRecordActionModal({ item, mode: "EXPENSE" });
                                      setActionAmount("");
                                      setActionDesc(`Pakai ${item.name}`);
                                    }}
                                    className="px-2 py-1 rounded-lg bg-secondary hover:bg-accent text-foreground border border-border text-[10px] font-bold"
                                    title="Pakai Dana Sinking Fund"
                                  >
                                    Pakai
                                  </button>
                                </>
                              ) : (
                                <button
                                  type="button"
                                  onClick={() => {
                                    setRecordActionModal({ item, mode: "EXPENSE" });
                                    setActionAmount("");
                                    setActionDesc(`Bayar ${item.name}`);
                                  }}
                                  className="px-2 py-1 rounded-lg bg-secondary hover:bg-accent text-foreground border border-border text-[10px] font-bold"
                                  title="Catat Realisasi Belanja dari Dompet Pos"
                                >
                                  Bayar
                                </button>
                              )}
                              <button
                                type="button"
                                onClick={() => handleEditItem(item)}
                                className="p-1 rounded text-muted-foreground hover:text-foreground"
                                title="Edit Pos"
                              >
                                <Edit2 className="w-3.5 h-3.5" />
                              </button>
                              <button
                                type="button"
                                onClick={() => handleDeleteItem(item.id)}
                                className="p-1 rounded text-muted-foreground hover:text-rose-500"
                                title="Hapus Pos"
                              >
                                <Trash2 className="w-3.5 h-3.5" />
                              </button>
                            </div>
                          </td>
                        </tr>
                      ))}

                      {/* Inline Quick-Add Row */}
                      {inlineGroup === group.group_type && (
                        <tr className="bg-accent/40 border-t border-border">
                          <td className="py-2 px-4 text-xs font-bold text-[#8a6300] dark:text-[#f0b000] pl-8">
                            + Baru
                          </td>
                          <td className="py-2 px-4">
                            <input
                              type="text"
                              placeholder="Nama pos (cth: Listrik / Bia)..."
                              value={inlineName}
                              onChange={(e) => setInlineName(e.target.value)}
                              className="w-full px-2 py-1 rounded-lg bg-background border border-border text-xs focus:outline-none focus:border-[#f0b000]"
                              autoFocus
                            />
                          </td>
                          <td className="py-2 px-4">
                            <input
                              type="number"
                              placeholder="Nominal budget..."
                              value={inlineLimit}
                              onChange={(e) => setInlineLimit(e.target.value)}
                              className="w-full px-2 py-1 rounded-lg bg-background border border-border text-xs text-right font-mono focus:outline-none focus:border-[#f0b000]"
                            />
                          </td>
                          <td colSpan={2} className="py-2 px-4 text-xs text-muted-foreground">
                            Pilih Dompet &rarr;
                          </td>
                          <td className="py-2 px-4">
                            <select
                              value={inlineWalletId}
                              onChange={(e) => setInlineWalletId(e.target.value)}
                              className="w-full px-2 py-1 rounded-lg bg-background border border-border text-xs focus:outline-none"
                            >
                              {wallets.map((w) => (
                                <option key={w.id} value={w.id}>{w.name}</option>
                              ))}
                            </select>
                          </td>
                          <td colSpan={2} className="py-2 px-4 text-center">
                            <div className="flex items-center justify-center gap-2">
                              <button
                                type="button"
                                onClick={() => handleInlineAdd(group.group_type)}
                                className="px-3 py-1 rounded-lg bg-primary text-primary-foreground font-bold text-xs"
                              >
                                Simpan
                              </button>
                              <button
                                type="button"
                                onClick={() => setInlineGroup(null)}
                                className="px-2 py-1 rounded-lg text-muted-foreground hover:text-foreground text-xs"
                              >
                                Batal
                              </button>
                            </div>
                          </td>
                        </tr>
                      )}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      ) : (
        /* Visual Cards View */
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {allocation?.groups.map((group) => (
            <div key={group.group_type} className="p-6 rounded-3xl bg-card border border-border shadow-sm space-y-4">
              <div className="flex items-center justify-between border-b border-border pb-3">
                <div>
                  <h3 className="font-bold text-base text-foreground">{group.group_type}</h3>
                  <span className="text-xs text-muted-foreground">
                    Total: {formatCurrency(group.subtotal_budget)} ({group.income_percentage}% gaji)
                  </span>
                </div>
                <div className="flex items-center gap-1.5">
                  <button
                    type="button"
                    onClick={() => handleStartEditGroup(group.group_type)}
                    className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-secondary transition-colors"
                    title="Edit Grup TYPE"
                  >
                    <Edit2 className="w-3.5 h-3.5" />
                  </button>
                  <button
                    type="button"
                    onClick={() => handleStartDeleteGroup(group.group_type, group.items_count)}
                    className="p-1.5 rounded-lg text-muted-foreground hover:text-rose-500 hover:bg-secondary transition-colors"
                    title="Hapus Grup TYPE"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                  <button
                    type="button"
                    onClick={() => handleOpenNewItem(group.group_type)}
                    className="px-2.5 py-1 rounded-lg bg-secondary hover:bg-accent text-xs font-semibold text-foreground border border-border"
                  >
                    + Tambah Pos
                  </button>
                </div>
              </div>

              <div className="space-y-3">
                {group.items.map((item) => (
                  <div key={item.id} className="p-3.5 rounded-2xl bg-secondary/60 border border-border space-y-2">
                    <div className="flex items-center justify-between">
                      <div className="font-semibold text-sm text-foreground flex items-center gap-2">
                        <span>{item.name}</span>
                        {item.wallet && (
                          <span className="text-[10px] px-2 py-0.5 rounded-full bg-card border border-border text-muted-foreground">
                            {item.wallet.name}
                          </span>
                        )}
                      </div>
                      <span className="font-mono text-xs font-bold text-foreground">
                        {formatCurrency(item.limit_amount)}
                      </span>
                    </div>

                    {/* Progress Bar */}
                    <div className="w-full bg-background h-2 rounded-full overflow-hidden border border-border">
                      <div
                        className={`h-full rounded-full transition-all duration-300 ${
                          item.is_over_budget
                            ? "bg-rose-500"
                            : item.percent_used >= 80
                            ? "bg-amber-400"
                            : "bg-[#f0b000]"
                        }`}
                        style={{ width: `${Math.min(100, item.percent_used)}%` }}
                      />
                    </div>

                    <div className="flex justify-between text-[11px] text-muted-foreground">
                      <span>Terpakai: {formatCurrency(item.spent_amount)}</span>
                      <span>{item.percent_used}%</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Modal: Tambah / Edit Pos Anggaran */}
      {showItemModal && (
        <div className="fixed inset-0 z-50 bg-background/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-card border border-border rounded-2xl max-w-lg w-full p-6 shadow-2xl space-y-4">
            <h2 className="text-lg font-bold text-foreground">
              {editingItem ? "Edit Pos Anggaran" : "Tambah Pos Anggaran Baru"}
            </h2>
            <form onSubmit={handleSaveItem} className="space-y-4 text-xs">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <div className="flex items-center justify-between mb-1">
                    <label className="font-semibold text-foreground">Grup TYPE</label>
                    <button
                      type="button"
                      onClick={() => setShowManageGroupsModal(true)}
                      className="text-[11px] text-[#8a6300] dark:text-[#f0b000] hover:underline font-semibold flex items-center gap-1"
                    >
                      <Settings2 className="w-3 h-3" />
                      Kelola Grup
                    </button>
                  </div>
                  <select
                    value={formGroup}
                    onChange={(e) => {
                      const val = e.target.value;
                      if (val === "__ADD_NEW__") {
                        setShowAddGroupModal(true);
                      } else {
                        setFormGroup(val);
                        const match = budgetGroups.find((g) => g.name === val);
                        if (match) setFormIsSinking(match.is_sinking_fund);
                        else if (val === "PREDICTABLE SAVING") setFormIsSinking(true);
                      }
                    }}
                    className="w-full px-3 py-2 rounded-xl bg-secondary border border-border text-foreground font-medium"
                  >
                    {(budgetGroups.length > 0
                      ? budgetGroups.map((g) => g.name)
                      : (allocation?.group_presets || ["LIVING NEEDS", "LIFE STYLE", "ZAKAT DAN SEDEKAH", "PREDICTABLE SAVING"])
                    ).map((grpName) => {
                      const match = budgetGroups.find((g) => g.name === grpName);
                      return (
                        <option key={grpName} value={grpName}>
                          {grpName} {match?.is_sinking_fund ? "(Sinking Fund)" : ""}
                        </option>
                      );
                    })}
                    <option value="__ADD_NEW__" className="text-[#8a6300] dark:text-[#f0b000] font-bold">
                      ➕ + Buat Grup Baru...
                    </option>
                  </select>
                </div>

                <div>
                  <label className="font-semibold text-foreground block mb-1">Nama Pos (Custom Bebas Ketik)</label>
                  <input
                    type="text"
                    placeholder="Contoh: KPR, Sekolah Aa, Bia, Bensin..."
                    value={formName}
                    onChange={(e) => setFormName(e.target.value)}
                    className="w-full px-3 py-2 rounded-xl bg-secondary border border-border text-foreground font-medium"
                    required
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="font-semibold text-foreground block mb-1">Nominal Budget (Rp)</label>
                  <input
                    type="number"
                    placeholder="Contoh: 1000000"
                    value={formLimit}
                    onChange={(e) => setFormLimit(e.target.value)}
                    className="w-full px-3 py-2 rounded-xl bg-secondary border border-border text-foreground font-mono"
                    required
                  />
                </div>
                <div>
                  <label className="font-semibold text-foreground block mb-1">Catatan / Remark</label>
                  <input
                    type="text"
                    placeholder="Catatan tambahan..."
                    value={formRemark}
                    onChange={(e) => setFormRemark(e.target.value)}
                    className="w-full px-3 py-2 rounded-xl bg-secondary border border-border text-foreground"
                  />
                </div>
              </div>

              {/* Fund Location Dropdown + Quick Add Wallet */}
              <div>
                <div className="flex items-center justify-between mb-1">
                  <label className="font-semibold text-foreground">Fund Location (Dompet Terhubung)</label>
                  <button
                    type="button"
                    onClick={() => setShowQuickWalletModal(true)}
                    className="text-[11px] text-[#8a6300] dark:text-[#f0b000] hover:underline"
                  >
                    + Buat Dompet Baru Cepat
                  </button>
                </div>
                <select
                  value={formWalletId}
                  onChange={(e) => setFormWalletId(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl bg-secondary border border-border text-foreground"
                >
                  <option value="">-- Tanpa Dompet Khusus --</option>
                  {wallets.map((w) => (
                    <option key={w.id} value={w.id}>
                      {w.name} ({w.type} - Saldo: {formatCurrency(w.balance)})
                    </option>
                  ))}
                </select>
              </div>

              {/* Category mapping + Quick Custom Category */}
              <div>
                <div className="flex items-center justify-between mb-1">
                  <label className="font-semibold text-foreground">Kategori (Opsional / Otomatis Terhubung)</label>
                  <button
                    type="button"
                    onClick={() => setShowCustomCatModal(true)}
                    className="text-[11px] text-[#8a6300] dark:text-[#f0b000] hover:underline"
                  >
                    + Kategori Custom Baru
                  </button>
                </div>
                <select
                  value={formCategoryId}
                  onChange={(e) => setFormCategoryId(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl bg-secondary border border-border text-foreground"
                >
                  <option value="">-- Auto Map Berdasarkan Nama Pos --</option>
                  {categories.map((c) => (
                    <option key={c.id} value={c.id}>{c.name}</option>
                  ))}
                </select>
              </div>

              {/* Sinking Fund Checkbox */}
              <div className="flex items-center gap-2 p-3 rounded-xl bg-secondary/70 border border-border">
                <input
                  type="checkbox"
                  id="isSinking"
                  checked={formIsSinking}
                  onChange={(e) => setFormIsSinking(e.target.checked)}
                  className="accent-[#f0b000] w-4 h-4 rounded cursor-pointer"
                />
                <label htmlFor="isSinking" className="text-xs text-foreground cursor-pointer">
                  <strong>Jadikan Sinking Fund (Tabungan Terjadwal):</strong> Saldo terkumpul tidak di-reset ke 0 tiap bulan dan otomatis terakumulasi lintas bulan sampai dipakai.
                </label>
              </div>

              <div className="flex items-center justify-end gap-3 pt-3 border-t border-border">
                <button
                  type="button"
                  onClick={() => setShowItemModal(false)}
                  className="px-4 py-2 rounded-xl text-muted-foreground hover:text-foreground"
                >
                  Batal
                </button>
                <button
                  type="submit"
                  className="px-5 py-2 rounded-xl bg-primary text-primary-foreground font-bold shadow-sm"
                >
                  Simpan Pos Anggaran
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Modal: Asisten Distribusi Gajian */}
      {showPaydayModal && (
        <div className="fixed inset-0 z-50 bg-background/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-card border border-border rounded-2xl max-w-lg w-full p-6 shadow-2xl space-y-4 text-xs">
            <div className="flex items-center gap-2">
              <Sparkles className="w-5 h-5 text-[#8a6300] dark:text-[#f0b000]" />
              <h2 className="text-base font-bold text-foreground">
                Asisten Distribusi Gajian Otomatis
              </h2>
            </div>
            <p className="text-muted-foreground leading-relaxed">
              Sistem akan mengeksekusi transfer antar-dompet dari rekening sumber gaji ke masing-masing dompet penempatan dana (Fund Location) agar saldo siap digunakan sesuai komitmen bulan ini.
            </p>

            <form onSubmit={handleExecutePayday} className="space-y-4">
              <div>
                <label className="font-semibold text-foreground block mb-1">Dompet Sumber Gaji / Payroll</label>
                <select
                  value={sourceWalletId}
                  onChange={(e) => setSourceWalletId(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl bg-secondary border border-border text-foreground font-semibold"
                >
                  {wallets.map((w) => (
                    <option key={w.id} value={w.id}>
                      {w.name} (Saldo: {formatCurrency(w.balance)})
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="font-semibold text-foreground block mb-1">Mode Perhitungan Transfer</label>
                <div className="grid grid-cols-2 gap-2">
                  <button
                    type="button"
                    onClick={() => setPaydayMode("SHORTFALL")}
                    className={`p-2.5 rounded-xl border text-left transition-colors ${
                      paydayMode === "SHORTFALL"
                        ? "bg-accent border-[#f0b000]/50 text-[#8a6300] dark:text-[#f0b000] font-bold"
                        : "bg-secondary border-border text-muted-foreground"
                    }`}
                  >
                    <div>Hanya Kekurangan (Shortfall)</div>
                    <div className="text-[10px] font-normal opacity-80">Transfer selisih saldo yang masih kurang</div>
                  </button>
                  <button
                    type="button"
                    onClick={() => setPaydayMode("FULL_BUDGET")}
                    className={`p-2.5 rounded-xl border text-left transition-colors ${
                      paydayMode === "FULL_BUDGET"
                        ? "bg-accent border-[#f0b000]/50 text-[#8a6300] dark:text-[#f0b000] font-bold"
                        : "bg-secondary border-border text-muted-foreground"
                    }`}
                  >
                    <div>Penuh Sesuai Anggaran</div>
                    <div className="text-[10px] font-normal opacity-80">Transfer 100% total limit bulan ini</div>
                  </button>
                </div>
              </div>

              {/* Preview Planned Transfers */}
              <div className="p-3 rounded-xl bg-secondary/80 border border-border space-y-1.5">
                <div className="font-bold text-foreground">Daftar Rencana Transfer:</div>
                {allocation?.wallet_allocations
                  .filter((wa) => wa.wallet_id !== sourceWalletId && (paydayMode === "SHORTFALL" ? wa.shortfall_amount > 0 : wa.total_monthly_budget > 0))
                  .map((wa) => (
                    <div key={wa.wallet_id} className="flex justify-between items-center text-muted-foreground">
                      <span>&rarr; {wa.wallet_name}:</span>
                      <strong className="text-foreground font-mono">
                        {formatCurrency(paydayMode === "SHORTFALL" ? wa.shortfall_amount : wa.total_monthly_budget)}
                      </strong>
                    </div>
                  ))}
              </div>

              <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  id="fundSinkingCheck"
                  checked={autoFundSinking}
                  onChange={(e) => setAutoFundSinking(e.target.checked)}
                  className="accent-[#f0b000] w-4 h-4 rounded cursor-pointer"
                />
                <label htmlFor="fundSinkingCheck" className="text-foreground cursor-pointer">
                  Otomatis tandai pos <em>Sinking Fund</em> di dompet tujuan sebagai sudah disisihkan.
                </label>
              </div>

              <div className="flex items-center justify-end gap-3 pt-3 border-t border-border">
                <button
                  type="button"
                  onClick={() => setShowPaydayModal(false)}
                  className="px-4 py-2 rounded-xl text-muted-foreground hover:text-foreground"
                >
                  Batal
                </button>
                <button
                  type="submit"
                  className="px-5 py-2 rounded-xl bg-primary text-primary-foreground font-bold shadow-md shadow-[#f0b000]/20"
                >
                  Eksekusi Distribusi Gajian
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Modal: Ubah Penghasilan Acuan */}
      {showIncomeModal && (
        <div className="fixed inset-0 z-50 bg-background/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-card border border-border rounded-2xl max-w-sm w-full p-6 shadow-2xl space-y-4 text-xs">
            <h2 className="text-base font-bold text-foreground">Atur Penghasilan Acuan</h2>
            <p className="text-muted-foreground">
              Nominal ini digunakan sebagai dasar pembagian persentase per grup (Living Needs %, Life Style %, dll).
            </p>
            <form onSubmit={handleSaveIncome} className="space-y-4">
              <div>
                <label className="font-semibold text-foreground block mb-1">Penghasilan Bulanan (Rp)</label>
                <input
                  type="number"
                  value={referenceIncomeInput}
                  onChange={(e) => setReferenceIncomeInput(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl bg-secondary border border-border text-foreground font-mono font-bold text-sm"
                  required
                />
              </div>
              <div className="flex items-center justify-end gap-3 pt-2">
                <button
                  type="button"
                  onClick={() => setShowIncomeModal(false)}
                  className="px-4 py-2 rounded-xl text-muted-foreground hover:text-foreground"
                >
                  Batal
                </button>
                <button
                  type="submit"
                  className="px-5 py-2 rounded-xl bg-primary text-primary-foreground font-bold"
                >
                  Simpan
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Modal: Kelola Grup TYPE Komprehensif */}
      {showManageGroupsModal && (
        <div className="fixed inset-0 z-50 bg-background/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-card border border-border rounded-2xl max-w-lg w-full p-6 shadow-2xl space-y-5 text-xs max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between border-b border-border pb-3">
              <div className="flex items-center gap-2">
                <Settings2 className="w-5 h-5 text-[#8a6300] dark:text-[#f0b000]" />
                <h2 className="text-base font-bold text-foreground">Kelola Grup TYPE Anggaran</h2>
              </div>
              <button
                type="button"
                onClick={() => setShowManageGroupsModal(false)}
                className="p-1 rounded-lg text-muted-foreground hover:text-foreground hover:bg-secondary"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <p className="text-muted-foreground">
              Grup TYPE membagi pos anggaran menjadi pos pengeluaran rutin atau tabungan terencana (Sinking Fund) dengan akumulasi lintas bulan.
            </p>

            {/* Existing Groups List */}
            <div className="space-y-2">
              <span className="font-semibold text-foreground uppercase tracking-wider text-[11px]">
                Daftar Grup Aktif ({budgetGroups.length})
              </span>
              <div className="divide-y divide-border border border-border rounded-xl overflow-hidden bg-secondary/40">
                {budgetGroups.map((bg) => (
                  <div key={bg.id} className="p-3 flex items-center justify-between hover:bg-secondary/70 transition-colors">
                    <div className="flex items-center gap-2.5">
                      <span className="font-bold text-foreground tracking-wide">{bg.name}</span>
                      {bg.is_sinking_fund ? (
                        <span className="text-[10px] px-2 py-0.5 rounded-full bg-amber-500/10 text-amber-700 dark:text-amber-400 border border-amber-500/30">
                          Sinking Fund
                        </span>
                      ) : (
                        <span className="text-[10px] px-2 py-0.5 rounded-full bg-blue-500/10 text-blue-700 dark:text-blue-400 border border-blue-500/30">
                          Rutin Bulanan
                        </span>
                      )}
                      <span className="text-[10px] text-muted-foreground">
                        ({bg.items_count || 0} Pos)
                      </span>
                    </div>

                    <div className="flex items-center gap-1">
                      <button
                        type="button"
                        onClick={() => {
                          setEditingGroup(bg);
                          setEditingGroupName(bg.name);
                          setEditingGroupIsSinking(bg.is_sinking_fund);
                        }}
                        className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-secondary"
                        title="Edit Grup"
                      >
                        <Edit2 className="w-3.5 h-3.5" />
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          handleStartDeleteGroup(bg.name, bg.items_count || 0);
                        }}
                        disabled={budgetGroups.length <= 1}
                        className="p-1.5 rounded-lg text-muted-foreground hover:text-rose-500 hover:bg-secondary disabled:opacity-30 disabled:cursor-not-allowed"
                        title={budgetGroups.length <= 1 ? "Minimal tersisa 1 grup" : "Hapus Grup"}
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Quick Add Form inside Manage Modal */}
            <form onSubmit={handleCreateGroup} className="p-4 rounded-xl border border-[#f0b000]/30 bg-accent/20 space-y-3">
              <span className="font-bold text-[#8a6300] dark:text-[#f0b000] text-xs flex items-center gap-1.5">
                <Plus className="w-4 h-4" />
                Tambah Grup TYPE Baru
              </span>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="font-semibold text-foreground block mb-1">Nama Grup</label>
                  <input
                    type="text"
                    placeholder="Contoh: PENDIDIKAN ANAK, BISNIS..."
                    value={groupFormName}
                    onChange={(e) => setGroupFormName(e.target.value)}
                    className="w-full px-3 py-2 rounded-xl bg-background border border-border text-foreground font-semibold uppercase text-xs"
                    required
                  />
                </div>
                <div className="flex items-center pt-5">
                  <label className="flex items-center gap-2 cursor-pointer text-xs font-semibold text-foreground select-none">
                    <input
                      type="checkbox"
                      checked={groupFormIsSinking}
                      onChange={(e) => setGroupFormIsSinking(e.target.checked)}
                      className="w-4 h-4 rounded text-[#f0b000] focus:ring-[#f0b000]"
                    />
                    <span>Sinking Fund (Rollover Saldo)</span>
                  </label>
                </div>
              </div>
              <div className="flex justify-end pt-1">
                <button
                  type="submit"
                  className="px-4 py-2 rounded-xl bg-primary text-primary-foreground font-bold shadow-sm text-xs"
                >
                  + Tambah Grup
                </button>
              </div>
            </form>

            <div className="flex justify-end pt-2">
              <button
                type="button"
                onClick={() => setShowManageGroupsModal(false)}
                className="px-5 py-2 rounded-xl bg-secondary hover:bg-secondary/80 text-foreground font-semibold"
              >
                Tutup
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Modal: Tambah Grup TYPE (Dedicated Popup dari Dropdown) */}
      {showAddGroupModal && (
        <div className="fixed inset-0 z-50 bg-background/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-card border border-border rounded-2xl max-w-sm w-full p-6 shadow-2xl space-y-4 text-xs">
            <h2 className="text-base font-bold text-foreground">Tambah Grup TYPE Baru</h2>
            <form onSubmit={handleCreateGroup} className="space-y-4">
              <div>
                <label className="font-semibold text-foreground block mb-1">Nama Grup TYPE</label>
                <input
                  type="text"
                  placeholder="Contoh: CICILAN & HUTANG, UMRAH..."
                  value={groupFormName}
                  onChange={(e) => setGroupFormName(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl bg-secondary border border-border text-foreground uppercase font-bold text-xs"
                  required
                  autoFocus
                />
              </div>

              <div className="p-3 rounded-xl bg-secondary/50 border border-border">
                <label className="flex items-center gap-2 cursor-pointer font-semibold text-foreground select-none">
                  <input
                    type="checkbox"
                    checked={groupFormIsSinking}
                    onChange={(e) => setGroupFormIsSinking(e.target.checked)}
                    className="w-4 h-4 rounded text-[#f0b000]"
                  />
                  <span>Sinking Fund (Akumulasi / Rollover)</span>
                </label>
                <p className="text-[10px] text-muted-foreground mt-1 ml-6">
                  Sisa dana pos pada grup ini tidak akan di-reset ke 0 saat ganti bulan, melainkan diakumulasikan.
                </p>
              </div>

              <div className="flex items-center justify-end gap-3 pt-2">
                <button
                  type="button"
                  onClick={() => {
                    setShowAddGroupModal(false);
                    setGroupFormName("");
                  }}
                  className="px-4 py-2 rounded-xl text-muted-foreground hover:text-foreground"
                >
                  Batal
                </button>
                <button
                  type="submit"
                  className="px-5 py-2 rounded-xl bg-primary text-primary-foreground font-bold"
                >
                  Simpan Grup
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Modal: Edit Grup TYPE */}
      {editingGroup && (
        <div className="fixed inset-0 z-50 bg-background/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-card border border-border rounded-2xl max-w-sm w-full p-6 shadow-2xl space-y-4 text-xs">
            <h2 className="text-base font-bold text-foreground">Edit Grup TYPE</h2>
            <form onSubmit={handleUpdateGroup} className="space-y-4">
              <div>
                <label className="font-semibold text-foreground block mb-1">Nama Grup</label>
                <input
                  type="text"
                  value={editingGroupName}
                  onChange={(e) => setEditingGroupName(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl bg-secondary border border-border text-foreground uppercase font-bold text-xs"
                  required
                />
                <p className="text-[10px] text-muted-foreground mt-1">
                  Nama grup akan otomatis diperbarui pada seluruh pos anggaran yang terhubung.
                </p>
              </div>

              <div className="p-3 rounded-xl bg-secondary/50 border border-border">
                <label className="flex items-center gap-2 cursor-pointer font-semibold text-foreground select-none">
                  <input
                    type="checkbox"
                    checked={editingGroupIsSinking}
                    onChange={(e) => setEditingGroupIsSinking(e.target.checked)}
                    className="w-4 h-4 rounded text-[#f0b000]"
                  />
                  <span>Sinking Fund (Akumulasi / Rollover)</span>
                </label>
                <p className="text-[10px] text-muted-foreground mt-1 ml-6">
                  Jika diaktifkan, seluruh pos dalam grup ini akan mengakumulasi saldo tersisa ke bulan berikutnya.
                </p>
              </div>

              <div className="flex items-center justify-end gap-3 pt-2">
                <button
                  type="button"
                  onClick={() => setEditingGroup(null)}
                  className="px-4 py-2 rounded-xl text-muted-foreground hover:text-foreground"
                >
                  Batal
                </button>
                <button
                  type="submit"
                  className="px-5 py-2 rounded-xl bg-primary text-primary-foreground font-bold"
                >
                  Simpan Perubahan
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Modal: Hapus Grup TYPE (Proteksi & Reassign Opsi) */}
      {deletingGroup && (
        <div className="fixed inset-0 z-50 bg-background/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-card border border-border rounded-2xl max-w-md w-full p-6 shadow-2xl space-y-4 text-xs">
            <div className="flex items-center gap-2 text-rose-500">
              <AlertCircle className="w-5 h-5" />
              <h2 className="text-base font-bold text-foreground">Hapus Grup TYPE: {deletingGroup.name}</h2>
            </div>

            {deletingGroup.items_count > 0 ? (
              <form onSubmit={handleDeleteGroup} className="space-y-4">
                <div className="p-3.5 rounded-xl bg-rose-500/10 border border-rose-500/20 text-rose-700 dark:text-rose-400">
                  <p className="font-semibold">
                    Grup ini memiliki <span className="font-bold underline">{deletingGroup.items_count} pos anggaran</span> aktif.
                  </p>
                  <p className="text-[11px] mt-1 text-muted-foreground">
                    Pilih apa yang ingin Anda lakukan terhadap pos-pos anggaran tersebut:
                  </p>
                </div>

                <div className="space-y-2.5">
                  <label className="flex items-start gap-2.5 p-3 rounded-xl border border-border bg-secondary/50 cursor-pointer">
                    <input
                      type="radio"
                      name="deleteAction"
                      value="reassign"
                      checked={deleteAction === "reassign"}
                      onChange={() => setDeleteAction("reassign")}
                      className="mt-0.5 text-[#f0b000]"
                    />
                    <div className="space-y-1.5 flex-1">
                      <span className="font-bold text-foreground block">
                        Pindahkan pos anggaran ke grup lain (Direkomendasikan)
                      </span>
                      {deleteAction === "reassign" && (
                        <select
                          value={deleteReassignToId}
                          onChange={(e) => setDeleteReassignToId(e.target.value)}
                          className="w-full px-2.5 py-1.5 rounded-lg bg-background border border-border text-foreground font-semibold text-xs"
                        >
                          {budgetGroups
                            .filter((g) => g.id !== deletingGroup.id)
                            .map((g) => (
                              <option key={g.id} value={g.id}>
                                Pindahkan ke: {g.name}
                              </option>
                            ))}
                        </select>
                      )}
                    </div>
                  </label>

                  <label className="flex items-start gap-2.5 p-3 rounded-xl border border-border bg-secondary/50 cursor-pointer">
                    <input
                      type="radio"
                      name="deleteAction"
                      value="cascade"
                      checked={deleteAction === "cascade"}
                      onChange={() => setDeleteAction("cascade")}
                      className="mt-0.5 text-rose-500"
                    />
                    <div>
                      <span className="font-bold text-rose-500 block">
                        Hapus grup beserta seluruh {deletingGroup.items_count} pos anggaran di dalamnya
                      </span>
                      <span className="text-[10px] text-muted-foreground block">
                        Pos dan riwayat alokasi terkait pada grup ini akan dihapus permanen.
                      </span>
                    </div>
                  </label>
                </div>

                <div className="flex items-center justify-end gap-3 pt-2">
                  <button
                    type="button"
                    onClick={() => setDeletingGroup(null)}
                    className="px-4 py-2 rounded-xl text-muted-foreground hover:text-foreground"
                  >
                    Batal
                  </button>
                  <button
                    type="submit"
                    className={`px-5 py-2 rounded-xl font-bold ${
                      deleteAction === "cascade"
                        ? "bg-rose-500 hover:bg-rose-600 text-white"
                        : "bg-primary text-primary-foreground"
                    }`}
                  >
                    {deleteAction === "cascade" ? "Hapus Permanen Semua" : "Pindahkan & Hapus Grup"}
                  </button>
                </div>
              </form>
            ) : (
              <form onSubmit={handleDeleteGroup} className="space-y-4">
                <p className="text-muted-foreground">
                  Grup ini kosong (0 pos terdaftar). Apakah Anda yakin ingin menghapus grup <strong>{deletingGroup.name}</strong>?
                </p>
                <div className="flex items-center justify-end gap-3 pt-2">
                  <button
                    type="button"
                    onClick={() => setDeletingGroup(null)}
                    className="px-4 py-2 rounded-xl text-muted-foreground hover:text-foreground"
                  >
                    Batal
                  </button>
                  <button
                    type="submit"
                    className="px-5 py-2 rounded-xl bg-rose-500 hover:bg-rose-600 text-white font-bold"
                  >
                    Ya, Hapus Grup
                  </button>
                </div>
              </form>
            )}
          </div>
        </div>
      )}

      {/* Modal: Rename Group TYPE (Legacy Fallback) */}
      {showRenameGroupModal && (
        <div className="fixed inset-0 z-50 bg-background/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-card border border-border rounded-2xl max-w-sm w-full p-6 shadow-2xl space-y-4 text-xs">
            <h2 className="text-base font-bold text-foreground">Ubah Nama Grup TYPE</h2>
            <form onSubmit={handleRenameGroup} className="space-y-4">
              <div>
                <label className="font-semibold text-foreground block mb-1">Nama Grup Baru</label>
                <input
                  type="text"
                  value={newGroupName}
                  onChange={(e) => setNewGroupName(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl bg-secondary border border-border text-foreground uppercase font-bold"
                  required
                />
              </div>
              <div className="flex items-center justify-end gap-3 pt-2">
                <button
                  type="button"
                  onClick={() => setShowRenameGroupModal(null)}
                  className="px-4 py-2 rounded-xl text-muted-foreground hover:text-foreground"
                >
                  Batal
                </button>
                <button
                  type="submit"
                  className="px-5 py-2 rounded-xl bg-primary text-primary-foreground font-bold"
                >
                  Perbarui Grup
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Modal: Aksi Cepat Baris (Bayar / Sisihkan / Pakai / Transfer Pos) */}
      {recordActionModal && (
        <div className="fixed inset-0 z-50 bg-background/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-card border border-border rounded-2xl max-w-sm w-full p-6 shadow-2xl space-y-4 text-xs">
            <h2 className="text-base font-bold text-foreground flex items-center gap-1.5">
              {recordActionModal.mode === "TRANSFER_ALLOCATION" && <ArrowLeftRight className="w-4 h-4 text-primary" />}
              {recordActionModal.mode === "TRANSFER_ALLOCATION"
                ? `Transfer Alokasi: ${recordActionModal.item.name}`
                : recordActionModal.mode === "FUND_SINKING"
                ? `Sisihkan Dana: ${recordActionModal.item.name}`
                : `Catat Realisasi Pengeluaran: ${recordActionModal.item.name}`}
            </h2>
            <form onSubmit={handleExecuteAction} className="space-y-3">
              <div>
                <label className="font-semibold text-foreground block mb-1">
                  {recordActionModal.mode === "TRANSFER_ALLOCATION"
                    ? "Nominal Transfer Alokasi (Rp)"
                    : "Nominal (Rp)"}
                </label>
                <input
                  type="number"
                  placeholder={
                    recordActionModal.mode === "TRANSFER_ALLOCATION" &&
                    recordActionModal.item.unfunded_amount !== undefined &&
                    recordActionModal.item.unfunded_amount > 0
                      ? recordActionModal.item.unfunded_amount.toString()
                      : recordActionModal.item.limit_amount.toString()
                  }
                  value={actionAmount}
                  onChange={(e) => setActionAmount(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl bg-secondary border border-border text-foreground font-mono font-bold"
                />
                <span className="text-[10px] text-muted-foreground">
                  {recordActionModal.mode === "TRANSFER_ALLOCATION"
                    ? `Sisa belum ditransfer: ${formatCurrency(recordActionModal.item.unfunded_amount ?? recordActionModal.item.limit_amount)}`
                    : `Limit anggaran: ${formatCurrency(recordActionModal.item.limit_amount)}`}
                </span>
              </div>

              {recordActionModal.mode === "TRANSFER_ALLOCATION" && (
                <>
                  <div>
                    <label className="font-semibold text-foreground block mb-1">
                      Dari Dompet Sumber (Rekening Gajian)
                    </label>
                    <select
                      value={
                        actionSourceWalletId ||
                        allocation?.payroll_wallet_id ||
                        wallets.find((w) => w.is_default)?.id ||
                        wallets[0]?.id ||
                        ""
                      }
                      onChange={(e) => setActionSourceWalletId(e.target.value)}
                      className="w-full px-3 py-2 rounded-xl bg-secondary border border-border text-foreground font-semibold"
                    >
                      {wallets
                        .filter(
                          (w) =>
                            w.access_role !== "VIEWER" &&
                            w.id !== recordActionModal.item.wallet_id
                        )
                        .map((w) => (
                          <option key={w.id} value={w.id}>
                            {w.is_default ? "⭐ " : ""}
                            {w.name} (Saldo: {formatCurrency(w.balance)})
                          </option>
                        ))}
                    </select>
                  </div>

                  <div>
                    <label className="font-semibold text-foreground block mb-1">
                      Ke Dompet Tujuan Pos
                    </label>
                    <div className="p-2.5 rounded-xl bg-secondary/70 border border-border flex items-center justify-between">
                      <span className="font-bold text-foreground">
                        {recordActionModal.item.wallet?.name || "Dompet Tujuan"}
                      </span>
                      <span className="text-[11px] text-muted-foreground font-mono">
                        Saldo: {formatCurrency(recordActionModal.item.wallet?.balance || 0)}
                      </span>
                    </div>
                  </div>
                </>
              )}

              {recordActionModal.mode === "EXPENSE" && (
                <div>
                  <label className="font-semibold text-foreground block mb-1">Potong Saldo Dompet</label>
                  <select
                    value={actionWalletId || recordActionModal.item.wallet_id || ""}
                    onChange={(e) => setActionWalletId(e.target.value)}
                    className="w-full px-3 py-2 rounded-xl bg-secondary border border-border text-foreground"
                  >
                    {wallets.map((w) => (
                      <option key={w.id} value={w.id}>
                        {w.name} ({formatCurrency(w.balance)})
                      </option>
                    ))}
                  </select>
                </div>
              )}

              <div>
                <label className="font-semibold text-foreground block mb-1">Deskripsi Tambahan</label>
                <input
                  type="text"
                  placeholder={
                    recordActionModal.mode === "TRANSFER_ALLOCATION"
                      ? `Transfer Alokasi Pos ${recordActionModal.item.name}`
                      : `Realisasi ${recordActionModal.item.name}`
                  }
                  value={actionDesc}
                  onChange={(e) => setActionDesc(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl bg-secondary border border-border text-foreground"
                />
              </div>

              <div className="flex items-center justify-end gap-3 pt-2">
                <button
                  type="button"
                  onClick={() => setRecordActionModal(null)}
                  className="px-4 py-2 rounded-xl text-muted-foreground hover:text-foreground"
                >
                  Batal
                </button>
                <button
                  type="submit"
                  className="px-5 py-2 rounded-xl bg-primary text-primary-foreground font-bold shadow-sm shadow-[#f0b000]/20 hover:bg-primary/90"
                >
                  {recordActionModal.mode === "TRANSFER_ALLOCATION" ? "Transfer Sekarang" : "Eksekusi"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Modal: Quick Create Category */}
      {showCustomCatModal && (
        <div className="fixed inset-0 z-50 bg-background/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-card border border-border rounded-2xl max-w-sm w-full p-6 shadow-2xl space-y-4 text-xs">
            <h2 className="text-base font-bold text-foreground">Buat Kategori Custom Baru</h2>
            <form onSubmit={handleCreateCustomCat} className="space-y-3">
              <div>
                <label className="font-semibold text-foreground block mb-1">Nama Kategori</label>
                <input
                  type="text"
                  placeholder="Contoh: Kebutuhan Bayi, Sedekah Subuh..."
                  value={customCatName}
                  onChange={(e) => setCustomCatName(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl bg-secondary border border-border text-foreground font-medium"
                  required
                />
              </div>
              <div className="flex items-center justify-end gap-3 pt-2">
                <button
                  type="button"
                  onClick={() => setShowCustomCatModal(false)}
                  className="px-4 py-2 rounded-xl text-muted-foreground hover:text-foreground"
                >
                  Batal
                </button>
                <button
                  type="submit"
                  className="px-5 py-2 rounded-xl bg-primary text-primary-foreground font-bold"
                >
                  Simpan Kategori
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Modal: Quick Create Wallet */}
      {showQuickWalletModal && (
        <div className="fixed inset-0 z-50 bg-background/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-card border border-border rounded-2xl max-w-sm w-full p-6 shadow-2xl space-y-4 text-xs">
            <h2 className="text-base font-bold text-foreground">Tambah Dompet Baru Cepat</h2>
            <form onSubmit={handleCreateQuickWallet} className="space-y-3">
              <div>
                <label className="font-semibold text-foreground block mb-1">Nama Dompet</label>
                <input
                  type="text"
                  placeholder="Contoh: Mandiri, Jago, Danamon..."
                  value={quickWalletName}
                  onChange={(e) => setQuickWalletName(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl bg-secondary border border-border text-foreground font-medium"
                  required
                />
              </div>
              <div>
                <label className="font-semibold text-foreground block mb-1">Tipe Dompet (Custom / Preset)</label>
                <input
                  type="text"
                  placeholder="BANK, EWALLET, KANTONG DIGITAL, BANK SYARIAH..."
                  value={quickWalletType}
                  onChange={(e) => setQuickWalletType(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl bg-secondary border border-border text-foreground uppercase"
                  required
                />
              </div>
              <div className="flex items-center justify-end gap-3 pt-2">
                <button
                  type="button"
                  onClick={() => setShowQuickWalletModal(false)}
                  className="px-4 py-2 rounded-xl text-muted-foreground hover:text-foreground"
                >
                  Batal
                </button>
                <button
                  type="submit"
                  className="px-5 py-2 rounded-xl bg-primary text-primary-foreground font-bold"
                >
                  Simpan Dompet
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
