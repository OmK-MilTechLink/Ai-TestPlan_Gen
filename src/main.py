"""
Main FastAPI application for Knowledge Graph DVP Generation System
"""
from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
import uvicorn

from src.config import settings
from src.api.v1 import ingest, graph, retrieval, llm, dvp, visualization
from loguru import logger
import sys
import os
import time
from fastapi import Request

# Configure logging
logger.remove()
logger.add(
    sys.stdout,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>",
    level=settings.log_level
)
logger.add(
    settings.log_file,
    rotation="500 MB",
    retention="10 days",
    level=settings.log_level
)

# Application lifespan
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events"""
    logger.info("Starting Knowledge Graph API...")
    logger.info(f"Environment: {'Development' if settings.debug else 'Production'}")
    logger.info(f"Data directory: {settings.data_dir}")
    logger.info(f"Graph storage: {settings.graph_storage_path}")

    # Initialize services
    # Initialize services
    # Run startup automation (Build Graph & Index)
    from src.utils.startup import run_startup_automation
    import src.api.v1.graph as graph_api
    
    builder, engine = run_startup_automation()
    
    if builder:
        # Inject into graph API module
        graph_api.graph_builder = builder
        if engine:
            graph_api.search_engine = engine
        logger.info("Graph API initialized with startup graph.")
    else:
        logger.warning("Startup automation failed or skipped. Graph API will need manual build.")


    yield

    # Cleanup
    logger.info("Shutting down Knowledge Graph API...")

# Create FastAPI app
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="""
    ## AI Test Plan Generator
    A professional module for automated PTP generation using Knowledge Graphs and LLMs.
    
    ### Core Capabilities:
    - **Ingest**: Multi-source standards ingestion.
    - **Graph**: Traceable Knowledge Graph construction.
    - **Retrieve**: Semantic & Graph retrieval.
    - **Generate**: AI-powered test procedure synthesis.
    - **Export**: Professional Excel/DOCX PTP generation.
    """,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Paths to exclude from access logging (high-frequency, low-value routes)
_LOG_SKIP_PATHS = {"/health", "/docs", "/redoc", "/openapi.json", "/"}

# API Request Logging Middleware
@app.middleware("http")
async def log_api_requests(request: Request, call_next):
    """Log all API requests, their execution time, and status code."""
    url_path = request.url.path

    # Skip logging for noisy infrastructure endpoints
    if url_path in _LOG_SKIP_PATHS:
        return await call_next(request)

    start_time = time.time()
    client_ip = request.client.host if request.client else "Unknown"
    method = request.method
    
    logger.info(f"API Request START | {client_ip} | {method} {url_path}")
    
    try:
        response = await call_next(request)
        process_time = (time.time() - start_time) * 1000  # Convert to ms
        status_code = response.status_code
        logger.info(f"API Request END   | {client_ip} | {method} {url_path} | Status: {status_code} | Latency: {process_time:.2f}ms")
        
        # Optionally add latency header to response
        response.headers["X-Process-Time"] = f"{process_time:.2f}ms"
        return response
    except Exception as e:
        process_time = (time.time() - start_time) * 1000
        logger.error(f"API Request FAILED | {client_ip} | {method} {url_path} | Latency: {process_time:.2f}ms | Error: {str(e)}")
        raise

# Include routers
app.include_router(
    ingest.router,
    prefix="/api/v1/ingest",
    tags=["Data Ingestion"]
)
app.include_router(
    graph.router,
    prefix="/api/v1/graph",
    tags=["Knowledge Graph"]
)
app.include_router(
    retrieval.router,
    prefix="/api/v1/retrieval",
    tags=["Context Retrieval"]
)
app.include_router(
    llm.router,
    prefix="/api/v1/llm",
    tags=["LLM Generation"]
)
app.include_router(
    dvp.router,
    prefix="/api/v1/dvp",
    tags=["DVP Generation"]
)
app.include_router(
    visualization.router,
    prefix="/api/v1/visualization",
    tags=["Visualization"]
)

# Mount static files
app.mount("/static/output", StaticFiles(directory=settings.output_dir), name="output")
if os.path.exists(settings.input_images_dir):
    app.mount("/static/images", StaticFiles(directory=settings.input_images_dir), name="images")

# Root endpoint
@app.get("/")
async def root():
    """API root endpoint"""
    return {
        "status": "online",
        "module": "ai-testplan-gen",
        "version": settings.app_version,
        "docs": "/docs",
        "health": "/health"
    }

# Health check
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    from datetime import datetime
    return {
        "status": "healthy",
        "version": settings.app_version,
        "timestamp": datetime.now().isoformat()
    }

# Error handlers
@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    """Handle HTTP exceptions"""
    logger.error(f"HTTP error: {exc.status_code} - {exc.detail}")
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.detail,
            "status_code": exc.status_code
        }
    )

@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    """Handle general exceptions"""
    logger.exception(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "detail": str(exc) if settings.debug else "An error occurred"
        }
    )

# Run application
if __name__ == "__main__":
    uvicorn.run(
        "src.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level=settings.log_level.lower()
    )
