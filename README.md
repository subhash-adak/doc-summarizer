# DocSummarizer — Enterprise AI-Powered Document Summarization Platform

DocSummarizer is a production-grade FastAPI application that integrates with the Google Drive API to download and parse enterprise documents, utilizing **Vertex AI Gemini 2.5 Flash** for advanced real-time text summarization. 

The application is architected for speed, resilience, and clean user experience, featuring Server-Sent Events (SSE) streaming progress, fallback map-reduce chunking for extra-large documents, and dynamic PDF and CSV report builders.

---

## Architecture & Data Flow

```
┌─────────────────────────────────────────────────────────┐
│                        Client                           │
│              Browser / API Consumer                     │
│                  (HTML5 + SSE)                          │
└────────────────────────┬────────────────────────────────┘
                         │ HTTP POST /api/documents/stream
┌────────────────────────▼────────────────────────────────┐
│                   FastAPI Application                   │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐               │
│  │  /auth   │  │ /docs    │  │ /reports │               │
│  │  routes  │  │ routes   │  │ routes   │               │
│  │  └────┬─────┘  └────┬─────┘  └────┬─────┘            |
│  │       │              │              │                │
│  │  ┌────▼──────────────▼──────────────▼──────────────┐ │
│  │  │              Service Layer                      │ |
│  │  │  DriveService │ ParserService │ SummaryService  │ │
│  │  └────┬──────────────┬──────────────┬──────────────┘ │
│  └───────┼──────────────┼──────────────┼────────────────┘
           │              │              │
      Google Drive    PyMuPDF /      Vertex AI
      API (OAuth2)  python-docx     Gemini 2.5 Flash
```

### Core Pipeline Flow:
1. **OAuth2 Connection**: The client logs in with Google OAuth2 (`/auth/login`). Credentials are encrypted and cached in the session store.
2. **Document Discovery**: The app queries the configured Google Drive Folder (`DRIVE_FOLDER_ID`), listing supported files.
3. **SSE Streaming Summarization**:
   - The user selects documents and initiates a POST request to `/api/documents/stream`.
   - The backend runs an async generator, streaming progress milestones (`Downloading` -> `Parsing` -> `Summarizing`) for each file back to the browser.
   - Files are parsed in-memory (no local disk footprint).
   - If the file is extremely large, the summarizer falls back to a **Map-Reduce** parser, chunking the content and compiling the intermediate summaries before generating the final overview.
   - Per-file results are streamed instantly to populate the UI table.
4. **Report Exporting**: Once the batch is complete, the session cache unlocks the export routes (`/api/reports/csv` and `/api/reports/pdf`), delivering compiled files on the fly.

---

## Tech Stack & Core Libraries

| Layer | Component | Technical Justification |
|---|---|---|
| **Web API Framework** | FastAPI | Native async/await support, Pydantic v2 validation, self-documenting OpenAPI endpoints (`/docs`). |
| **Document Parsing** | PyMuPDF (`fitz`), `python-docx` | Native high-speed binary decoders for PDF page streams and structured DOCX paragraph tables. |
| **Summarization Engine** | Vertex AI Gemini 2.5 Flash | Large context window, optimized token throughput, low latency, and native Google IAM integration. |
| **Text Chunking** | LangChain Text Splitters | Recursive splitting to prevent token fragmenting across paragraphs for oversized files. |
| **Export Engines** | ReportLab & Python CSV | High-performance PDF document canvas layout styling and native CSV formatting. |
| **Logging** | Python `structlog` | Structured JSON log generation compatible with Cloud Run and GCP Cloud Logging. |

---

## Project Structure

