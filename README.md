# AI-Finance: Smart Wealth, Budgeting & AI Financial Planner

Platform manajemen keuangan pribadi cerdas bertenaga AI dengan pencatatan pengeluaran tanpa hambatan (*zero-friction*) via chatbot WhatsApp & Telegram, multi-wallet statis, pelacak anggaran, simulasi FIRE (*Financial Independence, Retire Early*), dan asisten diskusi **AI Financial Planner** yang hangat & berbasis data.

---

## 🌟 Fitur Utama

1. **Auto-Dynamic Database Schema (Pola `ai-trading-agent`):**
   - Mendukung deployment database PostgreSQL di IP server terpisah (*remote VPS / cloud host*) maupun lokal di dalam Docker Compose.
   - Seluruh tabel dibuat secara otomatis (`Base.metadata.create_all()`) saat startup.
   - Kolom-kolom baru di masa depan ter-update secara otomatis dan dinamis (*self-healing schema DDL*) tanpa perlu menjalankan migrasi manual.
2. **Pencatatan Multimodal via Chatbot (Telegram & WhatsApp):**
   - Teks kasual bahasa Indonesia (*"kopi kenangan 28rb pake gopay"* -> tercatat otomatis).
   - Voice note audio (ditranskripsikan via 9router Audio / Whisper).
   - Foto struk kasir / nota belanja (dianalisis dengan 9router Vision OCR).
   - Dilengkapi simulator chatbot bawaan di browser untuk pengujian instan.
3. **Pengelolaan Dompet Statis (Multi-Wallet):**
   - Kelola akun riil Anda (Bank BCA, Mandiri, Cash Dompet, GoPay, OVO, Bibit, dll.) tanpa butuh integrasi Open Banking pihak ketiga.
   - Transfer antar-dompet dengan penyesuaian saldo otomatis.
4. **AI Financial Planner (Modular Skills & Progressive Profiling):**
   - Dilengkapi pustaka keahlian modular (`backend/skills/planner/`) mencakup 7 pilar perencanaan keuangan + psikologi keuangan (*behavioral coaching*).
   - Gaya ngobrol natural (*Adaptive Warm Mentor*), menyesuaikan sapaan (`aku/kamu`, `gue/lo`, `saya/Anda`), tanpa klaim lisensi profesi dan tanpa spam disclaimer di tiap bubble chat.
   - Personalisasi *zero-friction*: indikator **Akurasi Personalisasi (%)** opsional + *auto-save* fakta profil dari obrolan santai + dukungan penuh portofolio **Konvensional & Syariah**.
5. **Kalkulator & Simulator FIRE:**
   - Proyeksi target dana pensiun (*Rule of 25 / 4% Safe Withdrawal Rate*).
   - Estimasi jangka waktu mencapai Financial Freedom.

---

## 🚀 Panduan Menjalankan Sistem

### 1. Menghubungkan ke Database Remote (IP Terpisah)
Salin file template lingkungan:
```bash
cp .env.example .env
```
Buka file `.env` dan atur alamat IP database PostgreSQL Anda:
```env
DATABASE_URL=postgresql://postgres:password_anda@103.xxx.xxx.xxx:5432/ai_finance
```
Saat backend dijalankan pertama kali, ia akan otomatis membuat semua tabel, indeks, kategori default, dan starter wallets di server remote tersebut!

### 2. Menjalankan dengan Docker Compose
```bash
docker-compose up --build
```
- Dashboard Web: `http://localhost:3000`
- Backend API Docs (Swagger): `http://localhost:8000/docs`

### 3. Menjalankan Secara Manual (Lokal / Development)

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
Akses dashboard di `http://localhost:3000`.

---

## 🧪 Menjalankan Pengujian (Testing)
```bash
cd backend
pytest tests/ -v
```
Semua test unit (Formula Matematika FIRE, Parser Bahasa Kasual, & Deteksi Kolom Dinamis) terverifikasi 100% lulus.

