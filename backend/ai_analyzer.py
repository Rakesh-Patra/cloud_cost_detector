import os
import json
import logging
from typing import Literal, List
from pydantic import BaseModel, Field
from google import genai
from google.genai import types

logger = logging.getLogger("ai_analyzer")

class GeminiAPIException(Exception):
    """Custom exception raised when the Gemini API analysis fails."""
    pass

class RecommendationItem(BaseModel):
    resource_id: str = Field(..., description="The ID of the affected resource (e.g., instance ID, bucket name, or volume ID)")
    issue_type: str = Field(..., description="The type of cost optimization issue (e.g., 'Unattached EBS Volume', 'gp2 to gp3 Migration', 'Over-provisioned Instance')")
    severity: Literal["high", "medium", "low"] = Field(..., description="The urgency/impact of the recommendation")
    estimated_savings: float = Field(..., description="The estimated monthly savings in USD")
    remediation_command: str = Field(..., description="An accurate, copy-pasteable AWS CLI command to execute the recommendation")

class CostAnalysisResponse(BaseModel):
    executive_summary: str = Field(..., description="A high-level overview of the findings, total potential savings, and strategic cost-optimization opportunities")
    recommendations: List[RecommendationItem] = Field(..., description="A list of specific, structured resource-level recommendations")


