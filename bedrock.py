import boto3
import json
from Meeting_Transcripts.Gemini_generated_transcript import Meeting_Transcript_With_Multiple_Employee
from Meeting_Transcripts.meeting1 import meeting_transcript
from Prompt_Chaining_S.Prompts import system_prompt_for_step_1,system_prompt_for_step_2,system_prompt_for_step_3,final_system_prompt_for_step_1, final_system_prompt_for_step_3
from Meeting_Transcripts.T_M_1 import meeting_transcript,meeting_attendance_report,french_meeting_transcript,french_attendees_report

import re
import time
# -----------------------------
# AWS Bedrock client setup
# -----------------------------
bedrock = boto3.client("bedrock-runtime", region_name="us-east-1")

# -----------------------------
# Stage 0: Coreference Resolution
# -----------------------------

def resolve_coreferences_gpt_oss(transcript: str) -> str:
    """
    Resolves pronouns to named entities in the transcript using GPT-OSS on Bedrock.
    """
    system_prompt = """
You are a Coreference Resolver.
Task:
- Replace all pronouns (he, she, they, his, her, etc.) with the correct named entities from the transcript.
- Maintain readability and sentence structure.
- Do not change the meaning of any statement.
- Return only the resolved transcript as plain text, no JSON or extra formatting.
"""
    payload = {
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Transcript:\n{transcript}"}
        ],
        "max_tokens": 4000,
        "temperature": 0.0  # deterministic
    }

    response = bedrock.invoke_model(
        modelId="openai.gpt-oss-20b-1:0",  # GPT-OSS model
        body=json.dumps(payload),
        contentType="application/json"
    )

    response_body = json.loads(response["body"].read())

    # Extract model output text
    if "content" in response_body and len(response_body["content"]) > 0:
        resolved_transcript = response_body["content"][0].get("text", "")
        return resolved_transcript
    else:
        raise ValueError("Unexpected response format from Bedrock GPT-OSS model.")

# Replace with your actual transcript text
meeting_transcript = french_meeting_transcript

# resolved_transcript = resolve_coreferences_gpt_oss(meeting_transcript)
# print("Coreference resolution complete.\n")


meeting_attendance_report = french_attendees_report


# -----------------------------
# System prompt for Step 1
# -----------------------------
system_prompt_for_step_1 = final_system_prompt_for_step_1

# -----------------------------
# System prompt for Step 2
# -----------------------------
system_prompt_for_step_2 = system_prompt_for_step_2

# -----------------------------
# Bedrock call: Step 1
# -----------------------------
payload_step1 = {
    "messages": [
        {
            "role": "user",
            "content": f"""{system_prompt_for_step_1}

### Input Data
Attendance JSON:
{json.dumps(meeting_attendance_report, indent=2)}

Transcript:
{meeting_transcript}
"""
        }
    ],
    "max_tokens": 4000,
    "temperature": 0.1,
    "anthropic_version": "bedrock-2023-05-31"
}

start_time_step1 = time.time()
response_step1 = bedrock.invoke_model(
    modelId="arn:aws:bedrock:us-east-1:155470872893:inference-profile/global.anthropic.claude-haiku-4-5-20251001-v1:0",
    body=json.dumps(payload_step1),
    contentType="application/json",
)
end_time_step1 = time.time()

# -----------------------------
# Parse Step 1 response
# -----------------------------
response_body = json.loads(response_step1["body"].read())

if "content" in response_body and len(response_body["content"]) > 0:
    content = response_body["content"][0].get("text", "")

    # Clean fenced code block markdown if present
    content_clean = (
        content.strip()
        .removeprefix("```json")
        .removeprefix("```JSON")
        .removesuffix("```")
        .strip()
    )

    try:
        step1_output = json.loads(content_clean)
        print("Step 1 Output (Participants & Meeting Purpose):\n")
        print(json.dumps(step1_output, indent=2))
    except json.JSONDecodeError:
        print(" JSON parse failed, showing raw model output instead:")
        print(content)
        step1_output = {"meeting_purpose": "", "participants": []}  # fallback
else:
    print("Unexpected response format:")
    print(json.dumps(response_body, indent=2))
    step1_output = {"meeting_purpose": "", "participants": []}



# -----------------------------
# Step 2: Candidate-wise Relevant Contributions
# -----------------------------

# Extract participants and meeting purpose from Step 1 output
participants = [p["name"] for p in step1_output.get("participants", [])]
meeting_purpose = step1_output.get("meeting_purpose", "")

# Prepare Step 2 prompt dynamically
step2_prompt = f"""
{system_prompt_for_step_2}

Participants List:
{participants}

Meeting Purpose:
{meeting_purpose}

Transcript:
{meeting_transcript}
"""

payload_step2 = {
    "messages": [
        {
            "role": "user",
            "content": step2_prompt
        }
    ],
    "max_tokens": 8000,
    "temperature": 0.3,
    "anthropic_version": "bedrock-2023-05-31"
}
start_time_step2 = time.time()
response_step2 = bedrock.invoke_model(
    modelId="arn:aws:bedrock:us-east-1:155470872893:inference-profile/us.anthropic.claude-sonnet-4-5-20250929-v1:0",
    body=json.dumps(payload_step2),
    contentType="application/json",
)
end_time_step2 = time.time()
# -----------------------------
# Parse Step 2 response
# -----------------------------
response_body_step2 = json.loads(response_step2["body"].read())