```
doc-summarizer/
├── app/
│   ├── api/
│   │   └── routes/
│   │       ├── auth.py          # Google Drive OAuth2 routing flow
│   │       ├── documents.py     # File listings and summarization controllers
│   │       └── reports.py       # CSV and PDF dynamic generator endpoints
│   ├── core/
│   │   ├── config.py            # Pydantic BaseSettings environment parsing
│   │   ├── exceptions.py        # Domain-driven exceptions hierarchy
│   │   └── logging.py           # Structured structlog console/JSON layout
│   ├── models/
│   │   ├── document.py          # Google Drive entity models
│   │   └── summary.py           # Summary response schemas
│   ├── services/
│   │   ├── drive_service.py     # Stateless client wrapper for Google Drive API v3
│   │   ├── parser_service.py    # Memory-safe multi-format parser dispatcher
│   │   └── summary_service.py   # Async-wrapped Vertex AI summarization logic
│   └── utils/
│       ├── chunker.py           # Chunker utilities for large file splitting
│       └── report_builder.py    # CSV and PDF canvas composition scripts
├── templates/
│   └── index.html               # Main UI
├── static/
│   ├── css/
│   │   └── style.css            # Custom variable-based dashboard styling
│   └── js/
│       └── app.js               # Frontend controller (auth intercept, SSE streaming, layout)
├── tests/
│   ├── unit/
│   │   ├── test_parser.py       # Unit tests for multi-format parsers
│   │   └── test_chunker.py      # Unit tests for text token estimation
│   └── integration/
│       └── test_endpoints.py    # Mock/Demo integration tests for all endpoints
├── scripts/
│   ├── setup_gcp.sh             # GCP automated bootstrap bash script
│   └── setup_gcp.ps1            # GCP automated bootstrap PowerShell script
├── main.py                      # FastAPI application bootstrap
├── requirements.txt             # Declared dependency tree
├── .env.example                 # Environment configuration template
├── .gitignore                   # File ignore rules
└── README.md                    # Operational documentation
```

---

## Features & Supported Document Formats

- **Supported Extensions**:
  - **PDF (`.pdf`)**: Scanned & native text extraction via PyMuPDF.
  - **Word (`.docx`)**: Extract paragraphs, tables, and lists via python-docx.
  - **Plain Text (`.txt`, `.md`)**: Direct fallback decoding with UTF-8 and Latin-1 support.
  - **Structured Data (`.csv`)**: Row-by-row rendering before LLM digestion.
- **Enterprise-Grade UI**: Real-time progress updates, instant live-updating summary table, export options, search filters, and automatic auth-gate redirect on session expiration (401 error intercept).
- **Map-Reduce Resilience**: Handles extremely large files (e.g. 500+ pages) by partitioning text, summarizing chunks asynchronously, and synthesizing a master summary.

---

## Setup & Installation

### Prerequisites
- Python 3.11+
- Git

### 1. Clone the Repository & Install Dependencies
```bash
git clone https://github.com/subhash-adak/doc-summarizer.git
cd doc-summarizer
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Choose Execution Mode

#### Option A: Zero-Configuration Demo Mode (Quick Start)
To evaluate the application instantly with simulated files and summaries (no Google Cloud configuration required):
1. Copy the environment template:
   ```bash
   cp .env.example .env
   ```
2. Leave the placeholder credentials in `.env` as-is.
3. Run the application:
   ```bash
   uvicorn main:app --reload
   ```
The application will automatically detect the configuration placeholders and enter **Demo Mode**, loading mock files and generated summaries directly in the browser dashboard.

---

#### Option B: Production Integration (Google Workspace + Vertex AI)
To connect the application to your real Google Drive folder and Vertex AI (Gemini 2.5 Flash):

##### Additional Prerequisites:
- A Google Cloud Platform (GCP) project with the Vertex AI and Google Drive APIs enabled.
- Local Google Cloud CLI (`gcloud`) installed and authenticated.

##### Step A: Configure Environment Parameters
```bash
cp .env.example .env
# Edit .env and enter your GCP_PROJECT_ID and DRIVE_FOLDER_ID
```

##### Step B: Automated GCP Service Account Setup
Run the script for your OS. It authenticates with your gcloud session, enables APIs, builds a restricted service account, grants Vertex AI permissions, and downloads the service account key to `credentials/vertex_sa.json`:

* **macOS / Linux**:
  ```bash
  chmod +x scripts/setup_gcp.sh
  ./scripts/setup_gcp.sh
  ```
* **Windows (PowerShell)**:
  ```powershell
  Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
  .\scripts\setup_gcp.ps1
  ```

##### Step C: Configure Google Drive OAuth 2.0 Web Client
To authorize Drive file access:
1. Go to **APIs & Services** → **Credentials** in the GCP Console.
2. Click **Create Credentials** → **OAuth client ID**.
3. Set Application Type to **Web Application**.
4. Add `http://localhost:8000/auth/callback` to **Authorized redirect URIs**.
5. Save, download the credentials JSON, rename it to `oauth_credentials.json`, and place it in the `credentials/` folder.

