# Knowledge Graph DVP Generation System

A complete end-to-end API system for automatically generating Design Verification Plans (DVP) from standards documents using knowledge graphs. Built with FastAPI, NetworkX, and modern web technologies.

---

## Table of Contents

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

---

## Features

- **Knowledge Graph Construction**: Build multi-layer graphs from standards documents (Standards -> Clauses -> Requirements).
- **Interactive Query UI**: Web-based interface for querying and exploring the knowledge graph.
- **Hybrid Search**: Combines Keyword Search + Semantic Vector Search + Cross-Encoder Reranking for high-precision retrieval.
- **DVP Excel Generation**: Automated generation of Design Verification Plans with traceability.
- **Interactive Visualization**: D3.js-powered graph visualization.
- **Local LLM Support**: Compatible with LM Studio and other OpenAI-compatible APIs.
- **Full Traceability**: Complete requirement-to-test mapping.

---

## New Capabilities

We have recently upgraded the system with optimization features designed to improve performance and usability.

### Instant Startup with Incremental Updates
The system now avoids rebuilding the entire graph upon every restart.
*   **Incremental Processing**: The system tracks processed files and only adds new ones.
*   **Fast Restarts**: Startup time is significantly reduced as it loads the existing graph from disk.
*   **Benefit**: Improved development workflow with faster iteration times.

### Intelligent Data Ingestion
The data handling process has been improved for reliability.
*   **Duplicate Prevention**: Automatically detects previously ingested files to prevent duplicate records.
*   **Seamless Expansion**: New files added to the data folder are integrated into the existing graph without requiring a full rebuild.

### Optimized AI Search
Retrieve relevant information with greater accuracy and efficiency.
*   **Effective Reranking**: A reranking step evaluates search results with a high-precision model to ensure the most relevant matches are prioritized.
*   **Delta Indexing**: The AI model only processes new data, avoiding redundant computations and ensuring scalability.

---

## System Architecture

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
| 1 | `POST /api/v1/ingest/local` | Load standards from `./data` directory |
| 2 | `POST /api/v1/graph/build` | Build knowledge graph with nodes & edges |
| 3 | `POST /api/v1/retrieval/query` | Query for relevant requirements |
| 4 | `POST /api/v1/llm/generate` | Generate test procedures (optional) |
| 5 | `POST /api/v1/dvp/generate` | Create Excel DVP document |
| 6 | `GET /api/v1/dvp/download/{id}` | Download generated DVP |

---

## Prerequisites

| Requirement | Version | Notes |
|-------------|---------|-------|
| Python | 3.10+ | Required |
| RAM | 8GB+ | Recommended for graph operations |
| Disk Space | 2GB+ | For data and generated files |
| LLM (Optional) | - | OpenAI API or Local LLM (LM Studio) |

---

## Quick Start

### Step 1: Clone/Navigate to Project

```bash
cd "path/to/project"
```

### Step 2: Create Virtual Environment

```bash
# Windows
python -m venv venv
venv\Scripts\activate

# Linux/Mac
python -m venv venv
source venv/bin/activate
```

### Step 3: Install Dependencies

```bash
pip install -r requirements.txt
```

### Step 4: Start the Server

The system is pre-configured to run on **Port 8080**.

**Option A (Recommended):**
Run the startup script:
```bash
start_server.bat
```

**Option B (Manual):**
```bash
python -m src.main
```
(Do NOT use `uvicorn src.main:app` without arguments, as it defaults to port 8000).

### Step 5: Verify Server is Running

```bash
curl http://localhost:8080/health
```

Expected response:
```json
{"status": "healthy", "version": "1.0.0", "timestamp": "..."}
```

### Step 6: Build the Knowledge Graph

```bash
# 1. Ingest data
curl -X POST http://localhost:8080/api/v1/ingest/local

# 2. Wait for completion (check status)
curl http://localhost:8080/api/v1/ingest/status/{job_id}

# 3. Build graph (use job_id from step 1)
curl -X POST http://localhost:8080/api/v1/graph/build \
  -H "Content-Type: application/json" \
  -d '{"ingestion_job_id": "{job_id}", "enable_structural_links": true, "enable_semantic_links": false, "enable_reference_links": true}'
```

### Step 7: Open the Query UI

Open in browser: **http://localhost:8080/api/v1/visualization/query-ui**

