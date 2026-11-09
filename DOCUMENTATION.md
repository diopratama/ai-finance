# AI-Finance: System Architecture, Logic Flows & Technical Documentation

Dokumen ini menyediakan spesifikasi teknis mendalam mengenai arsitektur sistem, pemodelan data relasional (ERD), alur logika bisnis (*business logic flows*), diagram alir pengguna (*user journey diagrams*), serta spesifikasi API untuk seluruh fitur di dalam ekosistem **AI-Finance**.

---

## 📑 Daftar Isi
1. [Arsitektur Sistem Tingkat Tinggi (High-Level Architecture)](#1-arsitektur-sistem-tingkat-tinggi)
2. [Diagram Relasi Entitas Database (Entity-Relationship Diagram / ERD)](#2-diagram-relasi-entitas-database-erd)
3. [Alur Logika & Diagram Fitur Sistem](#3-alur-logika--diagram-fitur-sistem)
   - [3.1. Onboarding Pengguna, Personalisasi Terpusat & Pairing Bot](#31-onboarding-pengguna-personalisasi-terpusat--pairing-bot)
   - [3.2. Zero-Based Payday Budgeting & Fund Location Linking](#32-zero-based-payday-budgeting--fund-location-linking)
   - [3.3. Multimodal Bot NLU & Operasi Semua Dompet (All-Wallet Ops)](#33-multimodal-bot-nlu--operasi-semua-dompet-all-wallet-ops)
   - [3.4. Review Portofolio Investasi & Audit Best Practice Finansial](#34-review-portofolio-investasi--audit-best-practice-finansial)
   - [3.5. Dashboard & Laporan Analitik Arus Kas Bulanan](#35-dashboard--laporan-analitik-arus-kas-bulanan)
   - [3.6. Dompet Bersama (Shared Wallets) & Role-Based Access Control](#36-dompet-bersama-shared-wallets--role-based-access-control)
   - [3.7. AI Financial Planner (Modular Skills & Progressive Profiling)](#37-ai-financial-planner-modular-skills--progressive-profiling)
   - [3.8. Keamanan Data, Backup/Restore & Password-Protected Reset](#38-keamanan-data-backuprestore--password-protected-reset)
   - [3.9. Admin Console & Top-Up Saldo Administratif](#39-admin-console--top-up-saldo-administratif)
4. [Kamus Spesifikasi API RESTful](#4-kamus-spesifikasi-api-restful)

---

## 1. Arsitektur Sistem Tingkat Tinggi

Sistem AI-Finance dibangun menggunakan arsitektur *client-server* modern yang memisahkan antarmuka pengguna interaktif (Next.js 14) dengan mesin logika bisnis dan orkestrasi AI (FastAPI Python).

```mermaid
flowchart TD
    subgraph Clients["Kanal Pengguna (Clients)"]
        WEB["Next.js 14 Web App\n(Desktop & Mobile Browser)"]
        TG["Telegram Messenger\n(@AIFinanceExpenseBot)"]
        WA["WhatsApp Messenger\n(Meta Cloud API)"]
    end

    subgraph Gateway["API & Ingress Layer"]
        INGRESS["K3s Traefik Ingress / Reverse Proxy\n(HTTPS TLS Termination)"]
    end

    subgraph Backend["FastAPI Backend Application"]
        ROUTER["FastAPI Router (/api/v1)"]
        
        subgraph Engines["Core Logic Engines"]
            NLU["NLU & Multimodal Parser\n(Text Slang, Whisper STT, Vision OCR)"]
            BUDGET_ENG["Payday & Sinking Fund Engine"]
            PORTFOLIO_ENG["Portfolio Evaluator & FIRE Engine"]
            PLANNER_ENG["AI Planner Skill Router\n(Progressive Profiler & Memory)"]
            BACKUP_ENG["Security, Backup & Restore Engine"]
        end

        SCHEMA_MGR["Self-Healing Dynamic Schema DDL\n(Auto-Migration)"]
    end

    subgraph External["Layanan Eksternal (Third-Party Services)"]
        LLM["9router AI / OpenAI Compatible API\n(LLM Chat, Audio Whisper, Vision)"]
        RESEND["Resend API\n(Email Verification Delivery)"]
        TG_API["Telegram Bot Webhook API"]
        META_API["Meta WhatsApp Cloud API"]
    end

    subgraph Storage["Penyimpanan Data (Persistence)"]
        POSTGRES[("PostgreSQL 15+\n(Relational Database)")]
    end

    WEB -->|HTTPS REST & SSE| INGRESS
    TG -->|Webhook Payload| INGRESS
    WA -->|Webhook Payload| INGRESS

    INGRESS --> ROUTER
    ROUTER --> NLU
    ROUTER --> BUDGET_ENG
    ROUTER --> PORTFOLIO_ENG
    ROUTER --> PLANNER_ENG
    ROUTER --> BACKUP_ENG

    NLU <-->|NLP / Vision / STT| LLM
    PLANNER_ENG <-->|SSE Streaming LLM| LLM
    ROUTER <-->|Kirim Email OTP| RESEND
    ROUTER <-->|Balasan Chat| TG_API
    ROUTER <-->|Balasan Pesan| META_API

    ROUTER <--> SCHEMA_MGR
    SCHEMA_MGR <--> POSTGRES
    BUDGET_ENG <--> POSTGRES
    PORTFOLIO_ENG <--> POSTGRES
    PLANNER_ENG <--> POSTGRES
    BACKUP_ENG <--> POSTGRES
```

---

## 2. Diagram Relasi Entitas Database (ERD)

Database PostgreSQL mengelola struktur relasional yang menghubungkan profil pengguna, dompet fisik/digital, pos anggaran, transaksi, hingga riwayat snapshot pencadangan.

```mermaid
erDiagram
    USERS ||--o{ WALLETS : "memiliki"
    USERS ||--o{ WALLET_MEMBERS : "bergabung_dalam"
    USERS ||--o{ TRANSACTIONS : "mencatat"
    USERS ||--o{ BUDGETS : "menyusun"
    USERS ||--o{ BUDGET_GROUPS : "mengelompokkan"
    USERS ||--o{ CATEGORIES : "mengustomisasi"
    USERS ||--o{ ACCOUNT_BACKUPS : "menyimpan_snapshot"
    USERS ||--o{ BOT_TOKENS : "menautkan_bot"
    USERS ||--o{ CFP_CHAT_MESSAGES : "berdiskusi"

    WALLETS ||--o{ WALLET_MEMBERS : "dibagikan_ke"
    WALLETS ||--o{ TRANSACTIONS : "sumber_dana"
    WALLETS ||--o{ TRANSACTIONS : "tujuan_transfer"
    WALLETS ||--o{ BUDGETS : "fund_location"

    BUDGET_GROUPS ||--o{ BUDGETS : "menaungi"
    CATEGORIES ||--o{ BUDGETS : "kategori_pos"
    CATEGORIES ||--o{ TRANSACTIONS : "klasifikasi_tx"
    BUDGETS ||--o{ TRANSACTIONS : "realisasi_anggaran"

    USERS {
        uuid id PK
        string email UK
        string full_name
        string password_hash
        string role
        boolean is_verified
        string base_currency
        string personal_profile_json
        datetime created_at
    }

    WALLETS {
        uuid id PK
        uuid user_id FK
        string name
        string type
        string asset_class
        float balance
        string currency
        string color
        boolean is_default
        boolean is_archived
        datetime created_at
    }

    WALLET_MEMBERS {
        uuid id PK
        uuid wallet_id FK
        uuid user_id FK
        string role
        datetime created_at
    }

    BUDGET_GROUPS {
        uuid id PK
        uuid user_id FK
        string name
        boolean is_sinking_fund
        int sort_order
    }

    BUDGETS {
        uuid id PK
        uuid user_id FK
        uuid wallet_id FK
        uuid category_id FK
        string name
        string group_type
        float limit_amount
        float spent_amount
        string period
        string month_key
        boolean is_sinking_fund
        float rollover_balance
        float funded_this_month
        int sort_order
    }

    CATEGORIES {
        uuid id PK
        uuid user_id FK
        string name
        string type
        string color
        string icon
        boolean is_system
    }

    TRANSACTIONS {
        uuid id PK
        uuid user_id FK
        uuid wallet_id FK
        uuid to_wallet_id FK
        uuid category_id FK
        uuid budget_id FK
        string type
        float amount
        string currency
        float amount_in_base
        string description
        string merchant
        string raw_source
        datetime transaction_date
    }

    ACCOUNT_BACKUPS {
        uuid id PK
        uuid user_id FK
        string title
        string backup_type
        text summary_json
        text payload_json
        datetime created_at
    }

    BOT_TOKENS {
        uuid id PK
        uuid user_id FK
        string platform
        string token UK
        string chat_id
        string bot_username
        datetime expires_at
        boolean is_active
    }

    CFP_CHAT_MESSAGES {
        uuid id PK
        uuid user_id FK
        string role
        text content
        datetime created_at
    }
```

---

## 3. Alur Logika & Diagram Fitur Sistem

### 3.1. Onboarding Pengguna, Personalisasi Terpusat & Pairing Bot

Alur pengguna saat membuat akun baru, melengkapi profil finansial terpusat, dan menautkan bot Telegram/WhatsApp:

```mermaid
sequenceDiagram
    autonumber
    actor User as Pengguna
    participant Web as Web Frontend (/settings)
    participant Auth as Auth & Profile Service
    participant Resend as Resend Email Service
    participant BotSvc as Bot Pairing Service
    participant BotApp as Telegram / WhatsApp App

    User->>Web: Registrasi Akun (Nama Lengkap, Email, Password)
    Web->>Auth: POST /api/v1/auth/register
    Auth->>Resend: Kirim Email Verifikasi
    Auth-->>Web: Akun dibuat + Token Akses (JWT)
    
    User->>Web: Akses /settings?tab=financial
    User->>Web: Input Gaji, Biaya Hidup, Usia, Target FIRE, Toleransi Risiko, Preferensi Syariah
    Web->>Auth: PUT /api/v1/planner/personal-profile
    Auth-->>Web: Update Profile Completeness (%) & Model Portofolio Referensi

    User->>Web: Klik "Hubungkan Akun Telegram / WhatsApp"
    Web->>BotSvc: POST /api/v1/bot/generate-code (Platform: TELEGRAM)
    BotSvc-->>Web: Kode Unik 6 Digit (TTL 15 Menit)
    Web-->>User: Tampilkan "/pair 849201"

    User->>BotApp: Kirim pesan "/pair 849201"
    BotApp->>BotSvc: Webhook Event (chat_id, text)
    BotSvc->>BotSvc: Validasi Kode & Hubungkan user_id dengan chat_id
    BotSvc-->>BotApp: "✅ Akun Anda berhasil terhubung dengan AI-Finance!"
    Web->>BotSvc: GET /api/v1/bot/status
    BotSvc-->>Web: Status Telegram: Terhubung ✅
```

---

### 3.2. Zero-Based Payday Budgeting & Fund Location Linking

Konsep inti alokasi anggaran: **Setiap pos memiliki dompet penempatan dana fisik (*Fund Location*)**. Ketika gajian tiba, fitur *Payday Distribution* menghitung dan mengeksekusi transfer dari rekening gajian ke dompet tujuan.

```mermaid
flowchart TD
    START([Awal Bulan / Hari Gajian]) --> INPUT_INCOME[Tentukan Penghasilan Bersih Bulanan]
    INPUT_INCOME --> SETUP_POS[Susun Pos Anggaran & Tentukan Fund Location]
    
    subgraph PosAnggaran["Contoh Hubungan Pos ke Dompet (Fund Location)"]
        POS1["Pos: KPR Rumah (Rp 6,3jt) --> Fund Location: Bank Mandiri"]
        POS2["Pos: Bensin & Servis (Rp 1jt) --> Fund Location: Bank Danamon"]
        POS3["Pos: Belanja Harian (Rp 3jt) --> Fund Location: GoPay / Jago"]
        POS4["Pos: Sinking Fund Umrah (Rp 2jt) --> Fund Location: Kantong Syariah"]
    end

    SETUP_POS --> PosAnggaran
    PosAnggaran --> CALC_DIST[Hitung Kebutuhan Transfer dari Rekening Gajian]
    
    CALC_DIST --> EXEC_PAYDAY{Klik '1-Click Payday Distribution'}
    EXEC_PAYDAY -->|Eksekusi Otomatis| TRANSFER[Transfer Saldo: Rekening Gajian -> Dompet Tujuan Pos]
    
    TRANSFER --> TRACKING[Transaksi Berjalan Sepanjang Bulan]
    
    subgraph SinkingFundEngine["Mesin Sinking Fund (Akhir Bulan)"]
        SF_CHECK{Apakah Pos adalah Sinking Fund?}
        SF_CHECK -->|Ya| ROLLOVER[Sisa Saldo Tidak Hangus -> Akumulasi ke Rollover Bulan Depan]
        SF_CHECK -->|Bukan| FLUSH[Sisa Saldo Menjadi Surplus Bersih / Tabungan Bebas]
    end

    TRACKING --> SinkingFundEngine
    SinkingFundEngine --> NEXT_MONTH([Mulai Siklus Bulan Baru])
```

---

### 3.3. Multimodal Bot NLU & Operasi Semua Dompet (All-Wallet Ops)

Mesin Natural Language Understanding (NLU) mendukung pemrosesan teks kasual, transkripsi pesan suara (*Whisper*), dan OCR struk kasir (*Vision*).

```mermaid
flowchart TD
    MSG_IN[Pesan Masuk dari WA / Telegram] --> CLASSIFY{Tipe Konten Pesan}
    
    CLASSIFY -->|Audio / Voice Note| STT[Transkripsi Audio ke Teks via Whisper]
    CLASSIFY -->|Gambar / Foto Struk| OCR[Ekstraksi Merchant, Total & Item via Vision OCR]
    CLASSIFY -->|Teks Kasual| TEXT[Teks Pesan Langsung]

    STT --> NLU[NLU Parser Engine]
    OCR --> NLU
    TEXT --> NLU

    NLU --> INTENT{Deteksi Niat Transaksi / Perintah}

    INTENT -->|Command: /laporan| REP_CMD[Ambil Summary Bulanan -> Format Pesan Laporan -> Balas Chat]
    INTENT -->|Command: /portofolio| PORT_CMD[Ambil Review Portofolio & Best Practice -> Format Pesan -> Balas Chat]
    
    INTENT -->|Tambah Saldo / Topup| OP_ADD[Deteksi Dompet Tujuan & Nominal\nContoh: 'tambah saldo bibit 1jt'\nSaldo Dompet Bertambah (+)]
    
    INTENT -->|Kurangi Saldo / Tarik| OP_SUB[Deteksi Dompet Sumber & Nominal\nContoh: 'tarik dana bibit 500rb'\nSaldo Dompet Berkurang (-)]
    
    INTENT -->|Transfer Antar-Dompet| OP_TRF[Deteksi Dompet Asal & Tujuan\nContoh: 'transfer 1jt mandiri ke bibit'\nMutasi Saldo Asal (-) & Saldo Tujuan (+)]
    
    INTENT -->|Pencatatan Pengeluaran Harian| OP_EXP[Deteksi Kata Kunci Pos Anggaran & Merchant\nContoh: 'isi bensin 250rb']

    OP_EXP --> MATCH_BUDGET{Apakah Cocok dengan Pos Anggaran?}
    MATCH_BUDGET -->|Ya| DEDUCT_FUND_LOC[Otomatis Potong Dompet 'Fund Location' Terkait Pos Tersebut]
    MATCH_BUDGET -->|Tidak| DEDUCT_DEFAULT[Potong Dompet Default / Spesifik yang Disebut]

    OP_ADD --> SAVE_TX[Catat Record Transaksi ke Database]
    OP_SUB --> SAVE_TX
    OP_TRF --> SAVE_TX
    DEDUCT_FUND_LOC --> SAVE_TX
    DEDUCT_DEFAULT --> SAVE_TX

    SAVE_TX --> SEND_REPLY[Kirim Konfirmasi Balasan ke WhatsApp / Telegram]
```

---

### 3.4. Review Portofolio Investasi & Audit Best Practice Finansial

Sistem secara cerdas mengelompokkan dompet investasi ke dalam 5 kelas aset dan membandingkannya dengan kaidah perencanaan keuangan:

```mermaid
flowchart TD
    FETCH_WALLETS[Ambil Semua Dompet Pengguna] --> FILTER_INV[Filter Dompet Investasi / asset_class Terisi]
    
    subgraph AutoInference["Mesin Inferensi Otomatis Nama Dompet"]
        NAME_CHECK{Deteksi Nama / Tipe Dompet}
        NAME_CHECK -->|Bibit, Bareksa, Stockbit, Saham, RDN| SET_EQ[Kelas Aset: EQUITY]
        NAME_CHECK -->|SBN, Sukuk, Obligasi, Fixed Income| SET_BOND[Kelas Aset: BOND]
        NAME_CHECK -->|Pasar Uang, Deposito, Likuid| SET_MM[Kelas Aset: MONEY_MARKET]
        NAME_CHECK -->|Emas, Antam, Pegadaian, Pluang Gold| SET_GOLD[Kelas Aset: GOLD]
        NAME_CHECK -->|TokoCrypto, Indodax, Binance, Crypto| SET_CRYPTO[Kelas Aset: CRYPTO]
    end

    FILTER_INV --> AutoInference
    AutoInference --> AGGREGATE[Hitung Total Saldo Aktual per Kelas Aset]

    AGGREGATE --> BENCHMARK[Ambil Model Portofolio Referensi Berdasarkan Profil Risiko & Preferensi Syariah]
    
    subgraph AuditBestPractices["Audit 4 Kaidah Best Practice Finansial"]
        BP1["1. Dana Darurat Likuid: Minimal 3-6 Bulan Pengeluaran Terpenuhi Sebelum Investasi Agresif"]
        BP2["2. Invested Ratio vs Cash Drag: Minimal 20% Net Worth Terinvestasi (Cegah Erosi Inflasi)"]
        BP3["3. Batas Risiko Spekulatif: Alokasi Crypto / High-Risk <= 15%"]
        BP4["4. Diversifikasi Aset: Minimal 2 Kelas Aset Terisi"]
    end

    BENCHMARK --> AuditBestPractices
    AuditBestPractices --> REBALANCING_CALC[Kalkulasi Rebalancing: Delta Nominal = Saldo Aktual - Saldo Target]
    
    REBALANCING_CALC --> CLASSIFY_DELTA{Evaluasi Posisi Tiap Kelas Aset}
    CLASSIFY_DELTA -->|Delta > +3%| OVER[OVERWEIGHT: Rekomendasi Realisasi / Tahan Penambahan]
    CLASSIFY_DELTA -->|Delta < -3%| UNDER[UNDERWEIGHT: Rekomendasi Tambah Alokasi]
    CLASSIFY_DELTA -->|Antara -3% s/d +3%| BALANCED[IDEAL: Alokasi Telah Sesuai Kaidah]

    OVER --> SCORE[Hitung Alignment Score: 0 s/d 100]
    UNDER --> SCORE
    BALANCED --> SCORE
    
    SCORE --> UI_RENDER[Tampilkan pada /wallets, /dashboard, /fire & Balasan Bot Telegram /portofolio]
```

---

### 3.5. Dashboard & Laporan Analitik Arus Kas Bulanan

Alur pemrosesan data untuk menampilkan laporan summary bulanan di Web dan Telegram:

```mermaid
flowchart LR
    REQ[Request: GET /transactions/summary?month=YYYY-MM] --> PARSE_MONTH[Ekstraksi Rentang Tanggal Bulan Terpilih]
    
    PARSE_MONTH --> Q_CURR[Kueri Transaksi Bulan Terpilih (INCOME & EXPENSE)]
    PARSE_MONTH --> Q_PREV[Kueri Transaksi 1 Bulan Sebelumnya (Untuk Kalkulasi MoM%)]
    PARSE_MONTH --> Q_6M[Kueri Agregasi Bulanan 6 Bulan Terakhir (Untuk Bar Chart)]
    
    Q_CURR --> CALC_TOTALS[Hitung Total Pemasukan, Total Pengeluaran & Net Cashflow]
    CALC_TOTALS --> CALC_SR[Hitung Savings Rate % = Net Cashflow / Total Pemasukan * 100]
    
    Q_PREV --> CALC_MOM[Hitung Pertumbuhan MoM%: (Bulan Ini - Bulan Lalu) / Bulan Lalu * 100]
    
    Q_CURR --> CAT_GROUP[Kelompokkan Berdasarkan Kategori -> Hitung Persentase Distribusi]
    Q_CURR --> WALLET_GROUP[Kelompokkan Mutasi Masuk/Keluar per Dompet Aktif]
    
    CALC_TOTALS --> MERGE[Gabungkan ke Struktur MonthlyTransactionMetrics]
    CALC_SR --> MERGE
    CALC_MOM --> MERGE
    Q_6M --> MERGE
    CAT_GROUP --> MERGE
    WALLET_GROUP --> MERGE
    
    MERGE --> RES[Respons JSON Ringkasan Finansial Bulanan]
```

---

### 3.6. Dompet Bersama (Shared Wallets) & Role-Based Access Control

Mekanisme kolaborasi keuangan antar-pengguna (misal: dompet keluarga, kas bersama):

```mermaid
sequenceDiagram
    autonumber
    actor Owner as Pemilik Dompet (Owner)
    actor Member as Anggota (Partner / Editor)
    participant API as Wallets Service
    participant DB as PostgreSQL Database

    Owner->>API: POST /api/v1/wallets/{id}/members (email: partner@domain.com, role: EDITOR)
    API->>DB: Cari User berdasarkan email & buat record di tabel wallet_members
    DB-->>API: Member terdaftar
    API-->>Owner: "Anggota berhasil ditambahkan"

    Member->>API: GET /api/v1/wallets
    API->>DB: Kueri Dompet Pribadi + Dompet yang Dibagikan (Shared Wallets)
    DB-->>API: Daftar Dompet (Termasuk badge is_shared: true, access_role: EDITOR)
    API-->>Member: Render Dompet Bersama di Antarmuka Pengguna

    Member->>API: POST /api/v1/transactions (wallet_id: dompet_bersama, amount: 150000)
    API->>API: Cek Hak Akses (access_role != VIEWER) -> Validasi Lolos
    API->>DB: Catat Transaksi (user_id: Partner, wallet_id: dompet_bersama)
    API->>DB: Potong Saldo Dompet Bersama
    API-->>Member: Transaksi Berhasil Dicatat

    Owner->>API: GET /api/v1/transactions (Filter: Dompet Bersama)
    API-->>Owner: Tampilkan riwayat dengan penanda "Dicatat oleh: Partner"
```

---

### 3.7. AI Financial Planner (Modular Skills & Progressive Profiling)

Arsitektur diskusi perencanaan keuangan berbasis *Server-Sent Events (SSE)*:

```mermaid
flowchart TD
    USER_PROMPT[Pesan Pertanyaan Pengguna] --> ROUTER[Skill Router Engine]
    
    subgraph SkillModules["Pustaka Keahlian Perencanaan Keuangan"]
        SKILL1[Cashflow & Emergency Fund]
        SKILL2[Debt Management & DSR]
        SKILL3[FIRE & Retirement Modeling]
        SKILL4[Investment Portfolio & Asset Allocation]
        SKILL5[Behavioral Coaching & Empathy]
    end

    ROUTER --> SkillModules
    
    subgraph ContextBuilder["Penyusun Konteks Sistem (Dynamic Prompt)"]
        GET_PROFILE[Ambil Profil Finansial Pengguna & Catatan Hidup / Memory]
        GET_HEALTH[Hitung Health Score, Target FIRE & Status Portofolio]
        DETECT_TONE[Deteksi Gaya Bahasa Lawan Bicara: aku/kamu, gue/lo, formal]
        GET_PROFILE --> ASSEMBLE[Rakit Prompt dengan Pedoman Warm Mentor & Tanpa Spam Disclaimer]
        GET_HEALTH --> ASSEMBLE
        DETECT_TONE --> ASSEMBLE
    end

    SkillModules --> ContextBuilder
    ContextBuilder --> LLM_STREAM[Kirim ke Model LLM via Streaming SSE]
    
    LLM_STREAM --> CHUNK_RECEIVE[Terima Chunk Respon Teks Real-Time]
    
    subgraph ProgressiveProfiler["Auto-Capture Profil Baru (Background Extraction)"]
        DETECT_FACTS{Apakah Pengguna Menyebut Fakta Baru?\nMisal: 'gaji naik jadi 20jt', 'punya anak 1'}
        DETECT_FACTS -->|Ya| UPDATE_DB[Simpan Otomatis ke personal_profile & memory_notes_list]
        DETECT_FACTS -->|Tidak| NOOP[Tidak Ada Pembaruan Profil]
    end

    CHUNK_RECEIVE --> ProgressiveProfiler
    CHUNK_RECEIVE --> UI_STREAM[Tampilkan Respon Mengetik Real-Time di Chat Web]
```

---

### 3.8. Keamanan Data, Backup/Restore & Password-Protected Reset

Prosedur pengamanan data dan mekanisme *factory reset* berperingkat keamanan tinggi:

```mermaid
sequenceDiagram
    autonumber
    actor User as Pengguna
    participant Web as Web /settings (Tab: Data, Backup & Reset)
    participant Auth as Auth & Security Service
    participant DB as PostgreSQL Database

    User->>Web: Pilih Mode Reset ("ZERO_WALLETS" atau "FULL_ACCOUNT_RESET")
    User->>Web: Input Kata Sandi Login Akun
    Web->>Auth: POST /api/v1/auth/reset-data (password, mode)

    Auth->>Auth: Verifikasi Hash Kata Sandi (verify_password)
    alt Kata Sandi Salah
        Auth-->>Web: 401 Unauthorized ("Kata sandi akun tidak sesuai. Proses reset dibatalkan.")
        Web-->>User: Tampilkan Peringatan Error
    else Kata Sandi Valid
        Auth->>Auth: Buat Snapshot Cadangan Otomatis (AUTO_PRE_RESET)
        Auth->>DB: INSERT INTO account_backups (title: "Auto-Backup Sebelum Reset", payload_json)
        
        alt Mode: ZERO_WALLETS
            Auth->>DB: UPDATE wallets SET balance = 0 WHERE user_id = current_user
            opt Jika Clear Transactions Dipilih
                Auth->>DB: DELETE FROM transactions WHERE user_id = current_user
            end
        else Mode: FULL_ACCOUNT_RESET
            Auth->>DB: DELETE FROM transactions, budgets, budget_groups, categories (custom), chat_history
            Auth->>DB: Hapus semua dompet lama & Buat Starter Wallets Bersaldo Rp 0
        end

        Auth-->>Web: Reset Berhasil + ID Auto-Backup
        Web-->>User: Tampilkan Notifikasi Sukses ("Data berhasil direset. Snapshot pemulihan tersimpan aman.")
    end

    opt Pemulihan Data (Restore)
        User->>Web: Klik "Restore Snapshot" atau Unggah File .JSON + Masukkan Password
        Web->>Auth: POST /api/v1/auth/restore-data (password, backup_id / backup_payload)
        Auth->>Auth: Verifikasi Password
        Auth->>DB: Timpa & Pulihkan Kembali Dompet, Transaksi, Anggaran & Profil
        Auth-->>Web: Data Pulih 100%
    end
```

---

### 3.9. Admin Console & Top-Up Saldo Administratif

Alur khusus peran administrator (`role == "ADMIN"`) untuk memantau integritas ekosistem dan intervensi saldo:

```mermaid
flowchart TD
    ADMIN_REQ[Admin Login & Akses /admin] --> AUTH_CHECK{Cek Hak Akses Pengguna}
    
    AUTH_CHECK -->|Bukan Admin| FORBIDDEN[Tolak Akses: 403 Forbidden]
    AUTH_CHECK -->|Role Admin| ALLOW[Beri Akses Admin Console]

    ALLOW --> STATS[GET /api/v1/admin/stats]
    STATS --> RENDER_STATS[Tampilkan Metrik: Total Pengguna, Email Terverifikasi, User Aktif 30 Hari, Total Saldo Seluruh Sistem, Total Transaksi, Adopsi Bot]

    ALLOW --> USERS_LIST[GET /api/v1/admin/users?search=...]
    USERS_LIST --> RENDER_USERS[Tampilkan Tabel Pengguna, Status Verifikasi, Jumlah Dompet & Transaksi]

    RENDER_USERS --> ACTION_TOPUP[Pilih Pengguna & Eksekusi Penyesuaian Saldo]
    ACTION_TOPUP --> EXEC_TOPUP[POST /api/v1/admin/users/{id}/topup]
    EXEC_TOPUP --> LOG_TX[Sistem Menambah Saldo Dompet Default & Mencatat Transaksi 'TOPUP / PENYESUAIAN ADMIN']
    LOG_TX --> NOTIF[Perbarui Saldo Pengguna Secara Real-Time]
```

---

## 4. Kamus Spesifikasi API RESTful

Seluruh rute API diawali dengan prefiks `/api/v1`:

| Modul | Method | Endpoint | Deskripsi & Parameter |
| :--- | :--- | :--- | :--- |
| **Auth** | `POST` | `/auth/register` | Mendaftarkan pengguna baru (wajib `full_name`, `email`, `password`) |
| | `POST` | `/auth/login` | Otentikasi pengguna, mengembalikan Bearer JWT Token |
| | `GET` | `/auth/profile` | Mengambil data profil pengguna yang sedang login |
| | `PUT` | `/auth/profile` | Memperbarui nama lengkap, email, atau mata uang acuan |
| | `PUT` | `/auth/change-password` | Mengubah kata sandi pengguna |
| | `GET` | `/auth/backups` | Mengambil daftar riwayat snapshot backup tersimpan |
| | `POST` | `/auth/backups` | Membuat Cloud Snapshot akun secara manual |
| | `GET` | `/auth/backups/{id}/export`| Mengunduh payload snapshot backup dalam format JSON |
| | `DELETE`| `/auth/backups/{id}` | Menghapus snapshot backup tertentu |
| | `POST` | `/auth/reset-data` | **Wajib Password**: Eksekusi `ZERO_WALLETS` atau `FULL_ACCOUNT_RESET` |
| | `POST` | `/auth/restore-data` | **Wajib Password**: Memulihkan data dari snapshot / payload JSON |
| **Wallets** | `GET` | `/wallets` | Mengambil daftar semua dompet (pribadi, bersama, investasi) + skor portofolio |
| | `POST` | `/wallets` | Membuat dompet baru (mendukung parameter `asset_class`) |
| | `PUT` | `/wallets/{id}` | Memperbarui informasi dompet atau kelas aset |
| | `DELETE`| `/wallets/{id}` | Menghapus / mengarsipkan dompet |
| | `POST` | `/wallets/transfer` | Memindahkan saldo antar-dompet secara internal |
| | `POST` | `/wallets/{id}/members` | Menambahkan anggota ke dompet bersama (`role: EDITOR/VIEWER`) |
| | `DELETE`| `/wallets/{id}/members/{uid}` | Menghapus akses anggota dari dompet bersama |
| | `GET` | `/wallets/portfolio-review` | Mengambil evaluasi mendalam portofolio investasi vs best practice |
| **Budgets** | `GET` | `/budgets` | Mengambil daftar alokasi anggaran bulanan (`?month=YYYY-MM`) |
| | `POST` | `/budgets` | Menambahkan pos anggaran baru dengan tautan Fund Location |
| | `PUT` | `/budgets/{id}` | Memperbarui nominal limit, pos sinking fund, atau dompet penempatan |
| | `DELETE`| `/budgets/{id}` | Menghapus pos anggaran |
| | `POST` | `/budgets/distribute-payday` | Eksekusi distribusi gajian 1-klik ke dompet tujuan pos |
| | `POST` | `/budgets/copy-month` | Menduplikasi susunan pos anggaran dari bulan sebelumnya |
| | `GET` | `/budgets/groups` | Mengambil daftar grup anggaran (`Living Needs`, `Lifestyle`, dll.) |
| | `POST` | `/budgets/groups` | Membuat grup anggaran custom baru |
| **Transactions** | `GET` | `/transactions` | Mengambil daftar transaksi dengan filter tipe, dompet, pos, dan `?month=YYYY-MM` |
| | `POST` | `/transactions` | Mencatat transaksi pengeluaran/pemasukan baru secara manual |
| | `DELETE`| `/transactions/{id}` | Menghapus transaksi dan mengembalikan saldo dompet |
| | `GET` | `/transactions/summary` | Mengambil analitik arus kas bulanan, MoM%, tren 6 bulan & distribusi |
| **Webhooks & Bot** | `POST` | `/webhooks/telegram` | Webhook penerima payload chat, audio, dan foto struk Telegram |
| | `POST` | `/webhooks/whatsapp` | Webhook penerima pesan masuk Meta WhatsApp Cloud API |
| | `POST` | `/webhooks/simulate-chat` | Simulator pengujian NLU langsung di browser |
| | `POST` | `/bot/generate-code` | Menghasilkan kode pairing 6 digit (berlaku 15 menit) |
| | `GET` | `/bot/status` | Mengecek status koneksi akun WhatsApp & Telegram |
| **Planner & FIRE** | `GET` | `/planner/health-score` | Mengambil skor kesehatan finansial, target FIRE, dan konteks profil |
| | `PUT` | `/planner/personal-profile` | Menyimpan preferensi finansial & akurasi personalisasi secara terpusat |
| | `POST` | `/planner/chat` | SSE Streaming endpoint untuk percakapan interaktif bersama AI Planner |
| | `GET` | `/planner/history` | Mengambil riwayat percakapan chat AI |
| | `DELETE`| `/planner/history` | Membersihkan riwayat obrolan |
| | `GET` | `/fire/profile` | Mengambil parameter Rule of 25, proyeksi pensiun, dan alokasi aset |
| | `POST` | `/fire/calculate` | Kalkulasi interaktif simulasi target angka FIRE kustom |
| **Admin** | `GET` | `/admin/stats` | Statistik agregat seluruh sistem (Khusus role ADMIN) |
| | `GET` | `/admin/users` | Daftar seluruh pengguna terdaftar beserta ringkasan keuangannya |
| | `POST` | `/admin/users/{id}/topup` | Penyesuaian / top-up saldo administratif ke akun pengguna terpilih |

---

*Dokumentasi ini disusun dan diperbarui secara otomatis seiring dengan evolusi basis kode AI-Finance.*
