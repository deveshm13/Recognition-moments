
import json
import re
import time
import datetime
import os
import boto3

# -----------------------------
# Imports
# -----------------------------
from Meeting_Transcripts.T_M_1 import meeting_transcript_1
from Meeting_Transcripts.T_M_1 import meeting_attendance_report1

# -----------------------------
# AWS Bedrock client setup
# -----------------------------
bedrock = boto3.client("bedrock-runtime", region_name="us-east-1")

# -----------------------------
# 1️⃣  Input Data
# -----------------------------
meeting_transcript = meeting_transcript_1

# print(meeting_transcript)
meeting_attendance_report = meeting_attendance_report1

SYSTEM_PROMPT = """ 
### SYSTEM INSTRUCTION
You are a **Recognition Extraction and Evaluation Expert**.

Your task: Analyze a complete meeting transcript and produce **structured, context-aware recognition insights** in the defined JSON format.

---

## STEP 1 — Identify Context: Meeting Purpose

**Objective:**  
Understand and summarize the main intent and flow of the meeting to anchor later evaluation.

**Instructions:**  
- Derive the primary goal of the meeting — what participants were collectively trying to achieve or discuss.  
- Capture secondary themes or sub-objectives (if any) that influenced participant behavior or tone.  
- Use cues such as meeting title, recurring phrases, or repeated focus points.  
- Summarize the purpose in 1-2 clear, action-focused sentences.

**Example:**  
> "Project milestone review focusing on backend integration progress and risk mitigation for the next release."

**Note:**  
Avoid generic summaries like “team meeting.” Infer purpose from actual context and outcomes.

---

## STEP 2 — Extract and Attribute Contributions

**Objective:**  
Identify and summarize each participant's substantive and recognition-relevant actions or inputs.

**Instructions:**  
- Detect all distinct participant mentions (names, identifiers, contextual references).  
- For each participant, capture only meaningful contributions that:  
  - Advance the discussion or problem-solving  
  - Demonstrate initiative, leadership, or creativity  
  - Clarify direction, provide useful feedback, or enable collaboration  
- Ignore:  
  - Filler speech, greetings, or acknowledgments (“yes”, “agree”, “okay”)  
  - Repetitions without new substance  
- Combine multiple related turns into one cohesive summary focusing on the participant's role, intent, and impact.

**Example:**  
> "Proposed a simplified data model to reduce API complexity and clarified integration timelines."

**Note:**  
Maintain a neutral tone focusing on factual contribution and observable impact.

---

## STEP 3 — Evaluate Recognition-Worthy Contributions

**Objective:**  
Assess each participant's recognition relevance and score their contribution contextually.

**Context Awareness:**  
Infer the meeting archetype from overall purpose and tone:  
- Creative / Generative  
- Problem-Solving / Evaluative  
- Strategic / Planning  
- Operational / Alignment  
- Relational / Developmental  
- Learning / Training  
- External / Commercial  

Adjust recognition weighting dynamically based on the archetype.

**Recognition Dimensions (0-3 each, combined into 0-100 score):**  
1. **Impact:** measurable or observed outcome significance  
2. **Initiative:** proactive ownership or problem-solving  
3. **Collaboration:** teamwork and constructive interaction  
4. **Innovation / Creativity:** originality or new idea generation  
5. **Leadership / Mentorship:** guidance or enabling others  
6. **Overall Input Quality:** clarity, relevance, and professionalism  

**Concise Reason:**
Generate a one-line "reason" that captures the essence of the participant's recognition-worthiness.
- It should be short, clear, and easy for the organizer to read and decide appreciation value.
- Avoid generic statements like “good contribution” or “helped discussion.”
- Example: “Drove key architectural decision by resolving API conflict.” or “Provided actionable design feedback improving user experience.”

---

## OUTPUT FORMAT
```json
{
    "meeting_context": "string",
    "participant_name": {
        "reason": "string",
        "summary": "string",
        "overall_score": float
    }
}

"""

MODEL_LIST = [
    {
        "name": "Nova Lite",
        "id": "amazon.nova-lite-v1:0"
    },
    {
        "name": "Nova Micro",
        "id": "amazon.nova-micro-v1:0"
    },
    {
        "name": "Nova Premier",
        "id": "arn:aws:bedrock:us-east-1:155470872893:inference-profile/us.amazon.nova-premier-v1:0"
    },
    {
        "name": "Nova Pro",
        "id": "amazon.nova-pro-v1:0"
    }
]

# -----------------------------
# 3️⃣ Output Directory Setup
# -----------------------------
# timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
output_dir = f"bedrock_model_results_Amazon"
os.makedirs(output_dir, exist_ok=True)


payload = {
    "messages": [
        {
            "role": "user",
            "content": [
                {
                    "text": f"""
{SYSTEM_PROMPT}

Attendance JSON:
{json.dumps(meeting_attendance_report, indent=2)}

Transcript:
{meeting_transcript}

Now generate the structured recognition output as valid JSON.
"""
                }
            ]
        }
    ],
    "inferenceConfig": {
        "maxTokens": 4096,  # ✅ Must be integer, not float/string
        "temperature": 0.2,
        "topP": 0.9
    }
}



# -----------------------------
# Model Loop
# -----------------------------
results_summary = {}

for model in MODEL_LIST:
    model_name = model["name"]
    model_id = model["id"]
    print(f"\n🚀 Running model: {model_name}\n")

    payload = payload.copy()

    start_time = time.time()
    try:
        response = bedrock.invoke_model(
            modelId=model_id,
            body=json.dumps(payload),
            contentType="application/json",
            accept="application/json"
        )
        end_time = time.time()

        response_body = json.loads(response["body"].read())
        raw_output = (
    response_body.get("output", {})
    .get("message", {})
    .get("content", [])[0]
    .get("text", "")
)
        json_match = re.search(r"\{[\s\S]*\}", raw_output)
        json_str = json_match.group(0) if json_match else raw_output

        try:
            final_output = json.loads(
                json_str.strip()
                .removeprefix("```json")
                .removeprefix("```JSON")
                .removesuffix("```")
                .strip()
            )
            parsed = True
        except json.JSONDecodeError:
            final_output = {"raw_output": raw_output}
            parsed = False

        latency = end_time - start_time
        usage = response_body.get("usage", {})

        input_tokens = usage.get("inputTokens", 0)
        output_tokens = usage.get("outputTokens", 0)
        total_tokens = usage.get("totalTokens", 0)

        result_data = {
            "model_name": model_name,
            "model_id": model_id,
            "latency_seconds": latency,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "parsed_successfully": parsed,
            "output": final_output
        }

        results_summary[model_name] = result_data

        output_path = os.path.join(output_dir, f"{model_name.replace(' ', '_')}_output.json")
        with open(output_path, "w") as f:
            json.dump(result_data, f, indent=2)

        print(f"✅ Saved results for {model_name} → {output_path}")
        print(f"⏱️ Latency: {latency:.2f}s | 🧾 Tokens In: {input_tokens}, Out: {output_tokens}\n")

    except Exception as e:
        print(f"❌ Error running model {model_name}: {e}")
        continue

# -----------------------------
# Summary File
# -----------------------------
summary_path = os.path.join(output_dir, "summary_all_models.json")
with open(summary_path, "w") as f:
    json.dump(results_summary, f, indent=2)

print("\n🎯 Benchmarking complete!")
print(f"All model results saved under: {output_dir}")