---

## Web Interfaces

| Interface | URL | Description |
|-----------|-----|-------------|
| **Query UI** | http://localhost:8080/api/v1/visualization/query-ui | Search and explore the knowledge graph |
| **Interactive Graph** | http://localhost:8080/api/v1/visualization/interactive | D3.js graph visualization |
| **Statistics Dashboard** | http://localhost:8080/api/v1/visualization/statistics-visual | Graph statistics with charts |
| **Swagger API Docs** | http://localhost:8080/docs | Interactive API documentation |
| **ReDoc** | http://localhost:8080/redoc | Alternative API documentation |

### Query UI Features

The Query UI (`/api/v1/visualization/query-ui`) provides:

- **Query Parameters Panel**: Set component name, type, application, test level
- **Test Category Selection**: Thermal, Mechanical, Environmental, Electrical, EMC, Durability
- **Confidence Filter**: Slider to filter by minimum relevance score
- **Three Tabs**:
  - **Query Results**: View matching requirements with relevance scores
  - **All Nodes**: Browse all nodes with search & filter
  - **Graph View**: Mini D3.js visualization of results
- **Export to Excel**: Generate DVP Excel from query results

---

## API Endpoints

### Health & Status

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Server health check |
| GET | `/docs` | Swagger API documentation |

### Data Ingestion

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/ingest/local` | Ingest from local `./data` directory |
| POST | `/api/v1/ingest/external` | Ingest from external API |
| POST | `/api/v1/ingest/upload` | Upload files directly |
| GET | `/api/v1/ingest/status/{job_id}` | Check ingestion status |

### Graph Management

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/graph/build` | Build knowledge graph |
| GET | `/api/v1/graph/statistics` | Returns node/edge counts |
| GET | `/api/v1/graph/export` | Exports the current graph to JSON/GEXF |

### Retrieval & Search

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/retrieval/query` | **Core Search Function**. Query for requirements. |
| GET | `/api/v1/retrieval/explain/{query_id}` | Explain retrieval results |

### LLM Generation (Requires LLM)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/llm/generate` | Generate test procedures |
| POST | `/api/v1/llm/generate-simple` | Simple single procedure generation |

### DVP Document

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/dvp/generate` | Generate DVP Excel |
| POST | `/api/v1/dvp/generate-ptp` | Generate PTP Word Document |
| GET | `/api/v1/dvp/download/{dvp_id}` | Download DVP file |

---

## Complete Workflow

### Using cURL Commands

```bash
# Step 1: Start the server
python -m src.main

# Step 2: Ingest data
curl -X POST http://localhost:8080/api/v1/ingest/local
# Response: {"job_id": "abc-123", "status": "pending", ...}

# Step 3: Wait for ingestion (poll status)
curl http://localhost:8080/api/v1/ingest/status/abc-123
# Wait until status is "completed"

# Step 4: Build knowledge graph
curl -X POST http://localhost:8080/api/v1/graph/build \
  -H "Content-Type: application/json" \
  -d '{
    "ingestion_job_id": "abc-123",
    "enable_structural_links": true,
    "enable_semantic_links": false,
    "enable_reference_links": true
  }'

# Step 5: Query the graph
curl -X POST http://localhost:8080/api/v1/retrieval/query \
  -H "Content-Type: application/json" \
  -d '{
    "component_profile": {
      "name": "LED Module",
      "type": "LED Module",
      "application": "automotive lighting",
      "variants": ["High", "Low"],
      "test_level": "PCB level",
      "applicable_standards": ["ISO 16750"],
      "test_categories": ["thermal", "electrical"],
      "quantity_per_test": {"Sample": 5}
    },
    "retrieval_method": "hybrid",
    "max_results": 20,
    "min_confidence": 0.2
  }'

# Step 6: Generate DVP Excel (with test cases from query)
curl -X POST http://localhost:8080/api/v1/dvp/generate \
  -H "Content-Type: application/json" \
  -d '{
    "component_profile": {...},
    "test_cases": [...],
    "output_format": "xlsx",
    "include_traceability_sheet": true
  }'

