# Knowledge Graph DVP Generation System

A complete end-to-end API system for automatically generating Design Verification Plans (DVP) from standards documents using knowledge graphs. This system maps document structures (Standards -> Sections -> Requirements) and uses AI to generate professional test procedures and reports.

---

## 🚀 Version 2.0: Professionalization & Optimization

This system has been recently upgraded to Version 2.0. This update focuses on making the code cleaner, more professional, and easier to integrate into other platforms.

### 🧹 Major Architectural Changes
*   **Modular API Design**: The system was split into specialized routes (`ingest`, `graph`, `retrieval`, `llm`, `dvp`). This makes the code professionally organized and allows each part to be maintained or upgraded independently.
*   **Unified Job Management**: A new `JobManager` was created to track the progress of long-running tasks. It ensures the system never "hangs" and provides real-time status updates through a single, consistent interface.
*   **Synchronous API Support**: Added a `sync` option to the generation APIs so they can return results immediately. This ensures the frontend receives data instantly without needing to poll for completion.
*   **Intelligent KG Versioning**: The Knowledge Graph now saves versioned files (`startup_v1.pkl`, `v2.pkl`) and uses a pointer to load the latest one. This prevent data loss and allows you to track changes over time.
*   **Global API Observability**: A background middleware now logs every API call, including client IP, latency (ms), and status. This makes performance tuning and debugging significantly faster.
*   **Config Hardening**: Sensitive settings like API keys were moved out of the code and into a private `.env` file. This follows security best practices and makes it easy to switch between local and production settings.

### 🐛 Key Bugs Fixed
*   **Pydantic Validation**: Fixed a crash where the server failed to respond because a required "timestamp" field was missing. All API responses are now strictly validated and consistent.
*   **Frontend Generation Failure**: Fixed an issue where the frontend stopped working because it received "Pending" instead of actual data. Synchronous mode now ensures immediate delivery of documents.
*   **Redundant KG Rebuilds**: Fixed a bug where the system rebuilt the entire graph every time it started. It now uses a smart manifest to skip files that haven't changed, saving processing time.
*   **Startup Logic Errors**: Fixed a code error that accidentally skipped the search index update and caused redundant graph saves. Re-indexing now only happens when actually needed.
*   **Manifest Key Collision**: Fixed a bug where files in different folders with the same filename confused the system. It now uses full relative paths to uniquely identify every single file.
*   **Ingest Router Duplication**: Removed duplicate router declarations that caused instability. The ingestion process is now more stable and resource-efficient.

### 📂 New Professional Utilities
*   **`src/utils/job_manager.py`**: A new central controller that tracks the state (Pending, Processing, Completed) of every background task.
*   **`src/utils/graph_loader.py`**: A shared tool that automatically finds and loads the most recent version of the Knowledge Graph based on the versioning pointer.
*   **`.env` & `.env.example`**: Standardized configuration files that keep secrets safe and allow for environment-specific customization without touching code.

---

## 📋 Table of Contents

