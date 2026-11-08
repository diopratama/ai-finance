"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  Users,
  ShieldCheck,
  Activity,
  Wallet,
  Search,
  Bot,
  Calendar,
  CheckCircle2,
  Clock,
  ShieldAlert,
  Coins,
  RefreshCw,
  ArrowRight,
  ShieldX,
} from "lucide-react";
import {
  AdminStats,
  AdminUserItem,
  getAdminStats,
  getAdminUsers,
  getStoredUser,
  AuthUser,
} from "@/lib/api";

export default function AdminDashboardPage() {
  const [currentUser, setCurrentUser] = useState<AuthUser | null>(null);
  const [stats, setStats] = useState<AdminStats | null>(null);
  const [users, setUsers] = useState<AdminUserItem[]>([]);
  const [totalUsers, setTotalUsers] = useState(0);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [searchInput, setSearchInput] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const u = getStoredUser();
    setCurrentUser(u);
    if (u && u.role === "admin") {
      loadStats();
      loadUsers(1, "");
    } else {
      setLoading(false);
    }
  }, []);

  const loadStats = async () => {
    try {
      const s = await getAdminStats();
      setStats(s);
    } catch (err: any) {
      setError("Gagal memuat statistik admin: " + err.message);
    }
  };

  const loadUsers = async (p: number, s: string) => {
    setLoading(true);
    setError(null);
    try {
      const res = await getAdminUsers({ page: p, limit: 15, search: s });
      setUsers(res.users);
      setTotalUsers(res.total);
      setPage(res.page);
    } catch (err: any) {
      setError("Gagal memuat data pengguna: " + err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setSearch(searchInput);
    setPage(1);
    loadUsers(1, searchInput);
  };

  const handleRefresh = () => {
    loadStats();
    loadUsers(page, search);
  };

  if (!currentUser || currentUser.role !== "admin") {
    return (
      <div className="min-h-[70vh] flex flex-col items-center justify-center p-6 text-center">
        <div className="w-16 h-16 rounded-2xl bg-rose-500/10 border border-rose-500/30 flex items-center justify-center text-rose-500 mb-4 shadow-lg shadow-rose-500/10">
          <ShieldX className="w-8 h-8" />
        </div>
        <h1 className="text-xl font-bold text-foreground">Akses Dibatasi (Khusus Administrator)</h1>
        <p className="text-xs text-muted-foreground max-w-md mt-2 leading-relaxed">
          Halaman ini hanya dapat diakses oleh akun dengan wewenang <strong>Administrator</strong>. Silakan hubungi pengelola sistem jika Anda memerlukan hak akses ini.
        </p>
        <Link
          href="/dashboard"
          className="mt-6 inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-primary text-primary-foreground font-bold text-xs shadow-md shadow-[#f0b000]/20 hover:bg-primary/90 transition-all"
        >
          <span>Kembali ke Dashboard Utama</span>
          <ArrowRight className="w-3.5 h-3.5" />
        </Link>
      </div>
    );
  }

  const verifiedPercent = stats && stats.total_users > 0
    ? Math.round((stats.verified_users / stats.total_users) * 100)
    : 0;

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-8">
        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 text-xs font-semibold text-rose-600 dark:text-rose-400 uppercase tracking-wider">
              <ShieldAlert className="w-4 h-4" />
              <span>Admin Management Console</span>
            </div>
            <h1 className="text-2xl font-bold text-foreground mt-1 tracking-tight">
              Monitoring Sistem & Pengguna
            </h1>
            <p className="text-sm text-muted-foreground mt-1">
              Pantau jumlah pengguna terdaftar, status verifikasi email, keaktifan platform, dan kekayaan likuid sistem.
            </p>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={handleRefresh}
              className="inline-flex items-center gap-1.5 px-3 py-2 rounded-xl bg-secondary hover:bg-accent text-foreground text-xs font-semibold border border-border transition-all"
            >
              <RefreshCw className="w-3.5 h-3.5 text-[#8a6300] dark:text-[#f0b000]" />
              <span>Segarkan Data</span>
            </button>
          </div>
        </div>

        {error && (
          <div className="p-4 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-600 dark:text-rose-400 text-xs font-medium">
            {error}
          </div>
        )}

        {/* Aggregate Stats Cards */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {/* Card 1: Total Users */}
          <div className="p-5 rounded-2xl bg-card border border-border shadow-sm space-y-2">
            <div className="flex items-center justify-between text-muted-foreground">
              <span className="text-xs font-semibold">Total Pengguna</span>
              <div className="w-8 h-8 rounded-lg bg-blue-500/10 border border-blue-500/20 flex items-center justify-center text-blue-500">
                <Users className="w-4 h-4" />
              </div>
            </div>
            <div className="text-2xl font-black text-foreground">
              {stats ? stats.total_users.toLocaleString("id-ID") : "-"}
            </div>
            <div className="text-[11px] text-muted-foreground flex items-center gap-1.5">
              <ShieldCheck className="w-3.5 h-3.5 text-emerald-500" />
              <span>
                <strong className="text-foreground">{stats?.verified_users || 0}</strong> terverifikasi ({verifiedPercent}%)
              </span>
            </div>
          </div>

          {/* Card 2: Active Users 30d */}
          <div className="p-5 rounded-2xl bg-card border border-border shadow-sm space-y-2">
            <div className="flex items-center justify-between text-muted-foreground">
              <span className="text-xs font-semibold">Pengguna Aktif (30 Hari)</span>
              <div className="w-8 h-8 rounded-lg bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center text-emerald-500">
                <Activity className="w-4 h-4" />
              </div>
            </div>
            <div className="text-2xl font-black text-foreground">
              {stats ? stats.active_users_30d.toLocaleString("id-ID") : "-"}
            </div>
            <div className="text-[11px] text-muted-foreground">
              Pengguna yang aktif bertransaksi bulan ini
            </div>
          </div>

          {/* Card 3: Total Dompet & Saldo Sistem */}
          <div className="p-5 rounded-2xl bg-card border border-border shadow-sm space-y-2">
            <div className="flex items-center justify-between text-muted-foreground">
              <span className="text-xs font-semibold">Total Saldo Terkelola</span>
              <div className="w-8 h-8 rounded-lg bg-[#f0b000]/15 border border-[#f0b000]/30 flex items-center justify-center text-[#8a6300] dark:text-[#f0b000]">
                <Coins className="w-4 h-4" />
              </div>
            </div>
            <div className="text-2xl font-black text-foreground truncate">
              {stats ? `Rp ${intFormat(stats.total_system_balance)}` : "-"}
            </div>
            <div className="text-[11px] text-muted-foreground">
              Di {stats?.total_system_wallets || 0} dompet aktif pengguna
            </div>
          </div>

          {/* Card 4: Chatbot Integrations */}
          <div className="p-5 rounded-2xl bg-card border border-border shadow-sm space-y-2">
            <div className="flex items-center justify-between text-muted-foreground">
              <span className="text-xs font-semibold">Pengguna Chatbot</span>
              <div className="w-8 h-8 rounded-lg bg-purple-500/10 border border-purple-500/20 flex items-center justify-center text-purple-500">
                <Bot className="w-4 h-4" />
              </div>
            </div>
            <div className="text-2xl font-black text-foreground">
              {stats ? stats.bot_connected_users.toLocaleString("id-ID") : "-"}
            </div>
            <div className="text-[11px] text-muted-foreground">
              Terhubung ke Telegram / WhatsApp Bot
            </div>
          </div>
        </div>

        {/* User Management Section */}
        <div className="p-6 rounded-2xl bg-card border border-border shadow-sm space-y-6">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
            <div>
              <h2 className="text-base font-bold text-foreground">Daftar Pengguna Terdaftar</h2>
              <p className="text-xs text-muted-foreground mt-0.5">
                Total {totalUsers} pengguna tercatat di basis data AI-Finance
              </p>
            </div>

            {/* Search Form */}
            <form onSubmit={handleSearchSubmit} className="relative w-full sm:w-72">
              <Search className="w-3.5 h-3.5 text-muted-foreground absolute left-3 top-1/2 -translate-y-1/2" />
              <input
                type="text"
                value={searchInput}
                onChange={(e) => setSearchInput(e.target.value)}
                placeholder="Cari nama atau email..."
                className="w-full pl-9 pr-3 py-2 rounded-xl bg-secondary border border-border text-foreground text-xs focus:outline-none focus:border-[#f0b000]"
              />
            </form>
          </div>

          {/* Table */}
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-secondary/60 text-muted-foreground border-b border-border">
                <tr>
                  <th className="py-3 px-4 font-semibold">Pengguna</th>
                  <th className="py-3 px-3 font-semibold">Role</th>
                  <th className="py-3 px-3 font-semibold">Verifikasi Email</th>
                  <th className="py-3 px-3 font-semibold">Dompet Aktif</th>
                  <th className="py-3 px-3 font-semibold">Total Saldo</th>
                  <th className="py-3 px-3 font-semibold">Transaksi</th>
                  <th className="py-3 px-3 font-semibold">Chatbot</th>
                  <th className="py-3 px-4 font-semibold">Tanggal Daftar</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {users.length === 0 ? (
                  <tr>
                    <td colSpan={8} className="py-8 text-center text-muted-foreground">
                      {loading ? "Memuat data pengguna..." : "Tidak ada pengguna yang cocok dengan pencarian."}
                    </td>
                  </tr>
                ) : (
                  users.map((u) => (
                    <tr key={u.id} className="hover:bg-secondary/40 transition-colors">
                      {/* Name & Email */}
                      <td className="py-3 px-4">
                        <div className="flex items-center gap-3">
                          <div className="w-8 h-8 rounded-full bg-accent border border-[#f0b000]/30 flex items-center justify-center font-bold text-xs text-[#8a6300] dark:text-[#f0b000] shrink-0">
                            {u.full_name ? u.full_name.charAt(0).toUpperCase() : "U"}
                          </div>
                          <div>
                            <div className="font-semibold text-foreground">{u.full_name}</div>
                            <div className="text-[11px] text-muted-foreground">{u.email}</div>
                          </div>
                        </div>
                      </td>

                      {/* Role */}
                      <td className="py-3 px-3">
                        <span
                          className={`inline-block px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider ${
                            u.role === "admin"
                              ? "bg-rose-500/10 text-rose-600 dark:text-rose-400 border border-rose-500/20"
                              : "bg-secondary text-muted-foreground border border-border"
                          }`}
                        >
                          {u.role}
                        </span>
                      </td>

                      {/* Verification Status */}
                      <td className="py-3 px-3">
                        {u.is_verified ? (
                          <span className="inline-flex items-center gap-1 text-emerald-600 dark:text-emerald-400 font-semibold text-[11px]">
                            <CheckCircle2 className="w-3.5 h-3.5" />
                            <span>Terverifikasi</span>
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1 text-amber-500 font-semibold text-[11px]">
                            <Clock className="w-3.5 h-3.5" />
                            <span>Pending OTP</span>
                          </span>
                        )}
                      </td>

                      {/* Wallets */}
                      <td className="py-3 px-3 font-medium text-foreground">
                        {u.wallet_count} Dompet
                      </td>

                      {/* Total Balance */}
                      <td className="py-3 px-3 font-bold text-foreground">
                        Rp {intFormat(u.total_balance)}
                      </td>

                      {/* Transactions */}
                      <td className="py-3 px-3 text-muted-foreground">
                        {u.transaction_count} transaksi
                      </td>

                      {/* Chatbot Linked */}
                      <td className="py-3 px-3">
                        {u.has_bot_linked ? (
                          <span className="inline-flex items-center gap-1 text-emerald-600 dark:text-emerald-400 font-semibold text-[11px]">
                            <Bot className="w-3.5 h-3.5" />
                            <span>Aktif</span>
                          </span>
                        ) : (
                          <span className="text-muted-foreground text-[11px]">-</span>
                        )}
                      </td>

                      {/* Created At */}
                      <td className="py-3 px-4 text-muted-foreground text-[11px]">
                        {new Date(u.created_at).toLocaleDateString("id-ID", {
                          day: "numeric",
                          month: "short",
                          year: "numeric",
                        })}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          {/* Pagination Controls */}
          {totalUsers > 15 && (
            <div className="flex items-center justify-between pt-4 border-t border-border text-xs text-muted-foreground">
              <span>Halaman {page} dari {Math.ceil(totalUsers / 15)}</span>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  disabled={page <= 1}
                  onClick={() => loadUsers(page - 1, search)}
                  className="px-3 py-1.5 rounded-lg bg-secondary hover:bg-accent disabled:opacity-40 border border-border transition-all"
                >
                  Sebelumnya
                </button>
                <button
                  type="button"
                  disabled={page >= Math.ceil(totalUsers / 15)}
                  onClick={() => loadUsers(page + 1, search)}
                  className="px-3 py-1.5 rounded-lg bg-secondary hover:bg-accent disabled:opacity-40 border border-border transition-all"
                >
                  Selanjutnya
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    );
}

function intFormat(val: number): string {
  return Math.round(val).toLocaleString("id-ID");
}

