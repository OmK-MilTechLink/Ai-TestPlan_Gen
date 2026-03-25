"""
Endpoint 4: LLM Generation Service
Synthesizes test procedures and acceptance criteria using LLM
"""
from fastapi import APIRouter, HTTPException, BackgroundTasks
from typing import List, Dict, Any, Optional
import json
from pathlib import Path
from loguru import logger
from google import genai
import time
import re
from datetime import datetime

from src.models.api_models import (
    LLMGenerationRequest,
    LLMGenerationResponse,
    JobStatus,
    JobStatusResponse,
    RetrievalQueryRequest
)
from src.config import settings
from src.utils.job_manager import JobManager, JobStatus as JMStatus
from src.core import prompts

router = APIRouter()

# Unified job manager for LLM tasks
job_manager = JobManager()

# LLM Client (will initialize when needed)
_llm_client = None

def get_llm_client():
    """Get or create LLM client - supports local models (OpenAI) and Google Gemini"""
    global _llm_client
    
    if settings.llm_provider == "gemini":
        if not settings.gemini_api_key:
            logger.error("Gemini API key not configured")
            return None
        return genai.Client(api_key=settings.gemini_api_key)
        
    if _llm_client is None:
        from openai import OpenAI
        _llm_client = OpenAI(
            api_key=settings.openai_api_key or "not-needed",
            base_url=settings.openai_api_base
        )
        logger.info(f"LLM client initialized for {settings.openai_model}")
    return _llm_client

async def _fetch_context_fallback(request: LLMGenerationRequest) -> List[Dict[str, Any]]:
    """Fallback if no context is provided: query the knowledge graph."""
    from src.api.v1.retrieval import query_knowledge_graph
    query_str = f"Test requirements for {request.component_profile.name} {request.component_profile.type}."
    logger.info(f"Context fallback: Querying KG with '{query_str}'")
    try:
        response = await query_knowledge_graph(RetrievalQueryRequest(
            component_profile=request.component_profile,
            retrieval_method="hybrid",
            max_results=15,
            min_confidence=0.4,
            include_hierarchy=True,
            include_references=True
        ))
        return response.results
    except Exception as e:
        logger.error(f"Fallback context retrieval failed: {e}")
        return []

