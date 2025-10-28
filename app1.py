import boto3
import json
import re
import time

# -----------------------------
# Imports
# -----------------------------
from Meeting_Transcripts.T_M_1 import meeting_transcript
from Meeting_Transcripts.T_M_1 import meeting_attendance_report

# -----------------------------
# AWS Bedrock client setup
# -----------------------------
bedrock = boto3.client("bedrock-runtime", region_name="us-east-1")

# -----------------------------
# 1️⃣  Input Data
# -----------------------------
meeting_transcript = meeting_transcript
print(meeting_transcript)
meeting_attendance_report = meeting_attendance_report

# -----------------------------
# 2️⃣  Unified System Prompt
# -----------------------------
SYSTEM_PROMPT = """
You are a Recognition Extraction and Evaluation Expert.

Your task is to read a full meeting transcript and produce structured recognition insights in with desired output format.

### Step 1 - Identify Context **Meeting Purpose**
   - Summarize the overall purpose of the meeting in 1-2 sentences.
   - Example: “Weekly project sync to review progress and plan next sprint tasks.”

### Step 2 - Extract Contributions
- For each participant, summarize their **relevant** and **impactful** contributions.
- Ignore trivial remarks or off-topic chatter.

### Step 3 - Summarize recognition-worthy contributions from each participant concisely and professionally.
    ## Context Awareness:
    First, infer the overall *meeting archetype* from the meeting purpose and discussion themes:
    - Creative / Generative
    - Problem-Solving / Evaluative
    - Strategic / Planning
    - Operational / Alignment
    - Relational / Developmental
    - Learning / Training
    - External / Commercial

    Then, adapt the weight of recognition dimensions accordingly.

    ### Recognition Dimensions (Dynamic Weighting):
    Each participant's recognition relevancy should be computed using these factors, weighted based on meeting type:
    1. Impact
    2. Initiative
    3. Collaboration
    4. Innovation / Creativity
    5. Leadership / Mentorship
    6. Overall Input Quality (modifier on final score)

    Each factor is rated 0-3, weighted per context, and combined into a final percentage (0-100).

    ### Output Format:
    {
        "participant_name": {
            "summary": "string",
            "recognition_category": "Reward-worthy | Appreciated | Routine",
            "overall_score": float,
            "meeting_context": "string"
        }
    }

### Guidelines & Rules: 
# - Be concise and professional 
# — focus on **impact and recognition signal**, not task details. 
# - Merge overlapping or similar contributions into a cohesive summary. 
# - Keep tone positive, credible, and recognition-oriented. 
# - Ensure JSON is well-formed and parsable.
"""

# -----------------------------
# 3️⃣  Payload Construction
# -----------------------------
payload = {
    "messages": [
        {
            "role": "user",
            "content": f"""{SYSTEM_PROMPT}

Attendance JSON:
{json.dumps(meeting_attendance_report, indent=2)}

Transcript:
{meeting_transcript}
"""
        }
    ],
    "max_tokens": 8192,
    "temperature": 0.2,
    "anthropic_version": "bedrock-2023-05-31"
}

# -----------------------------
# 4️⃣  Bedrock Invocation
# -----------------------------
print("Invoking unified recognition model...\n")
start_time = time.time()

response = bedrock.invoke_model(
    modelId="arn:aws:bedrock:us-east-1:155470872893:inference-profile/us.anthropic.claude-sonnet-4-5-20250929-v1:0",
    body=json.dumps(payload),
    contentType="application/json",
)

end_time = time.time()

# -----------------------------
# 5️⃣  Parse Response
# -----------------------------
response_body = json.loads(response["body"].read())

if "content" in response_body and len(response_body["content"]) > 0:
    raw_output = response_body["content"][0].get("text", "")
else:
    print("❌ Unexpected response format from Bedrock:")
    print(json.dumps(response_body, indent=2))
    raw_output = ""

# --- Extract JSON safely ---
json_match = re.search(r"\{[\s\S]*\}", raw_output)
if json_match:
    json_str = json_match.group(0)
else:
    json_str = raw_output  # fallback

try:
    final_output = json.loads(
        json_str.strip()
        .removeprefix("```json")
        .removeprefix("```JSON")
        .removesuffix("```")
        .strip()
    )
    print("\n✅ Unified Output (Recognition Summary):\n")
    print(json.dumps(final_output, indent=2))
except json.JSONDecodeError:
    print("\n⚠️ Failed to parse model output as JSON. Showing raw output instead:\n")
    print(raw_output)
    final_output = {}

# -----------------------------
# 6️⃣  Metrics
# -----------------------------
latency = end_time - start_time
usage = response_body.get("usage", {})
input_tokens = usage.get("input_tokens", "N/A")
output_tokens = usage.get("output_tokens", "N/A")

print("\n--- Execution Summary ---")
print(f"⏱️  Latency: {latency:.2f} seconds")
print(f"🧾  Input Tokens: {input_tokens}, Output Tokens: {output_tokens}")
print(f"💰  Total Tokens: {int(input_tokens) + int(output_tokens) if isinstance(input_tokens, int) else 'N/A'}")

