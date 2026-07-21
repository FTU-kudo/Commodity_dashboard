# 📊 Commodity Prices Tracker — Dashboard Version

Automated daily pipeline that scrapes commodity prices from [SunSirs](https://sunsirs.com/uk/) and delivers a dashboard evryday (Vietnam time, UTC+7). Try the dashboard [here](https://ftu-kudo.github.io/Commodity_dashboard/).

---

## ✨ Features
-  **Various commodity prices** — More than 500 commodity prices are updated daily
- **Incremental scraping** — only fetches new data since the last run (first run scrapes full history from 2018-01-01)
- **Fault-tolerant** — automatic retry with exponential backoff on network errors; failed days are logged to `failed_days.txt` and retried next run
- **Auto-delivery** — formatted `.xlsx` report emailed to recipients every day
- **Fully automated** — runs on GitHub Actions, no local machine required

---

## 🗂️ Project Structure

```
├── .github/
│   └── workflows/
│       └── daily_update.yml      # GitHub Actions: scrape + dashboard
│
├── scripts/
│   ├── scrape_and_update.py
│
├── docs/
│   ├── data/
│   │   ├── .gitkeep
│   │   └── commodities.json      # Commodity prices
│   └── index.html
│
├── .gitignore
├── requirements.txt
└── README.md
```

---

## ⚙️ How It Works

```
Everyday 17:30 (UTC+7)
        │
        ▼
┌─────────────────────────────┐
│  Job 1: scrape-sunsirs      │
│  • Checkout repo            │
│  • Read existing parquet    │
│  • Scrape only new days     │  ← ~30 seconds after first run
│  • Commit data back to repo │
└─────────────────────────────┘
        │
        ▼ (on success)
┌─────────────────────────────┐
│  Job 2: dashboard           │
│  • Buidling dashboard       │  
└─────────────────────────────┘
```

---

## 🚀 Setup

### 1. Fork or clone this repo

```bash
git clone https://github.com/FTU-kudo/Commodity_dashboard.git
```

### 2. Enable GitHub Actions

Go to the **Actions** tab → enable workflows if prompted.

---

## 📋 Requirements

```
requests
beautifulsoup4
pandas
openpyxl
tqdm
lxml
pyarrow
```

---

## ⚠️ Notes

- First run scrapes full history (~900+ days, ~1 hour). Subsequent runs take under 1 minute.
- SunSirs data covers Chinese commodity markets. Weekends and Chinese public holidays return no data (expected behaviour).
- Never commit `.env` or credential files — all secrets are managed via GitHub Secrets.

---

## 📄 Data Source

Data sourced from [SunSirs — China Commodity Data Group](https://sunsirs.com/).
