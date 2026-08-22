import os
import json
import logging
import time
from typing import Literal, List
from pydantic import BaseModel, Field
from google import genai
from google.genai import types
from pricing_engine import PricingEngine

logger = logging.getLogger("ai_analyzer")

class GeminiAPIException(Exception):
    """Custom exception raised when the Gemini API analysis fails."""
    pass

class AICircuitBreaker:
    """
    Circuit breaker for Gemini AI API calls.
    If calls fail 3 times consecutively, it opens and degrades gracefully
    to deterministic local analysis for 60 seconds before probing again.
    """
    def __init__(self, failure_threshold: int = 3, recovery_timeout_seconds: float = 60.0):
        self.failure_threshold = failure_threshold
        self.recovery_timeout_seconds = recovery_timeout_seconds
        self.failure_count = 0
        self.last_failure_time = 0.0
        self.state = "CLOSED"  # CLOSED (normal), OPEN (broken), HALF-OPEN (testing)

    def can_attempt(self) -> bool:
        if self.state == "CLOSED":
            return True
        if self.state == "OPEN":
            if time.time() - self.last_failure_time > self.recovery_timeout_seconds:
                self.state = "HALF-OPEN"
                logger.info("AI Circuit Breaker entering HALF-OPEN state (re-testing Gemini API).")
                return True
            return False
        if self.state == "HALF-OPEN":
            return True
        return True

    def record_success(self):
        if self.state != "CLOSED":
            logger.info("AI Circuit Breaker recovered to CLOSED state.")
        self.failure_count = 0
        self.state = "CLOSED"

    def record_failure(self, error: Exception):
        self.failure_count += 1
        self.last_failure_time = time.time()
        if self.failure_count >= self.failure_threshold:
            self.state = "OPEN"
            logger.warning(
                f"AI Circuit Breaker TRIPPED to OPEN after {self.failure_count} consecutive failures: {error}. "
                f"Graceful deterministic fallback will be used for the next {self.recovery_timeout_seconds}s."
            )

circuit_breaker = AICircuitBreaker()

