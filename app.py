import os
from groq import Groq

# -----------------------------
# 1️⃣  Configuration
# -----------------------------
# export GROQ_API_KEY="your_api_key_here"
print("Using Groq API Key:", "Set" if os.getenv("GROQ_API_KEY") else "Not Set")
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

# -----------------------------
# 2️⃣  System Prompt
# -----------------------------
SYSTEM_PROMPT = """
You are an AI transcript enhancer for meetings. 
Your task is to transform a raw, possibly messy Zoom transcript into a clear, readable, and structured format.

### Requirements:
1. Correct grammar, punctuation, and capitalization.
2. Separate by speakers clearly (bold names).
3. Identify and label languages if multiple are detected.
4. If non-English speech is detected, translate it into English but also preserve the original text in parentheses.
5. Keep timestamps if present.
6. Do not invent content — only clarify or fix it.

### Input Transcript:
{transcript}

### Output Format:
{desired_format}

Now return the improved transcript below:
"""

# -----------------------------
# 3️⃣  Helper Function
# -----------------------------
def enhance_transcript(transcript: str) -> str:
    """
    Sends a raw Zoom transcript to LLaMA 3.1 8B via Groq
    and returns the enhanced version.
    """
    # Construct user prompt
    user_prompt = f"""
### Input Transcript:
{transcript}

### Output Format:
Readable transcript with:
- Bold speaker names
- Translated non-English parts (original kept in parentheses)
- Correct grammar, punctuation, and casing
- Preserve timestamps if available

Now enhance the transcript as per the above instructions.
"""

    # Call LLaMA-3.1-8B on Groq
    completion = client.chat.completions.create(
        model="llama-3.3-70b-versatile",  # Groq model ID
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt}
        ],
        temperature=0.3,
        max_tokens=3000
    )

    # ✅ Correct content access for Groq SDK
    return completion.choices[0].message.content.strip()

# -----------------------------
# 4️⃣  Main Script
# -----------------------------
if __name__ == "__main__":
    print("\n=== Zoom Transcript Enhancer (LLaMA 3.1 8B on Groq) ===\n")

    # Load transcript
    if os.path.exists("Meeting_Transcripts/T_M_13Oct.txt"):
        with open("Meeting_Transcripts/T_M_13Oct.txt", "r", encoding="utf-8") as f:
            raw_transcript = f.read().strip()
    else:
        print("No 'Meeting_Transcripts/T_M_13Oct.txt' found — please paste your transcript below.")
        raw_transcript = input("\nPaste raw transcript:\n")

    print("\nProcessing... Please wait...\n")
    improved_transcript = enhance_transcript(raw_transcript)

    # Output result
    print("=== Enhanced Transcript ===\n")
    print(improved_transcript)

    with open("E_T_M_13Oct_70B.txt", "w", encoding="utf-8") as f:
        f.write(improved_transcript)

    print("\n✅ Saved to 'E_T_M_13Oct_70B.txt'\n")
