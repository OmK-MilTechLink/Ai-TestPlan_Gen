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
    return f"""You are a test engineer creating a Product Testing Plan (PTP) for automotive components.

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
    "traceability": {{
        "requirement_id": "{requirement.get('requirement_id', '')}",
        "source_clause": "{requirement.get('clause_id', '')}",
        "source_standard": "{requirement.get('document_id', '')}",
        "confidence_reasoning": "A one-line explanation of why this requirement is relevant to the component",
        "relevance_score": "High, Medium, or Low"
    }}
}}

Generate a realistic and detailed test procedure that follows automotive industry standards."""

def get_batch_test_procedure_prompt(requirements: List[Dict[str, Any]],
                                    component_profile: Dict[str, Any]) -> str:
    """
    Generate prompt for BATCH test procedure creation
    """
    req_texts = []
    for i, req in enumerate(requirements):
        text = req.get('text', '')[:500]  # Truncate massive requirements
        req_id = req.get('requirement_id', req.get('node_id', f'REQ_{i}'))
        req_texts.append(f"Requirement {i+1} (ID: {req_id}): {text}")
        
    compiled_requirements = "\n\n".join(req_texts)

    return f"""You are a test engineer creating a Product Testing Plan (PTP).

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
