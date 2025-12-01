# Tenant Meeting Recognition Extractor
---

## 📋 Prerequisites

### Python Version
This project requires **Python 3.11.14**

Verify your Python version:
```bash
python3 --version
```

---

## 📂 Project Structure
```
streamlit_demo/
│
├── app.py
├── requirements.txt
├── tenants.json              # Auto-generated
├── meeting_transcripts.json  # Auto-generated
└── .env                      # Add your MSAL + Azure keys here
```

---

## 🚀 Installation & Setup

### 1. Navigate to the project folder
```bash
cd Streamlit_demo
```

### 2. Install dependencies
It's recommended to use a virtual environment (venv or conda):
```bash
pip install -r requirements.txt
```

---

## ▶️ Running the Application

Start the Streamlit app:
```bash
streamlit run app.py
```

The application will automatically launch in your browser at:
```
http://localhost:8501
```

---

## 🧩 Features

### 1️⃣ Tenant Onboarding
- Generates an Admin Consent URL for onboarding new tenants
- Saves onboarded tenant IDs to `tenants.json`

### 2️⃣ Fetch Microsoft Teams Meetings
- Retrieves organizer-led meetings from the last 8 days for all onboarded tenants
- Automatically fetches meeting transcripts
- Saves structured meeting and transcript data to `meeting_transcripts.json`

### 3️⃣ View All Transcripts
- Beautiful explorer UI for browsing meetings
- Displays transcript segments organized by speaker

### 4️⃣ AI Recognition Extraction
Powered by Azure OpenAI to analyze and extract:
- Meeting purpose and objectives
- Individual contribution summaries
- Recognition-worthy actions and achievements
- Scored contribution matrix

Output is delivered in structured JSON format.

---