- [Features](#features)
- [New Capabilities](#new-capabilities)
- [System Architecture](#system-architecture)
- [Prerequisites](#prerequisites)
- [Quick Start](#quick-start)
- [Web Interfaces](#web-interfaces)
- [API Endpoints](#api-endpoints)
- [Complete Workflow](#complete-workflow)
- [Configuration](#configuration)
- [Local LLM Setup](#local-llm-setup-optional)
- [Troubleshooting](#troubleshooting)
- [Project Structure](#project-structure)
- [Detailed Graph Information](#detailed-graph-information)
- [Test Categories](#test-categories)
- [Generated DVP Structure](#generated-dvp-structure)

---

## 🛠 Features

- **Knowledge Graph Construction**: Builds a multi-layer map of standards (Standards -> Chapters -> Requirements).
- **Interactive Query UI**: A web-based interface to search, browse, and export the knowledge graph.
- **Hybrid Search**: Combines keyword matching with AI-powered semantic vector search for high-precision results.
- **DVP Excel Generation**: Automates the creation of Design Verification Plans with full traceability.
- **Interactive Visualization**: Explore document connections visually using a D3.js powered graph view.
- **Traceability Matrix**: Automatically links every generated test case back to its source requirement.
- **Local LLM Support**: Compatible with local AI models (via LM Studio) and external OpenAI-compatible APIs.

---

## 💡 New Capabilities (v1.1 & v2.0)

### Instant Startup
The system loads the existing graph from disk on startup. It only processes new files added to the data folder, making restarts extremely fast.

### Intelligent Data Ingestion
Automatically detects and ignores duplicate files. You can drop new documents into the data folder anytime, and the system integrates them incrementally.

### Optimized AI Search
Uses an "effective reranking" step. Search results are evaluated by a high-precision AI model to ensure the most relevant information is always prioritized.

### Enhanced Observability
Includes deep logging for all system layers:
- **Search Transparency**: Logs raw similarity scores and reranking effects for every query.
- **LLM Debugging**: Tracks prompt sizes, snippets, and raw responses to ensure generation quality.
- **Document Tracking**: Traces the progress of Excel/Word generation sheet-by-sheet.

---

## 🏗 System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        Knowledge Graph DVP System                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌───────┐ │
│   │  Ingest  │─── │  Build   │─── │  Query   │─── │   LLM    │─── │  DVP  │ │
│   │   Data   │    │  Graph   │    │  Graph   │    │ Generate │    │ Excel │ │
│   └──────────┘    └──────────┘    └──────────┘    └──────────┘    └───────┘ │
│        │               │               │               │              │     │
│    JSON            Nodes &         Hybrid          Test Cases      Excel    │
│    Documents       Edges           Search          Generated       Output   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Data Flow

| Step | Endpoint | Description |
|------|----------|-------------|
| 1 | `POST /api/v1/ingest/local` | Reads standards documents from the `./data` folder. |
| 2 | `POST /api/v1/graph/build` | Builds the knowledge graph with nodes and links. |
| 3 | `POST /api/v1/retrieval/query` | Searches the graph for relevant requirements. |
| 4 | `POST /api/v1/llm/generate` | Generates detailed test procedures using AI. |
| 5 | `POST /api/v1/dvp/generate` | Exports everything to a professional Excel/Word file. |
| 6 | `GET /api/v1/dvp/download/{id}`| Downloads the final generated DVP document. |

---

## 🏁 Prerequisites

| Requirement | Version | Notes |
|-------------|---------|-------|
| Python | 3.10+ | Required for modern library support. |
| RAM | 8GB+ | Recommended for handling large documents. |
| Disk Space | 2GB+ | Space for document data and saved graph files. |
| LLM (Optional) | - | OpenAI API or Local LLM (like LM Studio). |

---

## ⚡ Quick Start

### 1. Setup
```bash
# Create and activate virtual environment
python -m venv venv
venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt
```

### 2. Start the Server
The system runs on **Port 8080** by default.
```bash
# Using the startup script
start_server.bat

# Or manually
python -m src.main
```

### 3. Build the Knowledge Graph
```bash
# 1. Ingest standards from local data
curl -X POST http://localhost:8080/api/v1/ingest/local

# 2. Build the graph (use job_id from Step 1)
curl -X POST http://localhost:8080/api/v1/graph/build -d '{"ingestion_job_id": "{job_id}"}'
```

---

## 🌐 Web Interfaces

| Interface | URL | Description |
|-----------|-----|-------------|
| **Query UI** | http://localhost:8080/api/v1/visualization/query-ui | search, view, and export results. |
| **Interactive Graph** | http://localhost:8080/api/v1/visualization/interactive | D3.js-powered visual document map. |
| **Stats Dashboard** | http://localhost:8080/api/v1/visualization/statistics-visual | charts showing document distributions. |
| **Swagger Docs** | http://localhost:8080/docs | Full interactive API documentation. |

### Query UI Features
The Query UI is the primary human interface. It allows you to:
- Filter by component name, type, and application.
- Select specific test categories (Thermal, Mechanical, etc.).
- Browse all document sections ("All Nodes").
- View results in a mini graph viewer.
- **Export to Excel** directly from the search results.

---

## 🔗 Detailed API Endpoints

### Data Ingestion
- `POST /api/v1/ingest/local`: Start loading files from the `./data` directory.
- `GET /api/v1/ingest/status/{job_id}`: Track the progress of a file load job.
- `GET /api/v1/ingest/list`: See all previous ingestion jobs.

### Graph Management
- `POST /api/v1/graph/build`: Construct the knowledge graph linking all standards.
- `GET /api/v1/graph/status/{job_id}`: Check the status of graph construction.
- `GET /api/v1/graph/statistics`: Returns node/edge counts for the current graph.

### Search & Retrieval
- `POST /api/v1/retrieval/query`: The core search engine. Supports keyword and semantic search.
- `GET /api/v1/retrieval/explain/{query_id}`: Provides details on why specific results were found.

### Document Generation
- `POST /api/v1/llm/generate`: Generates test cases from retrieved requirements.
- `POST /api/v1/dvp/generate`: Creates the final Excel (DVP) or Word (PTP) report.
- `GET /api/v1/dvp/download/{id}`: Download the generated report file.

---

## 🛠 Complete Workflow (cURL)

```bash
# Step 1: Ingest standards
curl -X POST http://localhost:8080/api/v1/ingest/local
# Expected: {"job_id": "job-123", "status": "pending"}

# Step 2: Build Knowledge Graph
curl -X POST http://localhost:8080/api/v1/graph/build \
  -H "Content-Type: application/json" \
  -d '{"ingestion_job_id": "job-123"}'

# Step 3: Query for Requirements
curl -X POST http://localhost:8080/api/v1/retrieval/query \
  -H "Content-Type: application/json" \
  -d '{
    "component_profile": {"name": "LED"},
    "test_categories": ["thermal"],
    "max_results": 10
  }'
```

---

## ⚙️ Configuration

Settings are managed in `src/config.py`.

### Environment Variables (.env)
```env
# Server
PORT=8080
DEBUG=true

# AI Settings (Optional)
OPENAI_API_BASE=http://localhost:1234/v1
OPENAI_MODEL=qwen/qwen3-vl-4b
ENABLE_RERANKING=true
```

---

## 📁 Project Structure (v2.0)
```
.
├── src/
│   ├── api/v1/          # Endpoints (Ingest, Graph, LLM, DVP)
│   ├── core/            # Logic (Graph Builder, Search Engine)
│   ├── models/          # Data Models (Pydantic schemas)
│   ├── utils/           # Utilities (Job Manager, Startup automation)
│   └── main.py          # App Entry Point
├── data/                # Your standards JSON documents
├── graph_data/          # Saved Graph files (.pkl, .json)
├── output/              # Generated reports (Excel, Word)
└── requirements.txt     # Python packages
```

---

## 📋 Detailed Graph Information

### Graph Statistics (Typical)
| Metric | Value |
|--------|-------|
| Total Nodes | 1,200 - 5,000+ |
| Standards | 3+ Main Documents |
| Clauses | 500+ Sections |
| Requirements | 500+ Statements |

### Node Types
| Type | Label | Description |
|------|-------|-------------|
| **Standard** | Red | Top-level document name (e.g., ISO-16750). |
| **Clause** | Teal | Sections and subsections within a document. |
| **Requirement**| Blue | Individual rules (statements containing "shall" or "should"). |
| **External** | Orange| References to other external standards. |

### Edge Types
| Type | Description |
|------|-------------|
| **CONTAINS_CLAUSE** | Relates a Standard to its main Sections. |
| **CONTAINS_REQ** | Relates a Clause to a specific Requirement. |
| **REFERENCES** | Links between documents (e.g., Clause 1 refers to Standard B). |
| **SIBLING_OF** | Connects chapters at the same document level. |

---

## 🧪 Test Categories

The system uses intelligent keyword grouping to find relevant data:

| Category | Typical Keywords |
|----------|------------------|
| **Thermal** | Temperature, heat, cold, thermal, heating. |
| **Mechanical** | Vibration, shock, mechanical, force, drop. |
| **Environmental**| Humidity, water, dust, salt, moisture. |
| **Electrical** | Voltage, current, power, resistance, surge. |
| **EMC** | Interference, emission, immunity, frequency. |
| **Durability** | Life cycle, endurance, long-term, aging. |

---

## 📉 Generated DVP Structure (Excel)

The system exports a professional 4-sheet report:

1. **Annex B - DVP**: The main test matrix showing procedures and criteria.
2. **Test Sequence**: Grouping of tests (EMC, Environmental, etc.).
3. **Traceability Matrix**: Mapping every requirement to its specific test ID.
4. **Source References**: Summary of all referenced clauses and standards used.

---

**Knowledge Graph DVP Generation System v2.0**
