# 🕵️‍♂️ TarcinScout: College Contact Data Scraper

[![Python Version](https://img.shields.io/badge/python-3.8%2B-blue.svg)](https://www.python.org/)
[![Flask Framework](https://img.shields.io/badge/framework-Flask-lightgrey.svg)](https://flask.palletsprojects.com/)
[![Database](https://img.shields.io/badge/database-SQLite-green.svg)](https://www.sqlite.org/)
[![Design](https://img.shields.io/badge/design-Emerald%20%26%20Charcoal-emerald.svg)](#)

**TarcinScout** is a premium, AI-powered Flask web application designed to scan academic websites, discover contact/directory subpages recursively, and extract professional contact credentials (names, roles, departments, emails, and phone numbers). The scraped details are stored in a structured database, refined using AI heuristic matching, and easily exported.

---

## 🚀 Key Features

*   **🔍 Recursive Link Discovery (Depth=2):** Crawls the target homepage, discovers internal links matching contact keywords (e.g., `contact`, `principal`, `staff`, `about`), and crawls them with a configurable cap (default: 25 pages per run).
*   **🧠 Context-Aware Role Matching:** Employs natural language heuristics to classify key institutional figures, automatically identifying roles such as **Principal/Director**, **Heads of Departments (HOD)**, and **Training & Placement Officers (TPO)**.
*   **🗄️ SQLite Storage & Deduplication:** Stores scraped contacts in a robust SQLite schema and automatically removes duplicates sharing identical credentials.
*   **📊 PostgreSQL Migration:** Includes pre-configured scripts to easily scale and migrate data from SQLite to a production PostgreSQL database.
*   **📥 Advanced Exports:** Support for exporting data to standard CSV and stylized MS Excel (.xlsx) templates using Pandas.
*   **🎨 Premium Glassmorphic UI:** Features a high-contrast Emerald & Charcoal HSL color palette, interactive hover effects, smooth transitions, and a modern crawling loader animation.

---

## 🛠️ Technology Stack

*   **Backend:** Python 3.8+, Flask
*   **HTML Parsing & Crawling:** BeautifulSoup4, Requests
*   **Data Deduplication & Analysis:** Pandas, OpenPyXL
*   **Databases:** SQLite3 (Local Dev), PostgreSQL (Production/Scalable)
*   **Frontend:** Vanilla CSS3, Google Fonts (Outfit & Inter), FontAwesome Icons

---

## ⚙️ Installation & Setup

Follow these steps to set up and run TarcinScout locally:

### 1. Clone or Open the Repository
```bash
git clone https://github.com/Pranav006svg/TarcinScout.git
cd TarcinScout
```

### 2. Set Up a Virtual Environment (Recommended)
```bash
# Windows
python -m venv venv
venv\Scripts\activate

# macOS / Linux
python3 -m venv venv
source venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables
Copy `.env.example` to a new `.env` file and insert your API credentials:
```bash
cp .env.example .env
```
Open `.env` and fill in:
*   `GEMINI_API_KEY`: API key for content refining & AI extractor functions.
*   `SERPER_API_KEY` & `SERPAPI_KEY`: Keys for the Google Search discovery engine.
*   `POSTGRESQL_URL` (Optional): Credentials for a PostgreSQL cloud/local database.

### 5. Run the Server
```bash
python app.py
```
Open your browser and navigate to **[http://127.0.0.1:5000](http://127.0.0.1:5000)**.

---

## 📊 Database Schema

TarcinScout stores contacts in the `college_contacts` table:

```sql
CREATE TABLE college_contacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    college_name TEXT,
    website_url TEXT,
    person_name TEXT,
    role TEXT,
    department TEXT,
    email TEXT,
    phone TEXT,
    address TEXT,
    source_url TEXT,
    scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## 🛡️ Scraping & Crawling Strategy

1.  **Polite Crawling:** Targets a custom User-Agent `CollegeContactScraper/1.0`, enforces a depth-limit of **2**, caps pages at **25** per run, and introduces an artificial delay (**0.5 seconds**) between requests to avoid rate limits.
2.  **Optimized Regex Filters:**
    *   *Emails:* Extracted using standard email regex.
    *   *Phone Numbers:* Custom-designed regex for Indian standard mobile prefixes (+91/6-9) and regional landline area codes.
3.  **Context Boundary Parsing:** Instead of searching plain text page-wide, the crawler inspects structured HTML container blocks (e.g. `<tr>`, `<div>`, `<p>`). When an email or phone is detected, it searches within the surrounding block boundary to correctly match the contact's name and role.
