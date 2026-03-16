"""
Endpoint 4: LLM Generation Service
Synthesizes test procedures and acceptance criteria using LLM
"""
from fastapi import APIRouter, HTTPException, BackgroundTasks
from typing import List, Dict, Any
import uuid
from datetime import datetime
import json
from pathlib import Path

from src.models.api_models import (
    LLMGenerationRequest,
    LLMGenerationResponse,
    JobStatus,
    LLMGenerationResponse,
    JobStatus,
    JobStatusResponse,
    RetrievalQueryRequest
)
from src.config import settings
from loguru import logger
from google import genai

router = APIRouter()

# In-memory job storage
llm_jobs = {}

# LLM Client (will initialize when needed)
llm_client = None

def get_llm_client():
    """Get or create LLM client - supports local models (OpenAI) and Google Gemini"""
    global llm_client
    
    if settings.llm_provider == "gemini":
        if not settings.gemini_api_key:
            logger.error("Gemini API key not configured")
            return None
        # For the new SDK, we'll return a Client instance
        client = genai.Client(api_key=settings.gemini_api_key)
        return client
        
    if llm_client is None:
        from openai import OpenAI
        # Use local LLM server (OpenAI-compatible API)
        llm_client = OpenAI(
            api_key=settings.openai_api_key or "not-needed",
            base_url=settings.openai_api_base  # Local model endpoint
        )
        logger.info(f"LLM client initialized with base_url: {settings.openai_api_base}, model: {settings.openai_model}")
    return llm_client

def generate_test_procedure_prompt(requirement: Dict[str, Any],
                                   component_profile: Dict[str, Any]) -> str:
    """
    Generate prompt for test procedure creation
    """
    prompt = f"""You are a test engineer creating a Product Testing Plan (PTP) for automotive components.

Component Under Test:
- Name: {component_profile.get('name', 'Component')}
- Type: {component_profile.get('type', 'Unknown')}
- Application: {component_profile.get('application', 'Unknown')}
- Test Level: {component_profile.get('test_level', 'Unknown')}
- Specifications: {json.dumps(component_profile.get('specifications', {}), indent=2)}

Requirement Information:
{json.dumps(requirement, indent=2)}
Task:
1. Carefully compare the Component Specifications with the given Requirement Information.
2. Based on this comparison, determine how relevant the requirement is to the component (High, Medium, or Low). Provide this score and a one-line justification inside the 'traceability' object.
3. Based on this requirement, generate a detailed test procedure in the following JSON format:
{{
    "test_name": "Brief descriptive name (e.g., Operation at Low Temperature)",
    "test_description": "1-2 sentence description",
    "test_standard": "Source standard (e.g., ISO 16750-4)",
    "detailed_procedure": "Step-by-step test procedure with specific parameters. Include temperature, duration, operating mode, etc.",
    "test_parameters": {{
        "temperature": "value if applicable",
        "duration": "value if applicable",
        "cycles": "value if applicable"
    }},
    "operating_mode": "Operating mode description if applicable",
    "acceptance_criteria": "Clear pass/fail criteria based on requirement",
    "estimated_days": 5,
    "traceability": {
        "requirement_id": "{requirement.get('requirement_id', '')}",
        "source_clause": "{requirement.get('clause_id', '')}",
        "source_standard": "{requirement.get('document_id', '')}",
        "confidence_reasoning": "A one-line explanation of why this requirement is relevant to the component",
        "relevance_score": "High, Medium, or Low"
    }
}}

Generate a realistic and detailed test procedure that follows automotive industry standards."""

    return prompt