async def process_llm_generation(job_id: str, request: LLMGenerationRequest) -> Dict[str, Any]:
    """
    Core logic for LLM generation. Returns the result payload directly.
    """
    try:
        job_manager.update_job(job_id, status=JMStatus.PROCESSING, current_step='Initializing LLM client')

        client = get_llm_client()
        if not client:
            error_msg = "LLM client initialization failed"
            job_manager.update_job(job_id, status=JMStatus.FAILED, error=error_msg)
            raise Exception(error_msg)

        # Handle Context Fallback
        results_to_process = request.retrieved_context
        if not results_to_process:
            job_manager.update_job(job_id, current_step='Fetching relevant context from KG')
            results_to_process = await _fetch_context_fallback(request)
            
        if not results_to_process:
            error_msg = "No relevant requirements found for context fallback"
            job_manager.update_job(job_id, status=JMStatus.FAILED, error=error_msg)
            raise Exception(error_msg)

        # Process up to 15 items
        results_to_process = results_to_process[:15]

        # --- Save retrieved context to temp for debugging/audit ---
        try:
            import json as _json
            from datetime import datetime as _dt
            _temp_dir = Path(settings.temp_dir)
            _temp_dir.mkdir(parents=True, exist_ok=True)
            _ts = _dt.now().strftime("%Y%m%d_%H%M%S")
            _ctx_file = _temp_dir / f"kg_context_{job_id}_{_ts}.txt"
            with open(_ctx_file, "w", encoding="utf-8") as _f:
                _f.write(f"Job ID      : {job_id}\n")
                _f.write(f"Timestamp   : {_ts}\n")
                _f.write(f"Total Nodes : {len(results_to_process)}\n")
                _f.write("=" * 80 + "\n\n")
                for _i, _node in enumerate(results_to_process, 1):
                    _f.write(f"--- Node {_i} ---\n")
                    _f.write(_json.dumps(_node, indent=2, ensure_ascii=False, default=str))
                    _f.write("\n\n")
            logger.info(f"Saved {len(results_to_process)} KG context nodes → {_ctx_file}")
        except Exception as _e:
            logger.warning(f"Could not save KG context to temp: {_e}")
        # ----------------------------------------------------------

        chunk_size = 5
        all_test_procedures = []
        all_acceptance_criteria = []
        total_tokens = 0
        
        # Process in chunks
        for i in range(0, len(results_to_process), chunk_size):
            chunk = results_to_process[i:i + chunk_size]
            current_chunk = (i // chunk_size) + 1
            total_chunks = (len(results_to_process) + chunk_size - 1) // chunk_size
            
            job_manager.update_job(
                job_id, 
                current_step=f'Generating tests (Batch {current_chunk}/{total_chunks})...',
                progress=(current_chunk / total_chunks) * 90
            )
            
            prompt = prompts.get_batch_test_procedure_prompt(
                chunk,
                request.component_profile.model_dump()
            )

            chunk_content = ""
            for attempt in range(3):  # Max retries
                try:
                    SLM_SYSTEM_MSG = (
                        "You are a JSON generator. "
                        "Output ONLY a valid JSON array []. "
                        "NO explanations. NO markdown. NO comments. NO extra text before or after the JSON. "
                        "Use ONLY the data provided. Do NOT add any values not present in the input."
                    )
                    if settings.llm_provider == "gemini":
                        response = client.models.generate_content(
                            model=settings.gemini_model,
                            contents=f"System: {SLM_SYSTEM_MSG}\n\nUser: {prompt}",
                            config={'temperature': 0.1, 'max_output_tokens': 4096}
                        )
                        chunk_content = response.text
                        total_tokens += getattr(response, 'usage_metadata', None).total_token_count if getattr(response, 'usage_metadata', None) else 0
                    else:
                        response = client.chat.completions.create(
                            model=settings.openai_model,
                            messages=[
                                {"role": "system", "content": SLM_SYSTEM_MSG},
                                {"role": "user", "content": prompt}
                            ],
                            temperature=0.1,
                            max_tokens=4096
                        )
                        chunk_content = response.choices[0].message.content if response.choices else ""
                        total_tokens += response.usage.total_tokens if response.usage else 0
                    break
                except Exception as e:
                    if "429" in str(e) or "quota" in str(e):
                        time.sleep(5 * (2 ** attempt))
                        continue
                    logger.error(f"LLM Error: {e}")
                    break
            
            # Parse Chunk Response
            try:
                current_procedures = []
                # Find ALL JSON arrays in the output (some SLMs output two blobs)
                for json_match in re.finditer(r'\[[\s\S]*?\]', chunk_content):
                    try:
                        parsed = json.loads(json_match.group())
                        if isinstance(parsed, list) and len(parsed) > 0:
                            current_procedures = parsed
                            break  # Use first non-empty array
                    except json.JSONDecodeError:
                        continue  # Try next match
                
                for k, proc in enumerate(current_procedures):
                    if not isinstance(proc, dict):
                        continue
                        
                    if 'traceability' not in proc: proc['traceability'] = {}
                    
                    source_req = None
                    if 'source_requirement' in proc:
                        source_req = next((r for r in chunk if r.get('requirement_id') == proc['source_requirement'] or r.get('node_id') == proc['source_requirement']), None)
                    
                    if not source_req and k < len(chunk):
                         source_req = chunk[k]
                         proc['source_requirement'] = source_req.get('requirement_id', source_req.get('node_id', ''))

                    if source_req:
                        proc['figures'] = source_req.get('figures', [])
                        proc['confidence_score'] = source_req.get('relevance_score', 0.0)
                        source_meta = source_req.get('metadata', {})
                        
                        if not proc['traceability'].get('source_standard'):
                            proc['traceability']['source_standard'] = source_meta.get('source_standard', '')
                        if not proc['traceability'].get('source_clause'):
                            proc['traceability']['source_clause'] = source_meta.get('source_clause', '')
                        if not proc['traceability'].get('requirement_id'):
                             proc['traceability']['requirement_id'] = proc.get('source_requirement')

                    if 'acceptance_criteria' in proc:
                        all_acceptance_criteria.append({
                            'criteria_id': f"AC_{len(all_test_procedures)+1}",
                            'test_id': f"B{len(all_test_procedures)+1}",
                            'criteria_text': proc['acceptance_criteria'],
                            'source_requirement': proc.get('source_requirement', '')
                        })
                    all_test_procedures.append(proc)
            except Exception as parse_err:
                logger.error(f"Parse error in chunk {current_chunk}: {parse_err}")

        # Finalizing
        job_manager.update_job(job_id, current_step='Saving DOCX...')
        
        result_payload = {
            'test_procedures': all_test_procedures,
            'acceptance_criteria': all_acceptance_criteria,
            'tokens_used': total_tokens,
            'procedures_generated': len(all_test_procedures),
            'component_profile': request.component_profile.model_dump()
        }
        
        # Save DOCX
        try:
            from src.api.v1.dvp import PTPGenerator
            generator = PTPGenerator()
            output_path = generator.generate_ptp_docx(
                component_profile=request.component_profile.model_dump(),
                test_cases=all_test_procedures,
                include_traceability=request.include_traceability
            )
            result_payload['download_url'] = f"/static/output/{Path(output_path).name}"
            result_payload['file_name'] = Path(output_path).name
        except Exception as docx_err:
            logger.warning(f"DOCX save failed: {docx_err}")

        job_manager.update_job(job_id, status=JMStatus.COMPLETED, result=result_payload)
        return result_payload

    except Exception as e:
        logger.exception(f"LLM Job {job_id} failed: {e}")
        job_manager.update_job(job_id, status=JMStatus.FAILED, error=str(e))
        raise e

@router.post("/generate", response_model=LLMGenerationResponse)
async def generate_test_procedures(request: LLMGenerationRequest, background_tasks: BackgroundTasks):
    """**Generate Test Procedures with LLM**"""
    job_id = job_manager.create_job()
    
    if request.sync:
        try:
            result = await process_llm_generation(job_id, request)
                
            return LLMGenerationResponse(
                job_id=job_id,
                status=JobStatus.COMPLETED,
                test_procedures=result.get('test_procedures', []),
                acceptance_criteria=result.get('acceptance_criteria', []),
                tokens_used=result.get('tokens_used', 0),
                timestamp=datetime.utcnow()
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    else:
        background_tasks.add_task(process_llm_generation, job_id, request)
        return LLMGenerationResponse(job_id=job_id, status=JobStatus.PENDING, timestamp=datetime.utcnow())

@router.get("/status/{job_id}", response_model=JobStatusResponse)
async def get_llm_generation_status(job_id: str):
    """**Check LLM generation job status**"""
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    return JobStatusResponse(
        job_id=job.job_id,
        status=job.status,
        progress_percent=job.progress_percent,
        current_step=job.current_step,
        message=f"LLM generation: {job.current_step}",
        result=job.result,
        error=job.error,
        timestamp=datetime.utcnow()
    )

@router.get("/list")
async def list_generation_jobs():
    """**List all generation jobs**"""
    return job_manager.list_jobs()