##### Step D: Launch the Application
```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```
Open `http://localhost:8000` to interact with the dashboard, and `http://localhost:8000/docs` to read the interactive Swagger API documentation.

---

## Environment Variables Configuration

The application validates the configuration schema at startup using Pydantic Settings.

| Variable | Description | Default Value | Required |
|---|---|---|---|
| `GCP_PROJECT_ID` | Google Cloud Platform project identifier | `demo-project` | ✅ |
| `GCP_LOCATION` | Region location for Vertex AI (e.g. `us-central1`) | `us-central1` | ✅ |
| `VERTEX_MODEL` | Vertex AI Gemini model name | `gemini-2.5-flash` | ✅ |
| `DRIVE_FOLDER_ID` | Google Drive folder ID to list and download documents | `demo-folder` | ✅ |
| `OAUTH_CREDENTIALS_PATH` | Path to the OAuth2 Web Client secrets JSON | `credentials/oauth_credentials.json` | ✅ |
| `OAUTH_TOKEN_PATH` | Path to persist the user's generated OAuth2 access token | `credentials/token.json` | ✅ |
| `VERTEX_SA_PATH` | Service Account JSON credentials for Vertex AI SDK | `credentials/vertex_sa.json` | Optional (Uses ADC if omitted) |
| `SECRET_KEY` | Secret key used to encrypt FastAPI session data | `demo-secret-key-16chars-minimum` | ✅ |
| `APP_ENV` | Application environment state (`development`, `staging`, `production`) | `development` | Optional |
| `LOG_LEVEL` | Logging filter level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) | `INFO` | Optional |
| `MAX_CHUNK_SIZE` | Maximum characters per chunk for map-reduce text splits | `8000` | Optional |
| `CHUNK_OVERLAP` | Character overlap between text chunks | `200` | Optional |
| `SUMMARY_MAX_TOKENS` | Max tokens generated by the Gemini model | `4096` | Optional |
| `SUMMARY_TEMPERATURE` | Model temperature (ranges from `0.0` to `1.0`) | `0.2` | Optional |

---

## API Endpoints Reference

| Method | Path | Request Body | Response Format | Description |
|---|---|---|---|---|
| `GET` | `/` | None | `text/html` | Serves the single-page application dashboard. |
| `GET` | `/auth/login` | None | Redirect | Initiates Google OAuth2 web authorization code flow. |
| `GET` | `/auth/callback` | Query params | Redirect | OAuth2 redirection handler. Persists tokens. |
| `GET` | `/auth/logout` | None | Redirect | Clears FastAPI session cookie and local tokens. |
| `GET` | `/api/documents` | None | JSON | Returns a list of supported files in the configured folder. |
| `POST` | `/api/documents/summarize` | `{"file_ids": [...]}` | JSON | Process and summarize selected documents (blocking). |
| `POST` | `/api/documents/stream` | `{"file_ids": [...]}` | `text/event-stream` | Streams progress and live row summaries via SSE. |
| `GET` | `/api/reports/csv` | None | `text/csv` | Returns summaries in an Excel-compatible CSV file. |
| `GET` | `/api/reports/pdf` | None | `application/pdf` | Returns summaries in a styled ReportLab PDF. |
| `GET` | `/health` | None | JSON | App health check endpoint. |

---

## Testing Strategy

The repository includes both unit tests and mock integration tests to verify core logic without making live network requests.

To run the automated test suite:
```bash
pytest tests/ -v --asyncio-mode=auto
```