def generate_batch_test_procedure_prompt(requirements: List[Dict[str, Any]],
                                       component_profile: Dict[str, Any]) -> str:
    """
    Generate prompt for BATCH test procedure creation
    """
    req_texts = []
    for i, req in enumerate(requirements):
        text = req.get('text', '')[:500] # Truncate massive requirements
        req_id = req.get('requirement_id', req.get('node_id', f'REQ_{i}'))
        req_texts.append(f"Requirement {i+1} (ID: {req_id}): {text}")
        
    compiled_requirements = "\n\n".join(req_texts)

    prompt = f"""You are a test engineer creating a Product Testing Plan (PTP).

Component: {component_profile.get('name')}
Type: {component_profile.get('type')}
Specs: {json.dumps(component_profile.get('specifications', {}), indent=2)}

Requirements to Test:
{compiled_requirements}

Task:
1. Generate a list of {len(requirements)} test procedures (one for each requirement) in valid JSON format.
2. Carefully compare the Component Specs with each Requirement. Based on this comparison, assign a "relevance_score" (High, Medium, or Low) evaluating the requirement's applicability to the component's parameters.
3. IMPORTANT: You must generate a test procedure for EVERY requirement provided. Do not skip any.
4. The output must be a JSON Array of objects.

Each object must have:
- "test_name"
- "test_description"
- "detailed_procedure" (List of strings)
- "acceptance_criteria"
- "source_requirement" (Must match the ID provided above)
- "traceability": {{ "requirement_id": "...", "source_standard": "...", "confidence_reasoning": "One line explanation of relevance", "relevance_score": "High/Medium/Low" }}

Example Response Format:
[
  {{
    "test_name": "...",
    "source_requirement": "REQ_001",
    ...
  }}
]
"""
    return prompt

