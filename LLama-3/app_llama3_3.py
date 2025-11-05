import boto3
import json
import re
import time
import datetime
import os
import fasttext as ft

# -----------------------------
# Local Imports
# -----------------------------
from Meeting_Transcripts.T_M_1 import (
    english_meeting_transcript,
    english_attendance_report,
    hindi_meeting_transcript,
    hindi_attendance_report,
    french_meeting_transcript,
    french_attendees_report,
    german_meeting_transcript,
    german_attendees_report,
    spanish_meeting_transcript,
    spanish_attendees_report,
    hindi_meeting_transcript1,
    hindi_attendance_report1,
)

# -----------------------------
# Optional — Lightweight Language Detector
# -----------------------------
import langdetect
from deep_translator import GoogleTranslator 

# Load the pretrained model
ft_model = ft.load_model("../pretrained_model/lid.176.bin")

# -----------------------------
# JSON Extractor (Llama 3.3 robust version)
# -----------------------------
def extract_llama33_json(raw_output: str):

    # cleaned = re.sub(r'\\u[0-9a-fA-F]', '', raw_output)
    cleaned = re.sub(r"\$+\\?boxed\{([\s\S]*?)\}\$+", r"\1", raw_output)

    json_blocks = re.findall(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned, flags=re.IGNORECASE)
    if not json_blocks:
        json_blocks = re.findall(r"\{[\s\S]*?\}", cleaned)

    if not json_blocks:
        return {"raw_output": raw_output.strip()}, False

    candidate = json_blocks[-1].strip().replace("```", "").strip()

    try:
        return json.loads(candidate), True
    except json.JSONDecodeError:
        try:
            candidate_fixed = re.sub(r"[\s\S]*?(\{.*\})[\s\S]*", r"\1", candidate).strip()
            return json.loads(candidate_fixed), True
        except Exception:
            return {"raw_output": candidate.strip()}, False
        
def extract_text_sample(transcript_json, max_sentences=10):
    """
    Combines first few 'text' entries from transcript into one string
    to detect dominant language.
    """
    if "transcript" not in transcript_json:
        raise ValueError("Transcript JSON missing 'transcript' key")

    texts = []
    for item in transcript_json["transcript"][:max_sentences]:
        if "text" in item:
            texts.append(item["text"])
    return " ".join(texts)


def translate_keys(obj, source_lang="auto", target_lang="en"):
    """Recursively translate all dictionary keys to English."""
    if isinstance(obj, dict):
        new_dict = {}
        for k, v in obj.items():
            try:
                # Translate the key to English
                translated_key = GoogleTranslator(source=source_lang, target=target_lang).translate(k)
            except Exception:
                translated_key = k  # fallback to original key if translation fails
            # Recurse into nested dictionaries/lists
            new_dict[translated_key] = translate_keys(v, source_lang, target_lang)
        return new_dict
    elif isinstance(obj, list):
        return [translate_keys(item, source_lang, target_lang) for item in obj]
    else:
        return obj  # keep values unchanged


# -----------------------------
# AWS Bedrock Setup
# -----------------------------
bedrock = boto3.client("bedrock-runtime", region_name="us-east-1")

# -----------------------------
# Select Input (you can swap datasets here)
# -----------------------------
meeting_transcript = french_meeting_transcript
meeting_attendance_report = french_attendees_report

sample_text = extract_text_sample(meeting_transcript, max_sentences=50)

# -----------------------------
# Detect transcript language
# -----------------------------
# try:
#     detected_lang = langdetect.detect(json.dumps(meeting_transcript))
# except Exception:
#     detected_lang = "en"

prediction = ft_model.predict(sample_text)
# print(prediction)
lang = prediction[0][0].replace("__label__", "")

print(f"Detected transcript language: {lang}")

SYSTEM_PROMPT = """ 
### SYSTEM INSTRUCTION
You are a **Recognition Extraction and Evaluation Expert**.

Your goal: Analyze a complete meeting transcript and produce **structured, context-aware recognition insights** in the defined JSON format.

Your analysis should help the meeting organizer identify individuals whose actions or inputs deserve appreciation or recognition — based on measurable impact, initiative, collaboration, or thought leadership.

---

## STEP 1 — Identify Context: Meeting Purpose

**Objective:**  
Understand and summarize the main intent and flow of the meeting to anchor later evaluation.

**Instructions:**  
- Derive the primary goal of the meeting — what participants were collectively trying to achieve or discuss.  
- Capture secondary themes or sub-objectives that influenced tone or contribution style.  
- Summarize the purpose in one clear, action-oriented statement.

**Example:**  
> "Team discussion focused on optimizing database performance and sharing implementation best practices."

**Note:**  
Avoid vague or generic summaries. Focus on the *actionable intent* of the meeting.

---

## STEP 2 — Extract and Attribute Contributions

**Objective:**  
Identify and summarize each participant's substantive, recognition-relevant actions or inputs.

**Instructions:**  
- Detect all distinct participant mentions (names, identifiers, contextual references).  
- For each participant, capture only *meaningful contributions* that:  
  - Advanced the discussion, solved a problem, or clarified direction  
  - Demonstrated ownership, expertise, or leadership  
  - Strengthened collaboration, motivation, or clarity in the team  
- Ignore filler speech, greetings, or simple acknowledgments.  
- Merge multiple turns into a single cohesive summary per participant.  

**Example:**  
> "Outlined indexing and partitioning strategies that reduced query time by 40(percent) and explained implementation trade-offs."

**Note:**  
Keep summaries fact-based but outcome-oriented — what the person contributed and *how it added value*.

---

## STEP 3 — Evaluate Recognition-Worthy Contributions

**Objective:**  
Assess each participant's recognition relevance and provide a concise, *actionable* reason showing *why* the organizer should appreciate them.

**Context Awareness:**  
Infer the meeting archetype from the purpose and tone:  
- Creative / Generative  
- Problem-Solving / Evaluative  
- Strategic / Planning  
- Operational / Alignment  
- Relational / Developmental  
- Learning / Training  
- External / Commercial  

Adjust recognition emphasis accordingly (e.g., reward creativity in generative meetings, impact in problem-solving ones).

**Recognition Dimensions (0-3 each, combined into 0-100 score):**  
1. **Impact:** measurable or observable contribution significance  
2. **Initiative:** proactive ownership or problem-solving drive  
3. **Collaboration:** teamwork, support, and constructive engagement  
4. **Innovation / Creativity:** new ideas or unique perspectives  
5. **Leadership / Mentorship:** enabling others or guiding direction  
6. **Overall Input Quality:** clarity, professionalism, and relevance  

---

### Crafting the "Reason"

The “reason” should answer **why this person deserves appreciation** — not just what they did.

- Highlight the *value* or *outcome* of their contribution.
- Use recognition-oriented phrasing such as:  
  - “Demonstrated strong leadership by…”  
  - “Enabled smoother execution through…”  
  - “Provided insightful technical direction that…”  
  - “Elevated the discussion by…”  
  - “Showed initiative by identifying…”  
- Avoid dry factual summaries like “Participated in the discussion” or “Explained database concepts.”  
- Make it easy for the organizer to see *why* the contribution matters.

**Examples:**
- “Demonstrated technical leadership by simplifying the database optimization strategy and guiding the team on indexing best practices.”
- “Proactively identified implementation challenges and offered clear solutions, helping align the group's next steps.”
- “Showed exceptional collaboration by connecting multiple ideas into a unified approach.”

---

## OUTPUT FORMAT
```json
{
  "meeting_context": "string",
  "participants": {
    "participant_name": {
      "reason": "string",
      "summary": "string",
      "overall_score": number
    }
  }
}
"""