if "content" in response_body_step2 and len(response_body_step2["content"]) > 0:
    content_step2 = response_body_step2["content"][0].get("text", "")
    try:
        step2_output = json.loads(content_step2)
        print("\nStep 2 Output (Candidate-wise Relevant Contributions):\n")
        print(json.dumps(step2_output, indent=2))
    except json.JSONDecodeError:
        print("Failed to parse Step 2 output as JSON. Raw output:")
        print(content_step2)
else:
    print("Unexpected response format in Step 2:")
    print(json.dumps(response_body_step2, indent=2))


# ============================================================
# Step 3: Recognition Scoring & Filtering
# ============================================================

system_prompt_for_step_3 = final_system_prompt_for_step_3


# --- Robust JSON extraction ---
json_match = re.search(r"\{[\s\S]*\}", content_step2)
if json_match:
    json_str = json_match.group(0)
else:
    json_str = content_step2  # fallback

try:
    step2_output = json.loads(json_str)
    print("\n✅ Step 2 Output (Parsed Successfully):\n")
    # Serialize safely
    try:
        step2_json_string = json.dumps(step2_output, indent=2)
    except Exception as e:
        print(f"Failed to serialize Step 2 output due to error: {e}")
        step2_json_string = "{}"
except json.JSONDecodeError as e:
    print(f"⚠️ Failed to parse Step 2 output as JSON ({e}). Raw output below:\n")
    print(content_step2)
    step2_output = {}


step3_prompt = f"""
{system_prompt_for_step_3}

Meeting Purpose:
{meeting_purpose}

Contributions JSON:
{step2_json_string}
"""
#Step 3 payload
payload_step3 = {
    "messages": [
        {
            "role": "user",
            "content": step3_prompt
        }
    ],
    "max_tokens": 4096,
    # "temperature": 0.2,
    "top_p": 0.2,
    "anthropic_version": "bedrock-2023-05-31"
}
start_time_step3 = time.time()
# Invoke Bedrock for Step 3
response_step3 = bedrock.invoke_model(
    modelId="arn:aws:bedrock:us-east-1:155470872893:inference-profile/us.anthropic.claude-sonnet-4-5-20250929-v1:0",
    body=json.dumps(payload_step3),
    contentType="application/json",
)
end_time_step3 = time.time()
# Parse Step 3 response
response_body_step3 = json.loads(response_step3["body"].read())

if "content" in response_body_step3 and len(response_body_step3["content"]) > 0:
    content_step3 = response_body_step3["content"][0].get("text", "")
    try:
        step3_output = json.loads(
            content_step3.strip()
            .removeprefix("```json")
            .removeprefix("```JSON")
            .removesuffix("```")
            .strip()
        )
        print("\nStep 3 Output (Recognition Scoring & Ranking):\n")
        print(json.dumps(step3_output, indent=2))
    except json.JSONDecodeError:
        print("Failed to parse Step 3 output as JSON. Raw output:")
        print(content_step3)
else:
    print("Unexpected response format in Step 3:")
    print(json.dumps(response_body_step3, indent=2))

# --- Corrected final block ---

# Latency is already calculated correctly
latency_step1 = end_time_step1 - start_time_step1
latency_step2 = end_time_step2 - start_time_step2
latency_step3 = end_time_step3 - start_time_step3

# For Claude models, token usage is in the main response body
# Note: You have already parsed these bodies earlier in the script.
# We are referencing the variables `response_body`, `response_body_step2`, `response_body_step3`.

usage_step1 = response_body.get('usage', {})
usage_step2 = response_body_step2.get('usage', {})
usage_step3 = response_body_step3.get('usage', {})

input_tokens_step1 = usage_step1.get('input_tokens', 'N/A')
output_tokens_step1 = usage_step1.get('output_tokens', 'N/A')

input_tokens_step2 = usage_step2.get('input_tokens', 'N/A')
output_tokens_step2 = usage_step2.get('output_tokens', 'N/A')

input_tokens_step3 = usage_step3.get('input_tokens', 'N/A')
output_tokens_step3 = usage_step3.get('output_tokens', 'N/A')

# Print latency and costing information
print("\n--- Execution Summary ---")
print("Latency:")
print(f"  - Step 1: {latency_step1:.2f} seconds")
print(f"  - Step 2: {latency_step2:.2f} seconds")
print(f"  - Step 3: {latency_step3:.2f} seconds")

print("\nInvocation Metrics (for costing):")
print(f"  - Step 1: Input Tokens: {input_tokens_step1}, Output Tokens: {output_tokens_step1}")
print(f"  - Step 2: Input Tokens: {input_tokens_step2}, Output Tokens: {output_tokens_step2}")
print(f"  - Step 3: Input Tokens: {input_tokens_step3}, Output Tokens: {output_tokens_step3}")