async def process_llm_generation(job_id: str, request: LLMGenerationRequest):
    """
    Background task for LLM generation
    """
    try:
        llm_jobs[job_id]['status'] = JobStatus.PROCESSING
        llm_jobs[job_id]['current_step'] = 'Initializing LLM client'

        client = get_llm_client()

        # Prepare batch prompt
        # Process up to 15 items as requested
        results_to_process = request.retrieved_context[:15] 
        logger.info(f"DEBUG: LLM Service received {len(request.retrieved_context)} items. Processing {len(results_to_process)} items.") 
        
        chunk_size = 5
        all_test_procedures = []
        all_acceptance_criteria = []
        total_tokens = 0
        
        import time

        # Process in chunks
        for i in range(0, len(results_to_process), chunk_size):
            chunk = results_to_process[i:i + chunk_size]
            current_chunk_index = (i // chunk_size) + 1
            total_chunks = (len(results_to_process) + chunk_size - 1) // chunk_size
            
            logger.info(f"Processing chunk {current_chunk_index}/{total_chunks} ({len(chunk)} requirements)")
            llm_jobs[job_id]['current_step'] = f'Generating tests (Batch {current_chunk_index}/{total_chunks})...'
            
            prompt = generate_batch_test_procedure_prompt(
                chunk,
                request.component_profile.model_dump()
            )

            max_retries = 3
            retry_delay = 5
            chunk_content = ""
            
            for attempt in range(max_retries):
                try:
                    if settings.llm_provider == "gemini":
                        full_prompt = f"System: You are an expert automotive test engineer. Return a JSON List of objects only.\n\nUser: {prompt}"
                        
                        response = client.models.generate_content(
                            model=settings.gemini_model,
                            contents=full_prompt,
                            config={
                                'temperature': settings.openai_temperature,
                                'max_output_tokens': 8192, # Sufficient for 5 items
                            }
                        )
                        chunk_content = response.text
                        total_tokens += getattr(response, 'usage_metadata', None).total_token_count if getattr(response, 'usage_metadata', None) else 0
                    else:
                        response = client.chat.completions.create(
                            model=settings.openai_model,
                            messages=[
                                {"role": "system", "content": "You are an expert automotive test engineer. Return a JSON List of objects only."},
                                {"role": "user", "content": prompt}
                            ],
                            temperature=settings.openai_temperature,
                            max_tokens=8192
                        )
                        chunk_content = response.choices[0].message.content
                        total_tokens += response.usage.total_tokens
                    
                    break # Success
                    
                except Exception as e:
                    error_str = str(e).lower()
                    if "429" in error_str or "quota" in error_str or "resource_exhausted" in error_str:
                        wait_time = retry_delay * (2 ** attempt)
                        logger.warning(f"Rate limit hit in chunk {current_chunk_index}. Retrying in {wait_time}s...")
                        time.sleep(wait_time)
                        continue
                    logger.error(f"Error generating chunk {current_chunk_index}: {e}")
                    break # Skip this chunk on non-retriable error
            
            # Parse Chunk Response
            try:
                import re
                current_procedures = []
                json_match = re.search(r'\[[\s\S]*\]', chunk_content)
                if json_match:
                    current_procedures = json.loads(json_match.group())
                else:
                    if chunk_content.strip().startswith('{'):
                         current_procedures = [json.loads(chunk_content)]
                
                # Post-process this chunk's procedures
                for k, proc in enumerate(current_procedures):
                    # Map back to source using order or ID
                    # Since we sent a specific chunk, we try to match indices if possible, 
                    # but rely on 'source_requirement' key from LLM mostly.
                    
                    # Ensure traceability exists
                    if 'traceability' not in proc:
                         proc['traceability'] = {}
                    
                    # Try to find matching source req in this chunk to get metadata
                    source_req = None
                    if 'source_requirement' in proc:
                        # Find by ID
                        source_req = next((r for r in chunk if r.get('requirement_id') == proc['source_requirement'] or r.get('node_id') == proc['source_requirement']), None)
                    
                    if not source_req and k < len(chunk):
                         # Fallback by index
                         source_req = chunk[k]
                         proc['source_requirement'] = source_req.get('requirement_id', source_req.get('node_id', ''))

                    if source_req:
                        proc['figures'] = source_req.get('figures', [])
                        proc['confidence_score'] = source_req.get('relevance_score', 0.0)
                        source_meta = source_req.get('metadata', {})
                        std = source_meta.get('source_standard', '')
                        clause = source_meta.get('source_clause', '')
                        
                        if not proc['traceability'].get('source_standard'):
                            proc['traceability']['source_standard'] = std
                        if not proc['traceability'].get('source_clause'):
                            proc['traceability']['source_clause'] = clause
                            
                        if not proc['traceability'].get('requirement_id'):
                             proc['traceability']['requirement_id'] = proc.get('source_requirement')
                        if not proc['traceability'].get('confidence_reasoning'):
                             proc['traceability']['confidence_reasoning'] = "Relevant requirement mapped from Knowledge Graph."

                    # Create AC
                    if 'acceptance_criteria' in proc:
                        all_acceptance_criteria.append({
                            'criteria_id': f"AC_{len(all_test_procedures)+1}",
                            'test_id': f"B{len(all_test_procedures)+1}",
                            'criteria_text': proc['acceptance_criteria'],
                            'source_requirement': proc.get('source_requirement', '')
                        })
                    
                    all_test_procedures.append(proc)
                    
            except json.JSONDecodeError:
                logger.error(f"Failed to parse JSON for chunk {current_chunk_index}")

            # Small delay between chunks to be nice to API
            time.sleep(1)

        # Update job status with aggregated results
        result_payload = {
            'test_procedures': all_test_procedures,
            'acceptance_criteria': all_acceptance_criteria,
            'tokens_used': total_tokens,
            'procedures_generated': len(all_test_procedures),
            'component_profile': request.component_profile.model_dump()
        }
        
        llm_jobs[job_id]['result'] = result_payload
        llm_jobs[job_id]['status'] = JobStatus.COMPLETED
        llm_jobs[job_id]['current_step'] = 'Completed'
        llm_jobs[job_id]['progress_percent'] = 100.0

        if result_payload:
             # Save to file for persistence
            import os
            from pathlib import Path
            output_dir = Path("output")
            output_dir.mkdir(parents=True, exist_ok=True)
            
            # Use centralized PTPGenerator
            from src.api.v1.dvp import PTPGenerator
            generator = PTPGenerator()
            
            # Save DOCX using existing project standard
            try:
                output_path = generator.generate_ptp_docx(
                    component_profile=request.component_profile.model_dump(),
                    test_cases=all_test_procedures,
                    include_traceability=request.include_traceability
                )
                
                # Add download URL to result
                filename = Path(output_path).name
                download_url = f"/static/output/{filename}"
                llm_jobs[job_id]['result']['download_url'] = download_url
                llm_jobs[job_id]['result']['file_name'] = filename
                
                logger.info(f"LLM generation job {job_id} completed. Saved to {output_path}")
            except Exception as docx_err:
                logger.warning(f"Could not save DOCX: {docx_err}")

    except Exception as e:
        logger.exception(f"LLM generation job {job_id} failed: {e}")
        llm_jobs[job_id]['status'] = JobStatus.FAILED
        llm_jobs[job_id]['error'] = str(e)





# ==================== ENDPOINTS ====================

@router.post("/generate", response_model=LLMGenerationResponse)
async def generate_test_procedures(
    request: LLMGenerationRequest,
    background_tasks: BackgroundTasks
):
    """
    **Endpoint 4: Generate Test Procedures with LLM**

    Uses OpenAI GPT to synthesize detailed test procedures from requirements.

    **Process:**
    1. Take retrieved requirements/clauses
    2. Generate detailed test procedure for each
    3. Extract test parameters (temperature, duration, etc.)
    4. Generate acceptance criteria
    5. Map to component specifications
    6. Maintain traceability chain

    **LLM Configuration:**
    - Model: GPT-4-turbo (configurable)
    - Temperature: 0.2 (for consistency)
    - Output: Structured JSON

    **Cost Estimation:**
    - ~1000 tokens per test procedure
    - 10 procedures = ~$0.20 (GPT-4-turbo pricing)

    **Example:**
    ```json
    {
        "retrieved_context": [...],
        "component_profile": {...},
        "generation_mode": "detailed",
        "include_traceability": true
    }
    ```

    **Returns:**
    - Test procedures with detailed steps
    - Acceptance criteria
    - Token usage and cost
    """
    # Check configuration
    if settings.llm_provider == "openai" and not settings.openai_api_base:
        raise HTTPException(
            status_code=500,
            detail="LLM API base URL not configured for OpenAI provider."
        )
    elif settings.llm_provider == "gemini" and not settings.gemini_api_key:
        raise HTTPException(
            status_code=500,
            detail="Google API key not configured for Gemini provider."
        )

    job_id = str(uuid.uuid4())

    # Create job entry
    llm_jobs[job_id] = {
        'job_id': job_id,
        'status': JobStatus.PENDING,
        'current_step': 'Initializing',
        'progress_percent': 0.0,
        'created_at': datetime.utcnow()
    }

    # Start background processing based on method
    if getattr(request, 'generation_method', 'llm') == 'deterministic':
        background_tasks.add_task(
            process_deterministic_generation,
            job_id,
            request
        )
    else:
        background_tasks.add_task(
            process_llm_generation,
            job_id,
            request
        )

    return LLMGenerationResponse(
        job_id=job_id,
        status=JobStatus.PENDING,
        test_procedures=[],
        acceptance_criteria=[],
        tokens_used=0,
        generation_time_seconds=0.0,
        timestamp=datetime.utcnow()
    )

@router.get("/status/{job_id}", response_model=JobStatusResponse)
async def get_llm_generation_status(job_id: str):
    """
    **Check LLM generation job status**

    **Parameters:**
    - job_id: Job ID from /generate endpoint

    **Returns:**
    - Current status and progress
    - Result when completed (test procedures, tokens used)
    """
    if job_id not in llm_jobs:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    job = llm_jobs[job_id]

    return JobStatusResponse(
        job_id=job_id,
        status=job['status'],
        progress_percent=job.get('progress_percent', 0.0),
        current_step=job.get('current_step', 'Unknown'),
        message=f"LLM generation: {job.get('current_step', 'Processing')}",
        result=job.get('result') if job['status'] == JobStatus.COMPLETED else None,
        error=job.get('error')
    )

async def process_deterministic_generation(job_id: str, request: LLMGenerationRequest):
    """
    Generates test plan deterministically (without LLM) using KG results directly.
    """
    try:
        llm_jobs[job_id]['status'] = JobStatus.PROCESSING
        llm_jobs[job_id]['current_step'] = 'Retrieving requirements'
        llm_jobs[job_id]['progress_percent'] = 10.0

        # 1. Use existing context if provided, else retrieve
        results = []
        if request.retrieved_context:
            logger.info(f"Using {len(request.retrieved_context)} items from provided context.")
            results = request.retrieved_context
        else:
            from src.api.v1.retrieval import query_knowledge_graph
            
            if request.component_profile.test_categories:
                cats = ", ".join(request.component_profile.test_categories)
                query_str = f"Test requirements for {request.component_profile.name} {request.component_profile.type}. Categories: {cats}."
            else:
                query_str = f"Test requirements for {request.component_profile.name} {request.component_profile.type}."

            query_request = RetrievalQueryRequest(
                query_text=query_str,
                n_results=100, 
                min_confidence=0.4, 
                include_metadata=True,
                component_profile=request.component_profile.model_dump()
            )

            response = await query_knowledge_graph(query_request)
            results = response.results
            
        if not results:
            logger.warning("No relevant nodes found in Knowledge Graph or provided context.")
            llm_jobs[job_id]['status'] = JobStatus.FAILED
            llm_jobs[job_id]['error'] = "No relevant requirements found"
            return

        # 2. Limit results
        results_to_process = results[:15]  # Process top 15 verified results
        
        test_procedures = []
        acceptance_criteria = []

        llm_jobs[job_id]['current_step'] = 'Formatting test procedures'
        
        for idx, result in enumerate(results_to_process):
            # Deterministic Mapping
            # Use Node text as requirement/description
            req_text = result.get('text', '')
            req_id = result.get('metadata', {}).get('source_clause', result.get('node_id', f'REQ_{idx}'))
            
            # Create a structured procedure object directly
            
            # Robust extraction of standard/clause
            source_meta = result.get('metadata', {})
            std = source_meta.get('source_standard', '')
            clause = source_meta.get('source_clause', '')
            
            # Fallback: Parse ID "Standard::Clause::ReqID"
            if not std and "::" in req_id:
                parts = req_id.split("::")
                if len(parts) >= 2:
                    std = parts[0]
                    clause = parts[1]

            procedure_data = {
                "test_name": f"Test for {req_id}",
                "test_description": req_text[:200] + "..." if len(req_text) > 200 else req_text,
                "detailed_procedure": [
                    f"1. Setup the {request.component_profile.name} in the test chamber.",
                    f"2. Configure test parameters according to {req_id}.",
                    f"3. Verify: {req_text}",
                    "4. Record observations and measurements.",
                    "5. Fail if deviations are observed."
                ],
                "acceptance_criteria": f"Must comply with {req_id}: {req_text[:100]}...",
                "source_requirement": req_id,
                "confidence_score": result.get('relevance_score', 0.0),
                "traceability": {
                    "requirement_id": req_id,
                    "source_clause": clause,
                    "source_standard": std
                },
                "figures": result.get('figures', [])
            }
            
            test_procedures.append(procedure_data)
            
            # AC
            acceptance_criteria.append({
                'criteria_id': f"AC_{idx+1}",
                'test_id': f"B{idx+1}",
                'criteria_text': procedure_data['acceptance_criteria'],
                'source_requirement': req_id
            })

        # Save Result
        result_payload = {
            'test_procedures': test_procedures,
            'acceptance_criteria': acceptance_criteria,
            'tokens_used': 0,
            'procedures_generated': len(test_procedures),
            'component_profile': request.component_profile.model_dump()
        }
        
        llm_jobs[job_id]['status'] = JobStatus.COMPLETED
        llm_jobs[job_id]['current_step'] = 'Completed'
        llm_jobs[job_id]['progress_percent'] = 100.0
        llm_jobs[job_id]['result'] = result_payload

        if result_payload:
             # Save to file for persistence
            import os
            from pathlib import Path
            output_dir = Path("output")
            output_dir.mkdir(parents=True, exist_ok=True)
            
            # Use centralized PTPGenerator
            from src.api.v1.dvp import PTPGenerator
            generator = PTPGenerator()
            
            # Save DOCX using existing project standard
            try:
                output_path = generator.generate_ptp_docx(
                    component_profile=request.component_profile.model_dump(),
                    test_cases=test_procedures,
                    include_traceability=request.include_traceability
                )
                
                # Add download URL to result
                filename = Path(output_path).name
                download_url = f"/static/output/{filename}"
                llm_jobs[job_id]['result']['download_url'] = download_url
                llm_jobs[job_id]['result']['file_name'] = filename

                logger.info(f"Deterministic generation job {job_id} completed. Saved to {output_path}")
            except Exception as docx_err:
                logger.warning(f"Could not save DOCX: {docx_err}")
                logger.info(f"Deterministic generation job {job_id} completed (DOCX save failed).")

    except Exception as e:
        logger.exception(f"Deterministic generation job {job_id} failed: {e}")
        llm_jobs[job_id]['status'] = JobStatus.FAILED
        llm_jobs[job_id]['error'] = str(e)

@router.post("/generate-deterministic", response_model=LLMGenerationResponse)
async def generate_test_procedures_deterministic(
    request: LLMGenerationRequest,
    background_tasks: BackgroundTasks
):
    """
    **Endpoint: Deterministic Generation (No LLM)**
    Generates test procedures directly from Knowledge Graph retrieval results.
    Fast, no rate limits, but less detailed than LLM generation.
    """
    job_id = str(uuid.uuid4())

    llm_jobs[job_id] = {
        'job_id': job_id,
        'status': JobStatus.PENDING,
        'current_step': 'Initializing',
        'progress_percent': 0.0,
        'created_at': datetime.utcnow()
    }

    background_tasks.add_task(
        process_deterministic_generation,
        job_id,
        request
    )

    return LLMGenerationResponse(
        job_id=job_id,
        status=JobStatus.PENDING,
        test_procedures=[],
        acceptance_criteria=[],
        tokens_used=0,
        generation_time_seconds=0.0,
        timestamp=datetime.utcnow()
    )

@router.post("/generate-simple")
async def generate_simple_test_procedure(
    requirement_text: str,
    component_type: str,
    test_category: str
):
    """
    **Simple test procedure generation (synchronous)**

    Quick endpoint for generating a single test procedure.
    Useful for testing or interactive use.

    **Parameters:**
    - requirement_text: The requirement text
    - component_type: Type of component
    - test_category: Test category (thermal, mechanical, etc.)

    **Returns:**
    - Generated test procedure (immediate response)
    """
    # Check configuration
    if settings.llm_provider == "openai" and not settings.openai_api_base:
        raise HTTPException(
            status_code=500,
            detail="LLM API base URL not configured"
        )
    elif settings.llm_provider == "gemini" and not settings.gemini_api_key:
        raise HTTPException(
            status_code=500,
            detail="Google API key not configured"
        )

    try:
        client = get_llm_client()

        prompt = f"""Generate a test procedure for:

Component: {component_type}
Test Category: {test_category}
Requirement: {requirement_text}

Provide a JSON response with:
- test_name
- test_description
- detailed_procedure
- acceptance_criteria"""

        if settings.llm_provider == "gemini":
            full_prompt = f"System: You are an automotive test engineer. Always respond with valid JSON only.\n\nUser: {prompt}"
            response = client.models.generate_content(
                model=settings.gemini_model,
                contents=full_prompt,
                config={
                    'temperature': 0.2,
                    'max_output_tokens': 1000,
                }
            )
            content = response.text
            tokens = getattr(response, 'usage_metadata', None).total_token_count if getattr(response, 'usage_metadata', None) else 0
        else:
            response = client.chat.completions.create(
                model=settings.openai_model,
                messages=[
                    {"role": "system", "content": "You are an automotive test engineer. Always respond with valid JSON only."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2,
                max_tokens=1000
            )
            content = response.choices[0].message.content
            tokens = response.usage.total_tokens
        # Try to extract JSON from the response
        try:
            result = json.loads(content)
        except json.JSONDecodeError:
            import re
            json_match = re.search(r'\{[\s\S]*\}', content)
            if json_match:
                result = json.loads(json_match.group())
            else:
                raise ValueError(f"Could not parse JSON from response: {content[:200]}")

        return {
            "test_procedure": result,
            "tokens_used": tokens,
            "model": settings.gemini_model if settings.llm_provider == "gemini" else settings.openai_model
        }

    except Exception as e:
        logger.exception(f"Simple generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
