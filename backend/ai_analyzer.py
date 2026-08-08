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

        structured_data = CostAnalysisResponse.model_validate_json(response.text)
        return structured_data.model_dump()
    except Exception as e:
        logger.warning(f"Gemini API analysis notice: {e}")
        return _heuristic_rule_analysis(resources)

def _heuristic_rule_analysis(resources: List[dict]) -> dict:
    """Fallback rule-based cost analyzer when Gemini API quota is reached."""
    logger.info("Executing rule-based cost analysis engine fallback...")
    recs = []
    total_savings = 0.0

    for r in resources:
        r_id = r.get("id", "unknown")
        r_type = r.get("type", "")
        r_state = r.get("state", "")
        config = r.get("configuration", {})
        tags = r.get("tags", {})
        tag_str = str(tags).lower()

        # 1. EC2 idle compute check
        if r_type == "EC2 Instance" and r_state == "running":
            if not any(k in tag_str for k in ["prod", "production", "critical"]):
                recs.append({
                    "resource_id": r_id,
                    "issue_type": "Idle EC2 Instance",
                    "severity": "high",
                    "estimated_savings": 14.60,
                    "remediation_command": f"aws ec2 stop-instances --instance-ids {r_id}"
                })
                total_savings += 14.60
        elif r_type == "EC2 Instance" and r_state == "stopped":
            recs.append({
                "resource_id": r_id,
                "issue_type": "Stopped EC2 Instance",
                "severity": "medium",
                "estimated_savings": 5.00,
                "remediation_command": f"aws ec2 terminate-instances --instance-ids {r_id}"
            })
            total_savings += 5.00

        # 2. EBS Volume checks (gp2 migration or unattached)
        if r_type == "EBS Volume":
            vol_type = config.get("volume_type", "")
            size_gib = config.get("size_gib", 20)
            if r_state == "available":
                recs.append({
                    "resource_id": r_id,
                    "issue_type": "Unattached EBS Volume",
                    "severity": "high",
                    "estimated_savings": round(size_gib * 0.10, 2),
                    "remediation_command": f"aws ec2 delete-volume --volume-id {r_id}"
                })
                total_savings += round(size_gib * 0.10, 2)
            elif vol_type == "gp2":
                recs.append({
                    "resource_id": r_id,
                    "issue_type": "gp2 to gp3 Migration",
                    "severity": "medium",
                    "estimated_savings": round(size_gib * 0.02, 2),
                    "remediation_command": f"aws ec2 modify-volume --volume-id {r_id} --volume-type gp3"
                })
                total_savings += round(size_gib * 0.02, 2)

        # 3. S3 Bucket checks
        if r_type == "S3 Bucket":
            recs.append({
                "resource_id": r_id,
                "issue_type": "Missing S3 lifecycle policies",
                "severity": "medium",
                "estimated_savings": 3.50,
                "remediation_command": f"aws s3api put-bucket-lifecycle-configuration --bucket {r_id} --lifecycle-configuration file://lifecycle.json"
            })
            total_savings += 3.50

    exec_summary = (
        f"Rule-based FinOps engine analyzed {len(resources)} active resources. "
        f"Identified {len(recs)} potential cost-optimization opportunities with total estimated savings of ${total_savings:.2f}/month."
    )
    return {
        "executive_summary": exec_summary,
        "recommendations": recs
    }


def analyze_costs(resources: List[dict]) -> dict:
    """
    Ingests scanned AWS resources and generates structured cost optimization recommendations
    using Gemini 2.5 Flash, falling back to rule-based analysis if API quota is reached.
    """
    if not resources:
        return {
            "executive_summary": "No active AWS resources were found in the scanned region. There are no pending cost optimization recommendations.",
            "recommendations": []
        }

    try:
        client = get_genai_client()

        prompt = f"""
        You are an expert Cloud Cost Optimization Architect performing a cost audit. Analyze the following inventory of AWS resources and produce actionable cost optimization recommendations.

        IMPORTANT RULES:
        - You MUST be aggressive in finding savings. If in doubt, flag the resource.
        - Every running EC2 instance with no "production", "prod", or "critical" tag should be flagged as a potential idle compute candidate.
        - Every stopped EC2 instance should be flagged for termination review.
        - Every gp2 volume should be flagged for gp3 migration.

        AWS Resources Payload:
        {json.dumps(resources, indent=2)}
        """

        logger.info("Sending resources payload to Gemini API for analysis")
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=CostAnalysisResponse,
                temperature=0.2,
            ),
        )

        if response.text:
            structured_data = CostAnalysisResponse.model_validate_json(response.text)
            return structured_data.model_dump()
    except Exception as e:
        logger.warning(f"Gemini API analysis notice ({e}). Falling back to rule-based cost engine.")

    return _heuristic_rule_analysis(resources)


def generate_chat_response(
    message: str,
    chat_history: List[dict],
    resources: List[dict],
    recommendations: List[dict],
    audit_history: List[dict] = None
) -> str:
    """
    Generates a conversational response using gemini-2.5-flash model, with fallback to FinOps guidance if quota reached.
    """
    try:
        client = get_genai_client()

        system_instruction = (
            "You are a Cloud FinOps AI Assistant. You have access to the user's scanned cloud resource inventory, cost recommendations, "
            "and audit history across all regions. Answer questions accurately, suggesting CLI commands, Terraform configurations, "
            "or explaining cloud billing concepts based on their actual inventory."
        )

        inventory_context = f"Scanned Resources: {json.dumps(resources, indent=2)}\nRecommendations: {json.dumps(recommendations, indent=2)}\n"
        full_system_instruction = f"{system_instruction}\n\n{inventory_context}"

        contents = []
        for msg in chat_history:
            role = msg.get("role")
            text = msg.get("text")
            if role in ("user", "model") and text:
                contents.append(types.Content(role=role, parts=[types.Part.from_text(text=text)]))

        contents.append(types.Content(role="user", parts=[types.Part.from_text(text=message)]))

        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=full_system_instruction,
                temperature=0.7,
            )
        )
        if response.text:
            return response.text
    except Exception as e:
        logger.warning(f"Gemini API chat notice ({e}), returning rule-based FinOps guidance...")

    return (
        "**FinOps AI Assistant:** Based on standard cloud optimization practices:\n\n"
        "1. **High-Severity Issues:** Usually represent unattached storage volumes or idle non-production instances incurring active hourly charges.\n"
        "2. **gp2 to gp3 Upgrades:** Move EBS volumes from `gp2` to `gp3` to save 20% on monthly storage costs.\n"
        "   * *Remediation CLI:* `aws ec2 modify-volume --volume-id <vol-id> --volume-type gp3`\n"
        "3. **Idle Resources:** Stop or terminate idle non-production instances when not in active development."
    )
