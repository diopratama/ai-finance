# AI-Finance: Smart Wealth, Zero-Based Payday Budgeting & AI Financial Planner

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python: 3.12](https://img.shields.io/badge/Python-3.12-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688.svg)](https://fastapi.tiangolo.com/)
[![Next.js: 14](https://img.shields.io/badge/Next.js-14.2-black.svg)](https://nextjs.org/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15+-336791.svg)](https://www.postgresql.org/)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED.svg)](https://www.docker.com/)

**AI-Finance** adalah platform manajemen kekayaan pribadi (*personal wealth management*) komprehensif yang dirancang untuk mengotomasi seluruh siklus finansial individu dan keluarga: mulai dari alokasi gajian berbasis *Zero-Based Budgeting*, pelacakan pengeluaran instan lewat chat WhatsApp & Telegram, evaluasi portofolio investasi vs *best practice*, pelaporan keuangan bulanan interaktif, hingga kalkulasi pensiun dini (**FIRE - Financial Independence, Retire Early**) dan diskusi perencanaan keuangan bersama asisten **AI Financial Planner**.

Sistem ini aktif dan dapat diakses langsung pada: **[https://aifinance.fellow.my.id](https://aifinance.fellow.my.id)**

---

## 📑 Daftar Isi
- [Fitur Utama](#-fitur-utama)
  - [1. Alokasi Anggaran Gajian & Fund Location](#1-alokasi-anggaran-gajian--fund-location-zero-based-budgeting)
  - [2. Dompet Multi-Akun & Dompet Bersama (Shared Wallets)](#2-dompet-multi-akun--dompet-bersama-shared-wallets)
  - [3. Review & Rebalancing Portofolio Investasi](#3-review--rebalancing-portofolio-investasi-vs-best-practice)
  - [4. Dashboard & Laporan Summary Transaksi Bulanan](#4-dashboard--laporan-summary-transaksi-bulanan)
  - [5. Multimodal Bot Telegram & WhatsApp](#5-multimodal-bot-telegram--whatsapp-all-wallet-ops)
  - [6. AI Financial Planner Cerdas & Personalisasi Terpusat](#6-ai-financial-planner-cerdas--personalisasi-terpusat)
  - [7. Kalkulator FIRE & Health Score Finansial](#7-kalkulator-fire--financial-health-score)
  - [8. Keamanan Akun, Backup/Restore & Reset Data](#8-keamanan-akun-backuprestore--reset-data-terproteksi-password)
  - [9. Admin Console & Dynamic Database Schema](#9-admin-console--dynamic-database-schema)
- [Arsitektur & Tech Stack](#-arsitektur--tech-stack)
- [Panduan Instalasi & Menjalankan Sistem](#-panduan-instalasi--menjalankan-sistem)
- [Pengujian & Verifikasi (Testing)](#-pengujian--verifikasi-testing)
- [Dokumentasi Lengkap Alur & Logika](#-dokumentasi-lengkap-alur--logika)

---

## 🌟 Fitur Utama

### 1. Alokasi Anggaran Gajian & Fund Location (Zero-Based Budgeting)
- **Metode Zero-Based Payday Budgeting**: Setiap rupiah dari penghasilan bulanan dialokasikan secara sadar ke dalam pos-pos anggaran hingga tidak ada saldo yang menganggur (*idle*).
- **Fund Location Linking**: Setiap pos anggaran (misal: *KPR Rumah*, *Bensin & Parkir*, *Belanja Bulanan*, *Dana Darurat*) terhubung secara riil ke dompet/rekening penempatan dananya (*Fund Location*, e.g., Mandiri, BCA, Danamon, GoPay).
- **Distribusi Gajian 1-Klik (*1-Click Payday Distribution*)**: Menghitung kebutuhan transfer dari rekening gajian ke dompet-dompet tujuan pos secara otomatis dalam sekali klik.
- **Sinking Fund Lintas Bulan**: Dukungan pos akumulasi dana bertahap (e.g., *Pajak Tahunan*, *Servis Mobil*, *Liburan Akhir Tahun*, *Umrah*) yang otomatis mempertahankan dan menggulirkan saldo tersisa ke bulan-bulan berikutnya (*Rollover Balance*).
- **Grup Anggaran Fleksibel**: Pengelompokan dinamis (*Living Needs*, *Life Style*, *Predictable Saving*, *Zakat & Sedekah*, dll.) dengan dukungan buat grup baru, ubah nama, dan hapus/reassign.

### 2. Dompet Multi-Akun & Dompet Bersama (Shared Wallets)
- **Multi-Wallet Nyata**: Kelola kas harian (*Cash*), rekening bank (*Bank Mandiri, BCA, BRI, Jago*), dompet digital (*GoPay, OVO, ShopeePay*), hingga rekening investasi (*Bibit, Stockbit, Bareksa, RDN*) tanpa perlu koneksi Open Banking pihak ketiga.
- **Sharing Dompet Antar-Pengguna**: Fitur berbagi dompet dengan pasangan, keluarga, atau partner bisnis via email.
- **Role-Based Access Control**:
  - `OWNER`: Pemilik dompet, memiliki kendali penuh (edit, hapus, kelola anggota).
  - `EDITOR`: Anggota yang dapat mencatat pengeluaran, pemasukan, atau transfer menggunakan saldo dompet tersebut.
  - `VIEWER`: Anggota dengan hak akses read-only untuk memantau mutasi saldo.

### 3. Review & Rebalancing Portofolio Investasi vs Best Practice
- **Klasifikasi Kelas Aset Otomatis & Manual**: Setiap dompet dapat memiliki atribut `asset_class`:
  - `EQUITY` (Saham & Reksa Dana Saham)
  - `BOND` (Obligasi Negara / SBN / Sukuk)
  - `MONEY_MARKET` (Pasar Uang & Likuid)
  - `GOLD` (Emas Fisik & Logam Mulia)
  - `CRYPTO` (Aset Kripto & Alternatif)
  - *Smart Auto-Inference*: Otomatis mengenali kata kunci seperti *Bibit, Stockbit, Bareksa, Ajaib, Pluang, Pegadaian, RDN, SBN, Sukuk*.
- **Evaluasi Keselarasan Portofolio (0–100 Skor)**: Membandingkan bobot aktual portofolio dengan profil risiko referensi (*Konservatif, Moderat, Agresif* — baik varian Konvensional maupun Syariah).
- **Kalkulasi Rebalancing**: Menghitung delta nominal rupiah yang perlu ditambah (*UNDERWEIGHT*) atau dikurangi (*OVERWEIGHT*) untuk mencapai rasio ideal.
- **Audit 4 Kaidah Best Practice Finansial**:
  1. Kecukupan dana darurat likuid sebelum eksposur investasi agresif.
  2. Rasio aset produktif (*Invested Net Worth Ratio*) vs *Cash Drag*.
  3. Batas toleransi aset risiko tinggi / spekulatif (*Crypto <= 15%*).
  4. Diversifikasi multi-instrumen (minimal 2 kelas aset).

### 4. Dashboard & Laporan Summary Transaksi Bulanan
- **Filter Periode Bulanan (`YYYY-MM`)**: Memilih bulan spesifik di Dashboard maupun halaman Transaksi untuk melihat rekapitulasi data.
- **Metrik Finansial Komprehensif**:
  - Total Pemasukan & Pengeluaran bulanan.
  - Perbandingan pertumbuhan bulan-ke-bulan (*Month-over-Month / MoM%*).
  - Net Cashflow bersih dan Rasio Tabungan (*Savings Rate %*).
- **Grafik Tren Arus Kas 6 Bulan**: Visualisasi tren inflow vs outflow dan fluktuasi savings rate selama 6 bulan ke belakang.
- **Distribusi Kategori**: Breakdown proporsi pengeluaran dan pemasukan per kategori.
- **Mutasi Arus Kas per Dompet**: Rekapitulasi perputaran dana masuk dan keluar untuk setiap dompet aktif.

### 5. Multimodal Bot Telegram & WhatsApp (All-Wallet Ops)
- **Pairing Aman 15 Menit**: Hubungkan akun WhatsApp atau Telegram pengguna lewat perintah `/pair <KODE>`.
- **Input Multimodal**:
  - Teks bahasa Indonesia kasual (*"kopi kenangan 28rb pake gopay"*, *"beli token listrik 100k"*).
  - Pesan suara / Voice note (ditranskrip via Speech-to-Text).
  - Foto nota struk belanja fisik (diekstraksi via Vision OCR).
- **Operasi Finansial Lengkap Semua Dompet**:
  - **Penambahan Saldo (`INCOME` / Topup)**: *"tambah saldo bibit 1jt"*, *"topup gopay 250rb"*, *"setor rdn bca 2jt"*, *"+500rb ke jago"*.
  - **Pengurangan Saldo (`EXPENSE` / Penarikan)**: *"kurangi saldo cash 100rb uang parkir"*, *"tarik dana bibit 500rb"*, *"potong saldo mandiri 150rb admin"*.
  - **Transfer Antar-Dompet (`TRANSFER`)**: *"transfer 1jt dari mandiri ke bibit"*, *"transfer bca ke gopay 200rb"*, *"topup gopay 100rb dari bca"*, *"pindah dana 500rb dari jago ke emas pegadaian"*.
- **Perintah Laporan Instan**:
  - `/laporan` — Ringkasan pemasukan, pengeluaran, net cashflow, dan pos terbesar bulan berjalan.
  - `/portofolio` — Ringkasan nilai investasi, skor keselarasan, dan saran rebalancing langsung di chat.

### 6. AI Financial Planner Cerdas & Personalisasi Terpusat
- **Pustaka Keahlian Modular (*Skill Library*)**: Menerapkan 7 pilar financial planning (arus kas, utang/DSR, dana darurat, proteksi, investasi, pensiun, estate planning) + psikologi finansial.
- **Adaptive Warm Mentor**: Berkomunikasi dengan empati, menyesuaikan gaya bahasa lawan bicara (`aku/kamu`, `gue/lo`, `saya/Anda`), tanpa spam disclaimer di setiap respon.
- **Pengaturan Profil Terpusat (`/settings`)**:
  - Tab **Akun & Keamanan**: Nama lengkap mandatori, email terverifikasi (Resend API), mata uang acuan, dan ubah kata sandi.
  - Tab **Personalisasi Finansial (AI)**: Penghasilan bersih bulanan, pengeluaran hidup, cicilan utang bulanan, status pernikahan, jumlah tanggungan, usia saat ini, target usia pensiun, toleransi risiko, preferensi Syariah, serta visualisasi indikator kelengkapan profil (*Profile Completeness %*).

### 7. Kalkulator FIRE & Financial Health Score
- **Kaidah Baku FIRE (*Rule of 25* & *4% Safe Withdrawal Rate*)**:
  - Menghitung target angka dana pensiun bebas finansial (*FIRE Number*).
  - Menghitung proyeksi nilai aset di usia target berdasarkan tingkat pengembalian (*CAGR*) dan kemampuan menabung bulanan.
  - Status *Coast FIRE* dan estimasi tahun yang dibutuhkan hingga pensiun.
- **Financial Health Score (0–100)**: Mengevaluasi kesehatan finansial holistik mencakup rasio dana darurat, rasio cicilan utang (*Debt Service Ratio / DSR*), dan surplus kas.

### 8. Keamanan Akun, Backup/Restore & Reset Data (Terproteksi Password)
- **Verifikasi Kata Sandi**: Setiap tindakan berbahaya (*destructive actions*) mewajibkan verifikasi kata sandi aktif pengguna.
- **Fitur Reset Akun**:
  - `ZERO_WALLETS`: Mereset saldo dompet terpilih atau seluruh dompet menjadi Rp 0 (dengan opsi membersihkan riwayat transaksi).
  - `FULL_ACCOUNT_RESET`: *Factory reset* yang menghapus seluruh transaksi, pos anggaran, kategori custom, dan riwayat chat AI, mengembalikan dompet ke kondisi awal bersaldo Rp 0.
- **Pencadangan Otomatis (*Auto Pre-Reset Snapshot*)**: Sistem secara otomatis mengamankan snapshot Cloud sebelum eksekusi reset dijalankan.
- **Backup & Restore Fleksibel**:
  - Pembuatan Cloud Snapshot manual kapan saja.
  - Ekspor dan unduh file snapshot ke format `.json`.
  - Pemulihan (*Restore*) data dari Cloud Snapshot atau unggahan file `.json` lokal dengan verifikasi password.

### 9. Admin Console & Dynamic Database Schema
- **Konsol Administrator (`/admin`)**:
  - Metrik sistem global: total pengguna terdaftar, status verifikasi email, pengguna aktif 30 hari, total volume saldo dan transaksi, serta adopsi chatbot.
  - Manajemen pengguna dan fitur top-up saldo administratif.
- **Self-Healing Dynamic Schema DDL**:
  - Backend secara dinamis mendeteksi dan mengeksekusi penambahan kolom baru pada runtime PostgreSQL tanpa membutuhkan migrasi manual terpisah.

---

## 🏗 Arsitektur & Tech Stack

```
[ Frontend: Next.js 14 App Router + Tailwind CSS + Lucide Icons ]
                                │
                        (HTTPS / REST / SSE)
                                │
[ Backend: FastAPI (Python 3.12) + SQLAlchemy + Pydantic v2 ]
  ├── Services & Core Logic:
  │   ├── NLU Parser & Multimodal Handlers (Whisper / Vision)
  │   ├── FIRE Engine & Portfolio Evaluator
  │   ├── Payday Allocation & Sinking Fund Engine
  │   └── Planner Skill Router & Progressive Profiler
  └── Integration & Persistence:
      ├── External Channels: Telegram Bot API & WhatsApp Cloud API
      ├── Email Verification: Resend API
      └── Database: PostgreSQL (Auto-Schema DDL, Auto-Migration)
```

| Layer | Komponen / Teknologi | Fungsi Utama |
| :--- | :--- | :--- |
| **Frontend** | Next.js 14, React 18, Tailwind CSS, Lucide | Antarmuka pengguna responsif, Dashboard interaktif, Mode Terang/Gelap |
| **Backend API** | FastAPI, Python 3.12, Uvicorn | RESTful API, webhook parser, SSE streaming untuk chat AI |
| **Database** | PostgreSQL 15+, SQLAlchemy ORM | Relasional DB dengan migrasi mandiri (*self-healing schema*) |
| **AI / LLM** | 9router AI / OpenAI Compatible API | NLP parser transaksi kasual, transkripsi audio, analisis nota struk |
| **Bot Integrations** | Webhooks Telegram & Meta WhatsApp Cloud API | Komunikasi interaktif pencatatan dana instan via chat |
| **Deployment** | Docker, Docker Compose, Kubernetes (K3s) | Kontainerisasi multi-environment dan orchestrator produksi |

---

## 🚀 Panduan Instalasi & Menjalankan Sistem

### 1. Prasyarat Lingkungan
- Docker & Docker Compose **atau**
- Python 3.12+, Node.js 18+, dan PostgreSQL 15+

### 2. Konfigurasi Environment Variable
Salin template konfigurasi pada root project:
```bash
cp .env.example .env
```
Sesuaikan variabel utama di dalam file `.env`:
```env
# Database PostgreSQL
DATABASE_URL=postgresql://postgres:password_anda@localhost:5432/ai_finance

# Keamanan Token & JWT
SECRET_KEY=kunci_rahasia_jwt_minimal_32_karakter_acak
ACCESS_TOKEN_EXPIRE_MINUTES=10080

# Layanan AI & Bot
AI_ROUTER_BASE_URL=https://api.9router.com/v1
AI_ROUTER_API_KEY=sk-xxxx
TELEGRAM_BOT_TOKEN=xxxx:xxxx
WHATSAPP_TOKEN=xxxx
WHATSAPP_PHONE_NUMBER_ID=xxxx

# Layanan Email (Resend)
RESEND_API_KEY=re_xxxx
RESEND_FROM_EMAIL=onboarding@resend.dev
```

### 3. Menjalankan dengan Docker Compose (Direkomendasikan)
```bash
docker compose up -d --build
```
Akses layanan melalui browser:
- **Web App**: [http://localhost:3001](http://localhost:3001)
- **Backend API Docs (Swagger)**: [http://localhost:8001/docs](http://localhost:8001/docs)
- **PostgreSQL**: `localhost:5434` (port internal kontainer: `5432`)

### 4. Menjalankan Secara Manual (Development)

#### Backend (FastAPI):
```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

#### Frontend (Next.js):
```bash
cd frontend
npm install
npm run dev
```
Akses antarmuka web di [http://localhost:3000](http://localhost:3000).

---

## 🧪 Pengujian & Verifikasi (Testing)

Seluruh logika bisnis, kalkulasi finansial, parser NLU, hingga modul backup/restore diuji secara menyeluruh melalui test suite otomatis:

```bash
# Menjalankan test di container Docker lokal
docker exec -it ai_finance_backend pytest tests/ -v
```

Hasil pengujian mencakup **26/26 pengujian Pytest lulus 100%**:
- `test_investment_portfolio_inference_and_evaluation`: Deteksi kelas aset dompet, perbandingan alokasi, skor keselarasan, dan rekomendasi rebalancing.
- `test_monthly_transaction_reporting_summary`: Agregasi bulanan, perbandingan MoM%, cashflow dompet, dan distribusi kategori.
- `test_bot_all_wallets_add_subtract_transfer_and_commands`: Operasi penambahan, pengurangan, dan transfer semua dompet via NLU serta perintah `/laporan` dan `/portofolio`.
- `test_account_backup_reset_and_restore_with_password`: Pembuatan snapshot cloud, verifikasi kata sandi reset `ZERO_WALLETS` dan `FULL_ACCOUNT_RESET`, pembuatan auto-backup, dan pemulihan data.
- `test_admin_and_topup`: Kontrol akses administrator dan penyesuaian saldo.
- `test_auth_profile`: Registrasi profil mandatori, verifikasi email, dan pembaruan profil.
- `test_budget_allocation`: Logika Zero-Based Payday Budgeting, linking Fund Location, dan rollover Sinking Fund.
- `test_shared_wallet_and_transfers`: Hak akses kolaboratif dompet bersama.
- `test_financial_math`: Formulasi Rule of 25, SWR 4%, dan skor kesehatan finansial.

---

## 📚 Dokumentasi Lengkap Alur & Logika

Untuk rincian diagram arsitektur teknis, diagram Mermaid alur pengguna (*user journeys*), pemodelan relasi database (*ERD*), kalkulasi matematis finansial, dan dokumentasi API RESTful secara komprehensif, silakan pelajari dokumen:

👉 **[DOCUMENTATION.md](./DOCUMENTATION.md)**

---

## 📄 Lisensi
Didistribusikan di bawah Lisensi MIT. Lihat file `LICENSE` untuk informasi lebih lanjut.
