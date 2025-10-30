import boto3
import json
import re
import os
import time

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

# -----------------------------
# 2️⃣  Unified System Prompt
# -----------------------------
SYSTEM_PROMPT = """
<system>
  You are a Recognition Extraction and Evaluation Expert.
  Your task is to analyze a complete meeting transcript and produce structured, context-aware recognition insights
  in the defined JSON format.
</system>

<steps>

  <step number="1" name="Identify Context: Meeting Purpose">
    <objective>
      Understand and summarize the main intent and flow of the meeting to anchor later evaluation.
    </objective>

    <instructions>
      - Derive the primary goal of the meeting — what participants were collectively trying to achieve or discuss.
      - Capture secondary themes or sub-objectives (if any) that influenced participant behavior or tone.
      - Use cues such as meeting title, recurring phrases, or repeated focus points.
      - Summarize the purpose in 1-2 clear, action-focused sentences.
    </instructions>

    <example>
      "Project milestone review focusing on backend integration progress and risk mitigation for the next release."
    </example>

    <note>
      Avoid generic summaries like "team meeting" — infer purpose from actual context and outcomes.
    </note>
  </step>

  <step number="2" name="Extract and Attribute Contributions">
    <objective>
      Identify and summarize each participant's substantive and recognition-relevant actions or inputs.
    </objective>

    <instructions>
      - Detect all distinct participant mentions (names, identifiers, contextual references).
      - For each participant, capture only meaningful contributions that:
        * Advance the discussion or problem-solving
        * Demonstrate initiative, leadership, or creativity
        * Clarify direction, provide useful feedback, or enable collaboration
      - Ignore:
        * Filler speech, greetings, or acknowledgments ("yes", "agree", "okay")
        * Repetitions without new substance
      - Combine multiple related turns into one cohesive summary focusing on the participant's role, intent, and impact.
    </instructions>

    <example>
      "Proposed a simplified data model to reduce API complexity and clarified integration timelines."
    </example>

    <note>
      Maintain a neutral tone, focusing on factual contribution and observable impact.
    </note>
  </step>

  <step number="3" name="Evaluate Recognition-Worthy Contributions Based on Meeting Context/Archetype/Purpose">
  <objective>
    Assess each participant's recognition relevance and provide a concise, actionable reason reflecting their contribution's value.
  </objective>

  <context_awareness>
    Infer the meeting archetype from overall purpose and conversational tone:
    - Creative / Generative
    - Problem-Solving / Evaluative
    - Strategic / Planning
    - Operational / Alignment
    - Relational / Developmental
    - Learning / Training
    - External / Commercial

    Adjust recognition weighting dynamically based on the archetype to ensure fair evaluation across meeting types.
  </context_awareness>

  <recognition_dimensions>
    Evaluate each participant using the following factors (scored 0-3), weighted into an overall percentage (0-100):

    1. Impact - measurable or visible effect on the meeting's goal  
    2. Initiative - proactive ownership or problem-solving behavior  
    3. Collaboration - constructive engagement or enabling teamwork  
    4. Innovation / Creativity - originality or introducing valuable ideas  
    5. Leadership / Mentorship - guiding or enabling others  
    6. Overall Input Quality - clarity, relevance, and professionalism  
  </recognition_dimensions>

  <concise_reason>
    Generate a one-line "reason" that captures the essence of the participant's recognition-worthiness.
    - It should be short, clear, and easy for the organizer to read and decide appreciation value.
    - Avoid generic statements like “good contribution” or “helped discussion.”
    - Example: “Drove key architectural decision by resolving API conflict.” or “Provided actionable design feedback improving user experience.”
  </concise_reason>
</step>

</steps>

<output_format>
{
    "meeting_context": "string",
    "participant_name": {
      "reason": "string",     
      "summary": "string",
      "overall_score": float
    }
}
</output_format>

<guidelines>
  - Be concise, factual, and recognition-oriented.
  - Focus on impact and recognition signals, not procedural or trivial details.
  - Merge overlapping or redundant statements into one coherent summary per participant.
  - Maintain a professional, balanced, and positive tone.
  - Ensure output is valid and strictly JSON-parsable.
  - Do not fabricate names or roles not supported by the transcript.
  - When uncertain, classify as "Routine" with appropriate confidence in the score.
</guidelines>
"""