# -----------------------------
# Translate SYSTEM_PROMPT if needed
# -----------------------------
if lang != "en":
    try:
        SYSTEM_PROMPT = GoogleTranslator(source="en", target=lang).translate(SYSTEM_PROMPT)
        print(f"SYSTEM_PROMPT translated to {lang}")
    except Exception as e:
        print(f"Translation failed, falling back to English prompt: {e}")
        SYSTEM_PROMPT = SYSTEM_PROMPT
else:
    SYSTEM_PROMPT = SYSTEM_PROMPT

# -----------------------------
# Combined prompt
# -----------------------------
combined_prompt = f"""
{SYSTEM_PROMPT}

Attendance JSON:
{json.dumps(meeting_attendance_report, indent=2)}

Transcript:
{meeting_transcript}

Now generate the structured recognition output as valid JSON.
Respond with exactly one JSON object.
Do not repeat, rephrase, or surround it with LaTeX, markdown, or explanations.
"""


# -----------------------------
# Model Config — Llama 3.3 70B Instruct
# -----------------------------
MODEL_NAME = "Llama 3.3 70B Instruct"
MODEL_ID = "arn:aws:bedrock:us-east-1:155470872893:inference-profile/us.meta.llama3-3-70b-instruct-v1:0"

# -----------------------------
# Output Directory
# -----------------------------
output_dir = "./LLama-3/bedrock_llama3_3_results"
os.makedirs(output_dir, exist_ok=True)

# -----------------------------
# Payload
# -----------------------------
payload = {
    "prompt": combined_prompt,
    "max_gen_len": 8192,
    "temperature": 0.2,
    "top_p": 0.9
}

# -----------------------------
# Model Invocation
# -----------------------------
print(f"\n Running model: {MODEL_NAME}\n")

start_time = time.time()

try:
    response = bedrock.invoke_model(
        modelId=MODEL_ID,
        body=json.dumps(payload),
        contentType="application/json",
        accept="application/json"
    )

    end_time = time.time()

    # Extract response content
    response_body = json.loads(response["body"].read())
    raw_output = (
    response_body.get("generation")
    or response_body.get("outputText")
    or response_body.get("outputs", [{}])[0].get("text")
    or ""
)


    print("\nRaw model output received.\n")
    decoded_data = json.dumps(raw_output, indent=2)

    # Parse structured JSON
    final_output, parsed = extract_llama33_json(raw_output)

    # -----------------------------
    # Metrics
    # -----------------------------
    latency = end_time - start_time
    input_tokens = response_body.get("prompt_token_count", "N/A")
    output_tokens = response_body.get("generation_token_count", "N/A")

    result_data = {
        "model_name": MODEL_NAME,
        "model_id": MODEL_ID,
        "latency_seconds": latency,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "parsed_successfully": parsed,
        "output": final_output
    }
    

    # -----------------------------
    # Save outputs
    # -----------------------------
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

    parsed_path = os.path.join(output_dir, f"{MODEL_NAME.replace('.', '_')}_french.json")

    # if lang != "en":
    #     translated_data = translate_keys(result_data, source_lang=lang, target_lang="en")
    # else:
    #     translated_data = result_data

    # with open(parsed_path, "w", encoding="utf-8") as f:
    #     json.dump(translated_data, f, ensure_ascii=False, indent=2)

    with open(parsed_path, "w", encoding="utf-8") as f:
        json.dump(result_data, f, ensure_ascii=False, indent=2)

    # print(f"Saved raw output → {raw_path}")
    print(f"Saved parsed JSON → {parsed_path}")
    print(f"⏱Latency: {latency:.2f}s | Tokens In: {input_tokens} Out: {output_tokens}\n")

except Exception as e:
    print(f"Error running {MODEL_NAME}: {e}")

print("\nRun complete for Llama 3.3 70B Instruct.")