def estimate_tokens(text: str) -> int:
    """Approximate token count (1 token ~= 4 characters)."""
    return max(1, len(text) // 4)

def log_ai_usage(prompt_length: int, completion_text: str = "", model: str = "gemini-2.5-flash"):
    """Estimates and logs AI token consumption and cost for FinOps telemetry."""
    prompt_tokens = max(1, prompt_length // 4)
    completion_tokens = max(1, len(completion_text) // 4) if completion_text else 0
    total_tokens = prompt_tokens + completion_tokens
    # Gemini 2.5 Flash pricing: $0.075 / 1M prompt tokens, $0.30 / 1M output tokens
    estimated_cost = (prompt_tokens * 0.000000075) + (completion_tokens * 0.00000030)
    logger.info(
        f"AI Spend Guard - Model: {model} | Input Tokens: ~{prompt_tokens} | "
        f"Output Tokens: ~{completion_tokens} | Total: ~{total_tokens} | Est. Cost: ${estimated_cost:.6f} USD"
    )

def get_genai_client():
    """Initializes and returns the Google GenAI client if an API key is present."""
    api_key = os.environ.get("GEMINI_API_KEY")
    # Ignore placeholder or template keys
    if not api_key or api_key.startswith("your_") or api_key in ("your_gemini_api_key_here", "mock-gemini-key"):
        api_key = os.environ.get("GOOGLE_API_KEY")
        
    if not api_key or api_key.startswith("your_") or api_key in ("your_gemini_api_key_here", "mock-gemini-key"):
        raise ValueError("GEMINI_API_KEY is not configured with a valid Google Gemini API key.")
    return genai.Client(api_key=api_key)

class RecommendationItem(BaseModel):
    resource_id: str = Field(..., description="The ID of the affected resource (e.g., instance ID, bucket name, or volume ID)")
    issue_type: str = Field(..., description="The type of cost optimization issue (e.g., 'Unattached EBS Volume', 'gp2 to gp3 Migration', 'Idle EC2 Instance')")
    severity: Literal["high", "medium", "low"] = Field(..., description="The urgency/impact of the recommendation")
    estimated_savings: float = Field(..., description="The estimated monthly savings in USD")
    remediation_command: str = Field(..., description="An accurate, copy-pasteable AWS CLI command to execute the recommendation")
    terraform_code: str = Field(default="", description="Optional Terraform HCL snippet to apply remediation via IaC")

class CostAnalysisResponse(BaseModel):
    executive_summary: str = Field(..., description="A high-level overview of the findings, total potential savings, and strategic cost-optimization opportunities")
    recommendations: List[RecommendationItem] = Field(..., description="A list of specific, structured resource-level recommendations")


def _deterministic_pre_filter(resources: List[dict], region: str = "us-east-1") -> tuple[list, float]:
    """
    Tier 1 Deterministic Pre-filter:
    Uses PricingEngine to evaluate each resource with mathematical accuracy before LLM processing.
    """
    flagged_recs = []
    total_waste = 0.0

    for r in resources:
        eval_result = PricingEngine.evaluate_resource_waste(r, region)
        if eval_result.get("is_wasteful"):
            r_id = r.get("id", "unknown")
            rec_type = eval_result.get("recommendation_type", "")
            waste_val = eval_result.get("monthly_waste_dollars", 0.0)
            total_waste += waste_val

            # Determine severity
            severity = "high" if waste_val > 50.0 or rec_type == "UNATTACHED_EBS" else "medium" if waste_val > 10.0 else "low"

            # Generate precise CLI and Terraform code
            cli_cmd = ""
            tf_code = ""
            if rec_type == "UNATTACHED_EBS":
                cli_cmd = f"aws ec2 delete-volume --volume-id {r_id} --region {region}"
                tf_code = f'# Remove aws_ebs_volume resource "{r_id}" from Terraform state\nterraform state rm aws_ebs_volume.legacy_{r_id.replace("-", "_")}'
            elif rec_type == "MODERNIZE_GP2":
                cli_cmd = f"aws ec2 modify-volume --volume-id {r_id} --volume-type gp3 --region {region}"
                tf_code = 'resource "aws_ebs_volume" "example" {\n  # update type to gp3\n  type = "gp3"\n}'
            elif rec_type == "IDLE_EC2":
                cli_cmd = f"aws ec2 stop-instances --instance-ids {r_id} --region {region}"
                tf_code = 'resource "aws_instance" "example" {\n  # Consider setting instance_state = "stopped" or downsizing SKU\n}'
            elif rec_type == "STOPPED_EC2":
                cli_cmd = f"aws ec2 terminate-instances --instance-ids {r_id} --region {region}"
            else:
                cli_cmd = f"aws ec2 describe-tags --filters 'Name=resource-id,Values={r_id}'"

            flagged_recs.append({
                "resource_id": r_id,
                "issue_type": eval_result.get("details") or rec_type,
                "severity": severity,
                "estimated_savings": round(waste_val, 2),
                "remediation_command": cli_cmd,
                "terraform_code": tf_code
            })

    return flagged_recs, round(total_waste, 2)


def analyze_costs(resources: List[dict], region: str = "us-east-1") -> dict:
    """
    Two-Tier FinOps Analysis:
    - Tier 1: Deterministic evaluation using PricingEngine (zero LLM token waste on healthy resources).
    - Tier 2: Gemini AI synthesis for executive overview and strategic planning.
    """
    if not resources:
        return {
            "executive_summary": "No active AWS resources were found in the scanned region. Zero waste detected.",
            "recommendations": []
        }

    # Run Tier 1 Deterministic Filtering
    flagged_recs, total_waste = _deterministic_pre_filter(resources, region)

    if not flagged_recs:
        return {
            "executive_summary": f"Scanned {len(resources)} resources across {region}. Infrastructure is well-optimized with zero unattached or severely idle assets detected.",
            "recommendations": []
        }

    # Attempt Tier 2 Gemini AI Synthesis for executive summary
    if circuit_breaker.can_attempt():
        try:
            client = get_genai_client()

            prompt = f"""
            You are a Principal FinOps Architect reviewing a filtered cloud audit.
            Tier 1 deterministic rule engine has already scored the following wasteful items and calculated exact savings:

            Total Monthly Waste Identified: ${total_waste:.2f} USD
            Scanned Region: {region}
            Flagged Resources:
            {json.dumps(flagged_recs, indent=2)}

            Provide an executive summary synthesizing the root cause (e.g. unattached storage vs idle compute vs gp2 legacy) and the primary strategic priority to cut spend.
            Keep the recommendations list faithful to the provided calculated savings.
            """

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
                circuit_breaker.record_success()
                log_ai_usage(len(prompt), response.text)
                return structured_data.model_dump()
        except Exception as e:
            circuit_breaker.record_failure(e)
            logger.warning(f"Gemini AI synthesis fallback ({e}). Using deterministic summary.")
    else:
        logger.info("AI Circuit Breaker is active. Bypassing Gemini synthesis for instant deterministic response.")

    # Fallback to pure deterministic output
    exec_summary = (
        f"Automated FinOps scan audited {len(resources)} resources in {region}. "
        f"Identified {len(flagged_recs)} cost-optimization opportunities totaling ${total_waste:.2f}/month in potential savings."
    )
    return {
        "executive_summary": exec_summary,
        "recommendations": flagged_recs
    }


def _build_finops_fallback_response(message: str, resources: List[dict], recommendations: List[dict]) -> str:
    """
    Intelligent conversational fallback that parses the user's intent and provides
    accurate, contextual answers based on the actual scanned resources and recommendations.
    """
    msg_lower = message.lower().strip()
    total_savings = round(sum(r.get("estimated_savings", 0.0) for r in recommendations), 2)
    high_recs = [r for r in recommendations if r.get("severity") == "high"]
    vol_recs = [r for r in recommendations if "volume" in r.get("issue_type", "").lower() or "gp2" in r.get("issue_type", "").lower() or "ebs" in r.get("issue_type", "").lower()]
    idle_recs = [r for r in recommendations if "idle" in r.get("issue_type", "").lower() or "stopped" in r.get("issue_type", "").lower() or "ec2" in r.get("issue_type", "").lower()]

    # 1. Greetings & Introductions
    if msg_lower in ("hi", "hello", "hey", "help", "who are you", "what can you do", "start") or any(msg_lower.startswith(g) for g in ["hi ", "hello ", "hey "]):
        greeting = (
            "👋 **Hello! I am your Cloud FinOps AI Assistant.**\n\n"
            f"Here is your current AWS inventory snapshot:\n"
            f"- **Scanned Resources:** {len(resources)} assets\n"
            f"- **Active Optimization Recommendations:** {len(recommendations)}\n"
            f"- **Total Identified Monthly Savings:** **${total_savings:,.2f} USD**\n\n"
            "You can ask me questions like:\n"
            "• *\"How can I save money on my AWS account?\"*\n"
            "• *\"What is gp2 and how does it compare to gp3?\"*\n"
            "• *\"What are my highest priority cost issues?\"*\n"
            "• *\"Which EC2 instances are idle?\"*"
        )
        return greeting

    # 2. What is gp2 / gp3 questions
    if "what is gp2" in msg_lower or "explain gp2" in msg_lower or "difference between gp2 and gp3" in msg_lower or "gp2 vs gp3" in msg_lower:
        return (
            "💾 **What is AWS EBS gp2?**\n\n"
            "**gp2 (General Purpose SSD, Generation 2)** is AWS's legacy general-purpose block storage volume type.\n\n"
            "**Key Characteristics & Limitations:**\n"
            "- **Performance tied to size:** Storage performance is strictly locked to volume size (3 IOPS per GB, up to 3,000 IOPS burst).\n"
            "- **Higher cost:** Costs **$0.10 per GB-month** in `us-east-1`.\n"
            "- **gp3 is better and cheaper:** Upgrading to **gp3** costs **$0.08 per GB-month (20% cheaper)** and provides **3,000 IOPS + 125 MB/s throughput baseline independently** of disk size.\n\n"
            "**How to upgrade (Zero downtime):**\n"
            "```bash\n"
            "aws ec2 modify-volume --volume-id <vol-id> --volume-type gp3\n"
            "```"
        )

    # 3. Terraform / IaC questions
    if "terraform" in msg_lower or "iac" in msg_lower or "cloudformation" in msg_lower:
        return (
            "🏗️ **Infrastructure as Code (Terraform) Remediation:**\n\n"
            "To modernize your EBS volume type to `gp3` in Terraform:\n"
            "```hcl\n"
            "resource \"aws_ebs_volume\" \"example\" {\n"
            "  availability_zone = \"us-east-1a\"\n"
            "  size              = 100\n"
            "  type              = \"gp3\"  # Upgrade from gp2 to save 20%\n"
            "  iops              = 3000   # Baseline included free\n"
            "  throughput        = 125    # Baseline 125 MB/s included free\n"
            "}\n"
            "```\n\n"
            "For stopped or idle EC2 instances, you can manage power scheduling with AWS Instance Scheduler or adjust `instance_type` SKU in Terraform."
        )

    # 4. High severity / Critical issues
    if any(k in msg_lower for k in ["high", "priority", "critical", "urgent", "severity"]):
        if not high_recs:
            return "✅ **Good news!** There are currently no high-severity cost anomalies detected in your scanned environment."
        items_md = "\n".join([
            f"- **`{r.get('resource_id')}`** — *{r.get('issue_type')}* (Save **${r.get('estimated_savings'):.2f}/mo**)\n"
            f"  `{r.get('remediation_command', 'aws ec2 describe-instances')}`"
            for r in high_recs[:5]
        ])
        return f"🚨 **High-Priority Cost Recommendations ({len(high_recs)} found):**\n\n{items_md}\n\n*Action Required:* Executing these fixes will immediately cut the highest wasteful spend."

    # 5. EBS / Volume / gp2 / gp3 migration
    if any(k in msg_lower for k in ["volume", "ebs", "gp2", "gp3", "storage", "disk"]):
        if vol_recs:
            items_md = "\n".join([
                f"- **`{r.get('resource_id')}`**: {r.get('issue_type')} — Est. Savings: **${r.get('estimated_savings'):.2f}/mo**\n"
                f"  CLI: `{r.get('remediation_command')}`"
                for r in vol_recs[:5]
            ])
            return f"💾 **Storage Optimization Analysis:**\n\n{items_md}\n\n*FinOps Tip:* Upgrading EBS volumes from `gp2` to `gp3` saves ~20% on baseline storage cost with zero downtime."
        return (
            "💾 **EBS Storage Best Practices:**\n\n"
            "1. **gp2 → gp3 Upgrades:** Save 20% on provisioned storage costs with 3,000 baseline IOPS and 125 MB/s throughput included.\n"
            "   * *Command:* `aws ec2 modify-volume --volume-id <vol-id> --volume-type gp3`\n"
            "2. **Unattached Volumes:** Detached EBS volumes continue incurring storage charges. Delete or snapshot unattached volumes."
        )

    # 6. EC2 / Compute / Idle instances
    if any(k in msg_lower for k in ["ec2", "instance", "compute", "idle", "cpu", "server"]):
        if idle_recs:
            items_md = "\n".join([
                f"- **`{r.get('resource_id')}`**: {r.get('issue_type')} — Potential Savings: **${r.get('estimated_savings'):.2f}/mo**\n"
                f"  Fix: `{r.get('remediation_command')}`"
                for r in idle_recs[:5]
            ])
            return f"🖥️ **Compute Optimization Analysis:**\n\n{items_md}\n\n*FinOps Tip:* Stop or terminate idle development instances after business hours or switch to Graviton/Spot instances for stateless workloads."
        return "🖥️ **Compute Optimization:** No idle compute instances detected. To cut EC2 costs further, consider AWS Savings Plans, 1-year reserved instances, or downsizing under-utilized instance families."

    # 7. General Savings / Cost Reduction / Summary
    if any(k in msg_lower for k in ["save", "saving", "cost", "waste", "recommend", "how much", "summary", "total", "action", "cli"]):
        if recommendations:
            top_recs = sorted(recommendations, key=lambda x: x.get("estimated_savings", 0.0), reverse=True)[:4]
            recs_text = "\n".join([
                f"• **{r.get('issue_type')}** (`{r.get('resource_id')}`) — **${r.get('estimated_savings'):.2f}/mo**\n"
                f"  Command: `{r.get('remediation_command')}`"
                for r in top_recs
            ])
            return (
                f"💰 **Top Cost Optimization Recommendations:**\n\n"
                f"You have a total of **${total_savings:,.2f}/month** in potential savings across **{len(recommendations)} flagged resources**.\n\n"
                f"{recs_text}\n\n"
                f"💡 *Ask me about any specific resource ID or issue type for detailed instructions!*"
            )

    # 8. Fallback with context
    return (
        f"🤖 **FinOps AI Insights:**\n\n"
        f"Based on your current scan of **{len(resources)} cloud resources** and **{len(recommendations)} active recommendations**:\n\n"
        f"1. **Potential Monthly Savings:** **${total_savings:,.2f} USD**\n"
        f"2. **Storage Modernization:** Migrate legacy `gp2` EBS volumes to `gp3` for a guaranteed 20% cost reduction.\n"
        f"3. **Waste Elimination:** Ensure all unattached EBS volumes and stopped EC2 instances are either archived or terminated.\n\n"
        f"💡 *Tip: Configure a valid `GEMINI_API_KEY` in `backend/.env` for full generative AI responses across any custom topic!*"
    )


def generate_chat_response(
    message: str,
    chat_history: List[dict],
    resources: List[dict],
    recommendations: List[dict],
    audit_history: List[dict] = None
) -> str:
    """
    Generates a conversational response using gemini-2.5-flash model, with fallback to FinOps guidance if quota reached or unconfigured.
    """
    if circuit_breaker.can_attempt():
        try:
            client = get_genai_client()

            system_instruction = (
                "You are a Cloud FinOps AI Assistant. You have access to the user's scanned cloud resource inventory, cost recommendations, "
                "and audit history across all regions. Answer questions accurately, suggesting CLI commands, Terraform configurations, "
                "or explaining cloud billing concepts based on their actual inventory.\n\n"
                "Important guidelines:\n"
                "- When the user asks about 'high-severity', 'critical', or 'priority' issues: if there are no items strictly tagged as 'high' severity, "
                "clearly clarify that no issues met the High-Severity threshold (> $50/mo), but immediately provide a detailed breakdown of all other identified issues "
                "(such as severely idle instances, low/medium severity recommendations) along with their resource IDs, waste amount, and remediation steps.\n"
                "- Always be actionable, transparent, and provide exact AWS CLI or Terraform code whenever relevant."
            )

            inventory_context = f"Scanned Resources: {json.dumps(resources, indent=2)}\nRecommendations: {json.dumps(recommendations, indent=2)}\n"
            full_system_instruction = f"{system_instruction}\n\n{inventory_context}"

            # Gemini requires contents to start with role='user'
            contents = []
            for msg in chat_history:
                role = msg.get("role")
                text = msg.get("text")
                if role in ("user", "model") and text:
                    if not contents and role == "model":
                        continue
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
                circuit_breaker.record_success()
                log_ai_usage(len(full_system_instruction) + len(message), response.text)
                return response.text
        except Exception as e:
            circuit_breaker.record_failure(e)
            logger.warning(f"Gemini API chat notice ({e}), using dynamic FinOps fallback...")
    else:
        logger.info("AI Circuit Breaker active. Bypassing Gemini chat call for local FinOps guidance.")

    return _build_finops_fallback_response(message, resources, recommendations)