def get_genai_client() -> genai.Client:
    """Initialize the Gemini client using the environment variable."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key or api_key == "your_gemini_api_key_here":
        raise GeminiAPIException(
            "GEMINI_API_KEY environment variable is not set or has placeholder value. "
            "Please add it to your environment or .env file."
        )
    try:
        # Default genai.Client() automatically picks up GEMINI_API_KEY,
        # but we explicitly pass it to ensure the key is verified.
        return genai.Client(api_key=api_key)
    except Exception as e:
        logger.error(f"Failed to initialize GenAI client: {str(e)}")
        raise GeminiAPIException(f"Failed to initialize Gemini API client: {str(e)}") from e


def analyze_costs(resources: List[dict]) -> dict:
    """
    Ingests scanned AWS resources and generates structured cost optimization recommendations
    using the gemini-2.5-flash model.
    """
    if not resources:
        return {
            "executive_summary": "No active AWS resources were found in the scanned region. There are no pending cost optimization recommendations.",
            "recommendations": []
        }

    client = get_genai_client()

    # Construct the instruction and contextual prompt
    prompt = f"""
    You are an expert Cloud Cost Optimization Architect performing a cost audit. Analyze the following inventory of AWS resources and produce actionable cost optimization recommendations.

    IMPORTANT RULES:
    - You MUST be aggressive in finding savings. If in doubt, flag the resource.
    - You do NOT have CloudWatch utilization metrics available. Instead, use the resource metadata (instance type, state, volume type, attachment status, tags) to infer cost waste.
    - You MUST generate at least one recommendation for every resource that matches any pattern below. Do NOT skip resources just because you lack utilization data.
    - Every running EC2 instance with no "production", "prod", or "critical" tag should be flagged as a potential idle compute candidate.
    - Every stopped EC2 instance should be flagged for termination review (it still incurs EBS storage costs).
    
    Target the following patterns (apply ALL that match):
    1. **Over-provisioned / Idle compute**: Any running EC2 or RDS instance that is not tagged as production workload. Flag it as "Idle EC2 Instance" or "Idle RDS Instance". Estimate savings as the full on-demand hourly cost * 730 hours/month for that instance type.
    2. **Orphaned/unattached storage**: Any EBS volume in "available" state (not attached to any instance). Flag it as "Unattached EBS Volume". Estimate savings based on volume type and size.
    3. **Stopped instances**: Any EC2 instance in "stopped" state. Flag it as "Stopped Instance" — it still costs money via attached EBS volumes. Recommend termination.
    4. **Missing S3 lifecycle policies**: Any S3 bucket without lifecycle configuration. Flag it for lifecycle policy setup.
    5. **Modern tier migration**: Any gp2 EBS volume. Flag it as "gp2 to gp3 Migration" — gp3 offers ~20% savings at equal or better performance. Always flag gp2 volumes.

    For each recommendation:
    - Use the EXACT resource ID from the payload.
    - Estimate monthly savings in USD (use publicly known AWS pricing for the resource type and region).
    - Provide a syntactically correct, copy-pasteable AWS CLI command to execute the remediation. Include --region flag where applicable.

    AWS Resources Payload:
    {json.dumps(resources, indent=2)}
    """

    try:
        logger.info("Sending resources payload to Gemini API for analysis")
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=CostAnalysisResponse,
                temperature=0.2, # Lower temperature for more factual and precise remediation commands
            ),
        )

        if not response.text:
            raise GeminiAPIException("Received empty response text from Gemini API.")

        # Validate the response text with the Pydantic schema
        structured_data = CostAnalysisResponse.model_validate_json(response.text)
        return structured_data.model_dump()

    except Exception as e:
        logger.error(f"Error calling or parsing Gemini API: {str(e)}")
        if isinstance(e, GeminiAPIException):
            raise e
        # Wrap any other exceptions (SDK errors, json validation errors, etc.)
        raise GeminiAPIException(f"Gemini API analysis failed: {str(e)}") from e


def generate_chat_response(
    message: str,
    chat_history: List[dict],
    resources: List[dict],
    recommendations: List[dict],
    audit_history: List[dict] = None
) -> str:
    """
    Generates a conversational response using the gemini-2.5-flash model,
    incorporating chat history, resource/recommendation context, and past audit records.
    """
    client = get_genai_client()

    system_instruction = (
        "You are a Cloud FinOps AI Assistant. You have access to the user's scanned cloud resource inventory, cost recommendations, "
        "and audit history across all regions. Answer questions accurately, suggesting CLI commands, Terraform configurations, "
        "or explaining cloud billing concepts (like gp2 vs gp3 performance, unattached volumes, idle DB instances) based on their actual inventory."
    )

    # Compile the inventory context (active region scan results)
    inventory_context = ""
    if resources:
        inventory_context += f"Scanned Cloud Resource Inventory (Active Region Audit):\n{json.dumps(resources, indent=2)}\n\n"
    else:
        inventory_context += "Scanned Cloud Resource Inventory (Active Region Audit): None (User has not run a scan or no resources were found)\n\n"

    if recommendations:
        inventory_context += f"Cost Optimization Recommendations (Active Region Audit):\n{json.dumps(recommendations, indent=2)}\n\n"
    else:
        inventory_context += "Cost Optimization Recommendations (Active Region Audit): None\n\n"

    # Compile the audit history context (multi-region summary)
    history_context = ""
    if audit_history:
        cleaned_history = []
        for audit in audit_history:
            # We filter out large payload results to keep context concise
            cleaned_history.append({
                "region": audit.get("region"),
                "status": audit.get("status"),
                "resources_scanned": audit.get("resources_scanned"),
                "issues_found": audit.get("issues_found"),
                "estimated_savings": audit.get("estimated_savings"),
                "created_at": audit.get("created_at")
            })
        history_context += f"Audit History and Status Across All Audited Regions:\n{json.dumps(cleaned_history, indent=2)}\n\n"
    else:
        history_context += "Audit History Across All Regions: None (No historical region audits exist in database)\n\n"

    full_system_instruction = f"{system_instruction}\n\n{inventory_context}{history_context}"

    # Build the contents list for multi-turn chat
    contents = []
    for msg in chat_history:
        role = msg.get("role")
        text = msg.get("text")
        if role in ("user", "model") and text:
            contents.append(
                types.Content(
                    role=role,
                    parts=[types.Part.from_text(text=text)]
                )
            )

    # Append current message
    contents.append(
        types.Content(
            role="user",
            parts=[types.Part.from_text(text=message)]
        )
    )

    try:
        logger.info(f"Sending message to Gemini API (history length: {len(chat_history)})")
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=full_system_instruction,
                temperature=0.7,
            )
        )
        return response.text or ""
    except Exception as e:
        logger.error(f"Error in generate_chat_response: {str(e)}")
        raise GeminiAPIException(f"Failed to generate chat response: {str(e)}") from e
