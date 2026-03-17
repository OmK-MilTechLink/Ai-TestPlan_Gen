"""
Pydantic models for API request/response validation
"""
from pydantic import BaseModel, Field, HttpUrl
from typing import List, Dict, Any, Optional
from enum import Enum
from datetime import datetime

# ==================== ENUMS ====================

class TestCategory(str, Enum):
    THERMAL = "thermal"
    MECHANICAL = "mechanical"
    ENVIRONMENTAL = "environmental"
    ELECTRICAL = "electrical"
    EMC = "emc"
    DURABILITY = "durability"

class RequirementType(str, Enum):
    MANDATORY = "mandatory"
    RECOMMENDED = "recommendation"
    OPTIONAL = "permission"
    PROHIBITED = "prohibition"

class JobStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"

# ==================== REQUEST MODELS ====================

class ExternalDataSourceRequest(BaseModel):
    """Request to fetch data from external API"""
    source_url: HttpUrl
    api_key: Optional[str] = None
    filters: Optional[Dict[str, Any]] = Field(default_factory=dict)

    class Config:
        json_schema_extra = {
            "example": {
                "source_url": "https://api.example.com/standards",
                "api_key": "your_api_key",
                "filters": {
                    "document_type": "standard",
                    "year": 2023
                }
            }
        }

class ComponentProfileRequest(BaseModel):
    """Component profile for DVP generation"""
    name: str = Field(..., description="Component name")
    type: str = Field(..., description="Component type (LED Module, PCB, etc.)")
    application: str = Field(..., description="Application domain")
    variants: List[str] = Field(default_factory=list, description="Component variants")
    test_level: str = Field(..., description="Test level (PCB, System, etc.)")
    applicable_standards: List[str] = Field(..., description="List of applicable standards")
    test_categories: List[TestCategory] = Field(..., description="Test categories to include")
    quantity_per_test: Dict[str, int] = Field(default_factory=dict, description="Sample quantities")
    specifications: Dict[str, str] = Field(default_factory=dict, description="Product specifications")

    class Config:
        json_schema_extra = {
            "example": {
                "name": "Transformer",
                "type": "Testing",
                "application": "Telecommunication, Medical",
                "variants": [],
                "test_level": "Component",
                "specifications": {
                    "voltage": "12",
                    "frequency": "240",
                    "current": "6",
                    "weight": "200",
                    "dimensions": "6x7x8 mm"
                },
                "applicable_standards": ["esd", "radiated", "dry-heat"],
                "test_categories": ["electrical", "environmental", "emc"],
                "quantity_per_test": {}
            }
        }

class RetrievalQueryRequest(BaseModel):
    """Request for retrieving relevant context from knowledge graph"""
    component_profile: ComponentProfileRequest
    retrieval_method: str = Field(default="hybrid", description="Search method: semantic, graph, hybrid")
    max_results: int = Field(default=15, ge=1, le=200)
    min_confidence: float = Field(default=0.4, ge=0.0, le=1.0)
    include_hierarchy: bool = Field(default=True)
    include_references: bool = Field(default=True)

    class Config:
        json_schema_extra = {
            "example": {
                "component_profile": {
                    "name": "LED Module",
                    "type": "LED Module",
                    "application": "automotive",
                    "variants": ["High"],
                    "test_level": "PCB level",
                    "applicable_standards": ["ISO 16750-4"],
                    "test_categories": ["thermal"],
                    "quantity_per_test": {"RH": 3, "LH": 3}
                },
                "retrieval_method": "hybrid",
                "max_results": 15,
                "min_confidence": 0.7
            }
        }

class LLMGenerationRequest(BaseModel):
    """Request for LLM to generate test procedures"""
    retrieved_context: List[Dict[str, Any]] = Field(default_factory=list)
    component_profile: ComponentProfileRequest
    generation_mode: str = Field(default="detailed", description="brief, detailed, comprehensive")
    generation_method: str = Field(default="llm", description="Method: 'llm' or 'deterministic'")
    include_traceability: bool = Field(default=True)
    sync: bool = Field(default=True, description="Execute synchronously and return full data")

class DVPGenerationRequest(BaseModel):
    """Request to generate complete DVP document"""
    component_profile: ComponentProfileRequest
    test_cases: List[Dict[str, Any]]
    output_format: str = Field(default="xlsx", description="Output format: xlsx, json, pdf")
    include_traceability_sheet: bool = Field(default=True)
    include_visualization: bool = Field(default=False)
    sync: bool = Field(default=True, description="Execute synchronously and return download url")

# ==================== RESPONSE MODELS ====================

class IngestionResponse(BaseModel):
    """Response from data ingestion endpoint"""
    job_id: str
    status: JobStatus
    message: str
    files_fetched: int
    estimated_time_seconds: Optional[int] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)

class GraphBuildResponse(BaseModel):
    """Response from graph building endpoint"""
    job_id: str
    status: JobStatus
    message: str
    nodes_created: int
    edges_created: int
    graph_checksum: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)

class RetrievalResponse(BaseModel):
    """Response from retrieval endpoint"""
    job_id: str
    query_id: str
    status: str
    results: List[Dict[str, Any]]
    total_results: int
    retrieval_metadata: Dict[str, Any]
    timestamp: datetime = Field(default_factory=datetime.utcnow)

class LLMGenerationResponse(BaseModel):
    """Response from LLM generation endpoint"""
    job_id: str
    status: JobStatus
    test_procedures: List[Dict[str, Any]] = Field(default_factory=list)
    acceptance_criteria: List[Dict[str, Any]] = Field(default_factory=list)
    tokens_used: int = 0
    generation_time_seconds: float = 0.0
    timestamp: datetime = Field(default_factory=datetime.utcnow)

class DVPGenerationResponse(BaseModel):
    """Response from DVP generation endpoint"""
    job_id: str
    dvp_id: str = ""
    status: JobStatus
    message: str
    download_url: str = ""
    file_size_bytes: int = 0
    test_cases_count: int = 0
    requirements_covered: int = 0
    traceability_complete: bool = False
    timestamp: datetime = Field(default_factory=datetime.utcnow)

class JobStatusResponse(BaseModel):
    """Generic job status response"""
    job_id: str
    status: JobStatus
    progress_percent: float
    current_step: str
    message: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)

# ==================== DATA MODELS ====================

class StandardDocument(BaseModel):
    """Standard document metadata"""
    document_id: str
    title: str
    version: Optional[str] = None
    year: Optional[int] = None
    total_clauses: int
    total_requirements: int

class RequirementNode(BaseModel):
    """Requirement node from knowledge graph"""
    requirement_id: str
    source_standard: str
    source_clause: str
    requirement_type: RequirementType
    requirement_text: str
    test_category: Optional[TestCategory] = None
    confidence_score: float
    provenance_event_id: str

class TestProcedureNode(BaseModel):
    """Test procedure synthesized from requirements"""
    procedure_id: str
    test_standard: str
    test_name: str
    test_description: str
    detailed_procedure: str
    test_parameters: Dict[str, Any]
    operating_mode: Optional[str] = None
    source_requirements: List[str]

class TestCaseNode(BaseModel):
    """Complete test case for DVP"""
    test_id: str
    test_standard: str
    test_description: str
    test_procedure: str
    acceptance_criteria: str
    test_responsibility: str
    test_stage: str
    quantity: str
    estimated_days: int
    pcb_or_lamp: str
    remarks: Optional[str] = None
    traceability: Dict[str, Any]

# ==================== ERROR MODELS ====================

class ErrorResponse(BaseModel):
    """Standard error response"""
    error: str
    detail: Optional[str] = None
    error_code: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
