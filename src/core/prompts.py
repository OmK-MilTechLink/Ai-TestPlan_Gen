"""
Centralized Prompt Templates for LLM Generation
"""
from typing import List, Dict, Any
import json

def get_test_procedure_prompt(requirement: Dict[str, Any],
                                component_profile: Dict[str, Any]) -> str:
    """
    Generate prompt for test procedure creation
    """
    return f"""You are a Senior Automotive Test Engineering Expert. Your task is to create a professional, industry-standard Design Verification Plan (DVP) test procedure based STRICTLY on the provided requirement.

CRITICAL RULES - NO HALLUCINATION:
1. You must ONLY use the information provided in the "Requirement Information" and "Component Specifications" sections.
2. Do NOT invent, assume, or hallucinate test parameters (like exact temperatures, voltages, times) if they are not explicitly mentioned in the provided text. If a parameter is missing, use "As specified in component manifest" or "Ambient".
3. The procedure must be a highly detailed, step-by-step technical instruction suitable for a laboratory technician.

--- INPUT DATA ---
Component Under Test:
- Name: {component_profile.get('name', 'Component')}
- Type: {component_profile.get('type', 'Unknown')}
- Application: {component_profile.get('application', 'Unknown')}
- Test Level: {component_profile.get('test_level', 'Unknown')}
- Specifications: {json.dumps(component_profile.get('specifications', {}), indent=2)}

Requirement Information (Source of Truth):
{json.dumps(requirement, indent=2)}
------------------

Task:
1. Analyze the Requirement Information against the Component Specifications.
2. Determine relevance (High, Medium, Low) and provide a concise justification.
3. Generate the test procedure in the exact JSON format below.

Output JSON Format Required:
{{
    "test_name": "Specific technical name (e.g., Cold Temperature Operational Test)",
    "test_description": "Precise engineering description of the test objective.",
    "test_standard": "The exact source document ID or standard name from the requirement context.",
    "detailed_procedure": "Step 1: Set chamber to X°C. Step 2: Soak for Y hours. Step 3: Power up component at Z Volts. Step 4...",
    "test_parameters": {{
        "temperature": "Extracted value or 'Ambient'",
        "duration": "Extracted value or 'Standard duration'",
        "voltage": "Extracted value or 'Nominal'"
    }},
    "operating_mode": "E.g., Powered ON, Sleep state, Unpowered",
    "acceptance_criteria": "Exact passing criteria derived directly from the requirement text. E.g., 'Device must remain functional with no parameter drift > 5%.'",
    "estimated_days": 1,
    "traceability": {{
        "requirement_id": "{requirement.get('requirement_id', '')}",
        "source_clause": "{requirement.get('clause_id', '')}",
        "source_standard": "{requirement.get('document_id', '')}",
        "confidence_reasoning": "Why this specific test validates this specific requirement for this component.",
        "relevance_score": "High"
    }}
}}"""

def get_batch_test_procedure_prompt(requirements: List[Dict[str, Any]],
                                    component_profile: Dict[str, Any]) -> str:
    """
    Generate SLM-safe prompt for BATCH test procedure creation.
    Designed to work with small local models (phi4, nanobeige, etc.)
    """
    req_texts = []
    for i, req in enumerate(requirements):
        text = req.get('text', '')[:600]  # Tighter limit for small context windows
        req_id = req.get('requirement_id', req.get('node_id', f'REQ_{i}'))
        meta = req.get('metadata', {})
        src = meta.get('source_standard', '')
        clause = meta.get('source_clause', '')
        req_texts.append(f"[{i+1}] ID={req_id} | Src={src} Clause={clause}\n{text}")

    compiled_requirements = "\n\n".join(req_texts)
    specs_str = json.dumps(component_profile.get('specifications', {}), indent=2)

    return f"""INSTRUCTION: Output ONLY a valid JSON array. No markdown. No explanation. No text before or after [].

COMPONENT:
Name: {component_profile.get('name')}
Type: {component_profile.get('type')}
Specs: {specs_str}

REQUIREMENTS:
{compiled_requirements}

CRITICAL ENGINEERING RULES:
- Base ALL test steps, parameters, and criteria STRICTLY on the requirements text.
- Do NOT make up specific test temperatures, voltages, vibrations, or timings if they are missing. Use "As specified" or "Generic functional check" if unspecified.
- Generate exactly {len(requirements)} JSON objects, one per requirement above.
- The "source_requirement" field MUST match the ID above exactly.
- Output MUST be a JSON array of exactly {len(requirements)} objects.

OUTPUT FORMAT (copy structure exactly):
[
  {{
    "test_name": "Specific technical test name",
    "test_description": "Precise engineering description of the test objective.",
    "detailed_procedure": [
      "Step 1: Highly descriptive setup instruction...",
      "Step 2: Apply parameter X...",
      "Step 3: Monitor for Y..."
    ],
    "acceptance_criteria": "Exact passing criteria derived directly from the text.",
    "source_requirement": "EXACT_ID_FROM_ABOVE",
    "traceability": {{
      "source_standard": "from metadata",
      "confidence_reasoning": "Why this specific test proves compliance",
      "relevance_score": "High"
    }}
  }}
]

BEGIN JSON OUTPUT:
"""

