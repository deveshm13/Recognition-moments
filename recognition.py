import os
from typing import Optional, TYPE_CHECKING
from Meeting_Transcripts.Gemini_generated_transcript import Meeting_Transcript_With_Multiple_Employee

try:
    from groq import Groq
except Exception:
    Groq = None  # type: ignore

from Prompts.recognition_prompt2 import SYSTEM_PROMPT
# -----------------------------------------
# 1️⃣  Configuration
# -----------------------------------------
# export GROQ_API_KEY="your_api_key_here"
if TYPE_CHECKING:
    from groq import Groq as GroqType  # for type hints only


def _get_client():
    if Groq is None:
        raise RuntimeError("The 'groq' package is not installed. Please run 'pip install groq'.")
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY environment variable is not set.")
    return Groq(api_key=api_key)

# -----------------------------------------
# 3️⃣  Helper Function
# -----------------------------------------
def find_recognition_moments(transcript: str) -> str:
    """
    Uses LLaMA 3.1 8B on Groq to extract recognition/appreciation moments
    from a meeting transcript.
    """
    user_prompt = f"""
### Meeting Transcript:
{transcript}

### Task:
Extract and summarize all recognition or appreciation moments as per the above instructions.
"""

    client = _get_client()
    completion = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.2,
        max_tokens=4000,
    )

    # ✅ Correct Groq SDK syntax
    return completion.choices[0].message.content.strip()

# -----------------------------------------
# 4️⃣  Main Script
# -----------------------------------------
if __name__ == "__main__":
    print("\n=== Recognition Moment Finder (LLaMA 3.1 70B on Groq) ===\n")

    # Load transcript
    if os.path.exists("E_T_M_13Oct_70B.txt"):
        with open("E_T_M_13Oct_70B.txt", "r", encoding="utf-8") as f:
            transcript_text = f.read().strip()
    else:
        print("No 'E_T_M_13Oct_70B.txt' found — please paste your transcript below.")
        transcript_text = input("\nPaste transcript:\n")
    # transcript_text = Meeting_Transcript_With_Multiple_Employee

    print("\nProcessing... Please wait...\n")
    recognition_data = find_recognition_moments(transcript_text)

    print("=== Recognition Moments Found ===\n")
    print(recognition_data)

    # Save output
    with open("Recognition_Moments/r_m_13Oct_70B_with_P2.json", "w", encoding="utf-8") as f:
        f.write(recognition_data)

    print("\n✅ Saved extracted recognition data to 'Recognition_Moments/r_m_13Oct_70B_with_P2.json'\n")