# Step 7: Download DVP
curl http://localhost:8080/api/v1/dvp/download/{dvp_id} --output DVP_Output.xlsx
```

### Using the Query UI (Recommended)

1. Open **http://localhost:8080/api/v1/visualization/query-ui**
2. Fill in component details (name, type, application)
3. Select test categories (thermal, mechanical, electrical, etc.)
4. Adjust max results and confidence threshold
5. Click **"Query Knowledge Graph"**
6. Review results in the table
7. Click **"Export to Excel"** to generate DVP

---

## Configuration

Managed in `src/config.py`.

### Key Settings

*   `PORT`: 8080
*   `ENABLE_SEMANTIC_SEARCH`: `False` (Default) - Set to `True` for AI search.
*   `ENABLE_RERANKING`: `True` (Default) - Enables Cross-Encoder for better results.

### Environment Variables

Create a `.env` file in the project root:

```env
# API Settings
APP_NAME=Knowledge Graph API
HOST=0.0.0.0
PORT=8080
DEBUG=true

# Data Paths
DATA_DIR=./data
GRAPH_STORAGE_PATH=./graph_data
VECTOR_DB_PATH=./chroma_db
OUTPUT_DIR=./output

# LLM Configuration (Optional - for test procedure generation)
OPENAI_API_KEY=not-needed
OPENAI_API_BASE=http://localhost:1234/v1
OPENAI_MODEL=qwen/qwen3-vl-4b
OPENAI_TEMPERATURE=0.2
OPENAI_MAX_TOKENS=4096

# Logging
LOG_LEVEL=INFO
LOG_FILE=./logs/app.log
```

---

## Local LLM Setup (Optional)

The system supports local LLMs via OpenAI-compatible APIs (e.g., LM Studio).

### Using LM Studio

1. **Install LM Studio**: Download from https://lmstudio.ai/
2. **Load a Model**: Download and load a model (e.g., `qwen/qwen3-vl-4b`)
3. **Start Local Server**:
   - Go to "Local Server" tab
   - Set host to `0.0.0.0` (for network access)
   - Start server on port `1234`
4. **Update Config**: Set `openai_api_base` in `src/config.py`:
   ```python
   openai_api_base: str = "http://localhost:1234/v1"
   ```

### Verify LLM Connection

```bash
curl http://localhost:1234/v1/models
```

---

## Troubleshooting

### Common Issues

| Issue | Solution |
|-------|----------|
| `Port 8080 already in use` | Kill existing process: `netstat -ano \| findstr :8080` then `taskkill //F //PID {pid}` |
| `Knowledge graph not built` | Run ingestion and graph build before querying |
| `No results found` | Lower the `min_confidence` threshold (try 0.1 or 0.2) |
| `LLM connection failed` | Check LM Studio is running and accessible |
| `ModuleNotFoundError` | Ensure virtual environment is activated |

### Check Server Status

```bash
# Health check
curl http://localhost:8080/health

# Check if graph is built
curl http://localhost:8080/api/v1/visualization/graph-data?max_nodes=5
```

### Clear and Restart

```bash
# Stop all Python processes
taskkill //F //IM python.exe

# Restart server
python -m src.main
```

---

## Project Structure

```
.
├── src/
│   ├── api/v1/                 # API Endpoint Controllers
│   │   ├── ingest.py           # Data Ingestion (JSON/PDF loading)
│   │   ├── graph.py            # Graph Building & Management
│   │   ├── retrieval.py        # Search & Context Retrieval
│   │   ├── llm.py              # GenAI Test Generation
│   │   ├── dvp.py              # DVP Excel/Word Export
│   │   └── visualization.py    # Graph Viz & Statistics
│   ├── core/
│   │   ├── graph_builder.py    # Logic to build NetworkX graph
│   │   ├── semantic_search.py  # Embeddings & Reranking Engine
│   ├── models/                 # Pydantic Data Models
│   ├── utils/                  # Helper scripts (startup.py)
│   ├── config.py               # Application Configuration
│   └── main.py                 # App Entry Point & Lifecycle
├── data/
│   ├── output_json_chunk/      # Source JSON documents (Standards)
│   └── output_images/          # Extracted Images
├── graph_data/                 # Serialized Graph (pkl/json)
├── output/                     # Generated Reports (DVP Excel, PTP Docx)
├── requirements.txt            # Python Dependencies
└── start_server.bat            # Startup Script
```

---

**Knowledge Graph DVP Generation System v1.0.0**