MODEL_LIST = [
    {
        "name": "Claude Opus 4.1",
        "id": "arn:aws:bedrock:us-east-1:155470872893:inference-profile/us.anthropic.claude-opus-4-1-20250805-v1:0"
    },
    {
        "name": "Claude Haiku 4.5",
        "id": "arn:aws:bedrock:us-east-1:155470872893:inference-profile/global.anthropic.claude-haiku-4-5-20251001-v1:0"
    },
    {
        "name": "Claude Sonnet 4",
        "id": "arn:aws:bedrock:us-east-1:155470872893:inference-profile/global.anthropic.claude-sonnet-4-20250514-v1:0"
    },
    {
        "name": "Claude Sonnet 4.5",
        "id": "arn:aws:bedrock:us-east-1:155470872893:inference-profile/global.anthropic.claude-sonnet-4-5-20250929-v1:0"
    },
    {
        "name": "Claude 3.5 Haiku",
        "id": "arn:aws:bedrock:us-east-1:155470872893:inference-profile/us.anthropic.claude-3-5-haiku-20241022-v1:0"
    },
    {
        "name": "Claude 3.5 Sonnet v2",
        "id": "arn:aws:bedrock:us-east-1:155470872893:inference-profile/us.anthropic.claude-3-5-sonnet-20241022-v2:0"
    }
]


output_dir = f"bedrock_model_results_Claude"
os.makedirs(output_dir, exist_ok=True)



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
# 6️⃣  Model Evaluation Loop
# -----------------------------
results_summary = {}

for model in MODEL_LIST:
    model_name = model["name"]
    model_id = model["id"]
    print(f"\n🚀 Running model: {model_name}\n")

    start_time = time.time()

    try:
        response = bedrock.invoke_model(
            modelId=model_id,
            body=json.dumps(payload),
            contentType="application/json",
        )

        end_time = time.time()
        latency = end_time - start_time

        # -----------------------------
        # Parse response
        # -----------------------------
        response_body = json.loads(response["body"].read())

        if "content" in response_body and len(response_body["content"]) > 0:
            raw_output = response_body["content"][0].get("text", "")
        else:
            print(f"⚠️ Unexpected response format for {model_name}")
            raw_output = json.dumps(response_body, indent=2)

        # Extract JSON from raw output
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

        # -----------------------------
        # Metrics
        # -----------------------------
        usage = response_body.get("usage", {})
        input_tokens = usage.get("input_tokens", "N/A")
        output_tokens = usage.get("output_tokens", "N/A")

        result_data = {
            "model_name": model_name,
            "model_id": model_id,
            "latency_seconds": round(latency, 2),
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "parsed_successfully": parsed,
            "output": final_output
        }

        results_summary[model_name] = result_data

        # -----------------------------
        # Save model-wise JSON
        # -----------------------------
        output_path = os.path.join(output_dir, f"{model_name.replace('.', '_')}_output.json")
        with open(output_path, "w") as f:
            json.dump(result_data, f, indent=2)

        print(f"✅ Saved results for {model_name} → {output_path}")
        print(f"⏱️ Latency: {latency:.2f}s | 🧾 Tokens In: {input_tokens}, Out: {output_tokens}\n")

    except Exception as e:
        print(f"Error running {model_name}: {e}")

# -----------------------------
# 7️⃣  Summary File
# -----------------------------
summary_path = os.path.join(output_dir, "summary_all_models.json")
with open(summary_path, "w") as f:
    json.dump(results_summary, f, indent=2)

print("\n🎯 Benchmarking complete!")
print(f"All model results saved under: {output_dir}")