import streamlit as st
import json
import os
import re
import logging
from datetime import datetime, timedelta
import requests
import msal
from dotenv import load_dotenv


# -------------------------------
# CONFIG
# -------------------------------
load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
REDIRECT_URI = os.getenv("REDIRECT_URI", "http://localhost:8501")
AUTHORITY = os.getenv("AUTHORITY", "https://login.microsoftonline.com/common")
GRAPH_API = os.getenv("GRAPH_API", "https://graph.microsoft.com/v1.0")

TENANTS_FILE = "tenants.json"
TRANSCRIPTS_FILE = "meeting_transcripts.json"

# -------------------------------
# HELPERS
# -------------------------------
def load_json(file):
    if os.path.exists(file):
        with open(file) as f:
            return json.load(f)
    return {}

def save_json(file, data):
    with open(file, "w") as f:
        json.dump(data, f, indent=2)

def onboard_tenant(tenant_id):
    tenants_data = load_json(TENANTS_FILE)
    tenants = tenants_data.get("tenants", [])
    if tenant_id not in tenants:
        tenants.append(tenant_id)
        tenants_data["tenants"] = tenants
        save_json(TENANTS_FILE, tenants_data)
        logging.info(f"✅ Tenant onboarded: {tenant_id}")
        return True
    return False

def generate_admin_consent_url():
    return (
        f"https://login.microsoftonline.com/common/adminconsent"
        f"?client_id={CLIENT_ID}"
        f"&redirect_uri={REDIRECT_URI}"
    )

def _build_msal_app(authority=None):
    return msal.ConfidentialClientApplication(
        CLIENT_ID,
        authority=authority or AUTHORITY,
        client_credential=CLIENT_SECRET,
    )

def get_app_token_for_tenant(tenant_id):
    app_instance = _build_msal_app(f"https://login.microsoftonline.com/{tenant_id}")
    result = app_instance.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])
    print(result)
    if "access_token" in result:
        return result["access_token"]
    return None

def parse_vtt(vtt_text):
    pattern = r"(\d{2}:\d{2}:\d{2}\.\d{3}) --> (\d{2}:\d{2}:\d{2}\.\d{3})\r?\n<v ([^>]+)>(.*?)</v>"
    entries = re.findall(pattern, vtt_text, flags=re.DOTALL)
    return [
        {"start": s, "end": e, "speaker": speaker.strip(), "text": text.strip()}
        for s, e, speaker, text in entries
    ]

# -------------------------------
# FETCH MEETINGS (Streamlit Version)
# -------------------------------
def fetch_all_tenant_meetings():
    tenants = load_json(TENANTS_FILE).get("tenants", [])
    if not tenants:
        st.error("⚠️ No tenants onboarded yet!")
        return None

    transcripts_store = load_json(TRANSCRIPTS_FILE)
    final_output = []

    for tenant_id in tenants:
        st.info(f"Fetching meetings for tenant: {tenant_id}")
        token = get_app_token_for_tenant(tenant_id)
        if not token:
            st.warning(f"❌ No valid token for tenant {tenant_id}")
            continue

        headers = {"Authorization": f"Bearer {token}"}

        # -------------------------------
        # STEP 1 — FETCH USERS (LIVE)
        # -------------------------------
        users_resp = requests.get(f"{GRAPH_API}/users?$select=id,displayName,mail", headers=headers)
        if users_resp.status_code != 200:
            st.error(f"Failed to fetch users for tenant {tenant_id}: {users_resp.text}")
            continue
        tenant_users = users_resp.json().get("value", [])

        # -------------------------------
        # STEP 2 — FETCH MEETINGS (LAST 2 DAYS)
        # -------------------------------
        for user in tenant_users:
            uid = user["id"]
            uname = user.get("displayName", "Unknown User")
            mail = user.get("mail", "N/A")

            end = datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
            start = (datetime.utcnow() - timedelta(days=8)).replace(microsecond=0).isoformat() + "Z"

            cal_url = f"{GRAPH_API}/users/{uid}/calendarView?startDateTime={start}&endDateTime={end}"
            meet_resp = requests.get(cal_url, headers=headers)

            # if meet_resp.status_code != 200:
            #     st.warning(f"⚠️ Failed to fetch meetings for {uname}: {meet_resp.text}")
            #     continue

            events = meet_resp.json().get("value", [])

            for e in events:
                organizer_info = e.get("organizer", {}).get("emailAddress", {})
                organizer_email = organizer_info.get("address", "")
                if organizer_email.lower() != mail.lower():
                    continue  # Only process meetings this user organized

                subject = e.get("subject", "Untitled Meeting")
                start_time = e.get("start", {}).get("dateTime", "N/A")
                meeting_id = e.get("id")
                join_url = e.get("onlineMeeting", {}).get("joinUrl")

                if not join_url:
                    continue

                # Skip if already stored
                if any(m.get("meeting_id") == meeting_id for m in transcripts_store.get(tenant_id, [])):
                    st.info(f"Skipping already saved meeting: {subject}")
                    continue

                # -------------------------------
                # STEP 3 — ORGANIZER + ATTENDEES
                # -------------------------------
                organizer_entry = {
                    "name": organizer_info.get("name", uname),
                    "email": organizer_email or mail,
                    "role": "organizer"
                }

                attendee_entries = [
                    {
                        "name": a.get("emailAddress", {}).get("name", "Unknown"),
                        "email": a.get("emailAddress", {}).get("address", "Unknown"),
                        "role": a.get("type", "attendee").lower()
                    }
                    for a in e.get("attendees", [])
                ]
                attendees = [organizer_entry] + attendee_entries

                # -------------------------------
                # STEP 4 — TRANSCRIPTS LOOKUP
                # -------------------------------
                encoded_url = join_url.replace("'", "%27")
                lookup_url = f"{GRAPH_API}/users/{uid}/onlineMeetings?$filter=JoinWebUrl eq '{encoded_url}'"
                lookup_resp = requests.get(lookup_url, headers=headers)

                if lookup_resp.status_code != 200:
                    continue
                found = lookup_resp.json().get("value", [])
                if not found:
                    continue

                actual_meeting_id = found[0].get("id")
                trans_url = f"{GRAPH_API}/users/{uid}/onlineMeetings/{actual_meeting_id}/transcripts"
                trans_resp = requests.get(trans_url, headers=headers)

                if trans_resp.status_code != 200:
                    continue

                transcripts = trans_resp.json().get("value", [])
                merged_transcript = []

                for t in transcripts:
                    tid = t.get("id")
                    content_url = f"{GRAPH_API}/users/{uid}/onlineMeetings/{actual_meeting_id}/transcripts/{tid}/content"
                    content_resp = requests.get(content_url, headers={**headers, "Accept": "text/vtt"})

                    if content_resp.status_code == 200 and content_resp.text:
                        parsed_content = parse_vtt(content_resp.text)
                        if parsed_content:
                            merged_transcript.extend(parsed_content)
                    else:
                        st.warning(f"Failed to fetch transcript content for meeting: {subject}")

                if not merged_transcript:
                    st.info(f"No transcript found for meeting: {subject}")
                    continue

                # Sort transcript by start time
                def time_to_seconds(t):
                    try:
                        h, m, s = t.split(":")
                        return int(h)*3600 + int(m)*60 + float(s)
                    except:
                        return 0.0

                merged_transcript.sort(key=lambda x: time_to_seconds(x.get("start", "00:00:00.000")))

                # -------------------------------
                # STEP 5 — SAVE MEETING ENTRY
                # -------------------------------
                transcripts_store.setdefault(tenant_id, []).append({
                    "tenant_id": tenant_id,
                    "Organiser_name": uname,
                    "Organiser_mail": mail,
                    "subject": subject,
                    "meeting_id": meeting_id,
                    "start_time": start_time,
                    "attendees": attendees,
                    "meeting_transcript": merged_transcript
                })

                save_json(TRANSCRIPTS_FILE, transcripts_store)

                final_output.append({
                    "tenant_id": tenant_id,
                    "Organiser_name": uname,
                    "Organiser_mail": mail,
                    "subject": subject,
                    "attendee_count": len(attendees)
                })

    save_json(TRANSCRIPTS_FILE, transcripts_store)
    return final_output


# -------------------------------
# STREAMLIT UI WITH EXTENDED TABS
# -------------------------------
st.set_page_config(page_title="Tenant Management Dashboard", page_icon="🏢", layout="wide")
st.title("🏢 Fetching Relevant Recognition moments from Microsoft Teams meetings")

tabs = st.tabs(["🧩 Tenant Onboarding", "📅 Fetch Meetings", "🗒️ View Transcripts", "🏆 Recognition Moments"])

# ================================================================
# TAB 1: Tenant Onboarding
# ================================================================
with tabs[0]:
    st.subheader("Tenant Onboarding via Admin Consent")

    query_params = st.query_params.to_dict() if hasattr(st, "query_params") else {}
    tenant_id = query_params.get("tenant")
    admin_consent = query_params.get("admin_consent")

    if tenant_id and admin_consent and admin_consent.lower() == "true":
        st.write("🔄 Processing tenant onboarding callback...")
        if onboard_tenant(tenant_id):
            st.success(f"✅ Tenant {tenant_id} onboarded successfully!")
        else:
            st.info(f"ℹ️ Tenant {tenant_id} already onboarded.")
    else:
        consent_url = generate_admin_consent_url()
        st.markdown(
            f"""
            <h4>Step 1: Grant Admin Consent</h4>
            <p>Share this URL with your tenant admin to onboard:</p>
            <a href='{consent_url}' target='_blank'>{consent_url}</a>
            """,
            unsafe_allow_html=True
        )

    st.divider()
    tenants = load_json(TENANTS_FILE).get("tenants", [])
    st.subheader("✅ Onboarded Tenants")
    if tenants:
        st.json(tenants)
    else:
        st.info("No tenants onboarded yet.")

# ================================================================
# TAB 2: Fetch Meetings
# ================================================================
with tabs[1]:
    st.subheader("📅 Fetch Tenant Meetings and Transcripts")
    tenants = load_json(TENANTS_FILE).get("tenants", [])

    if not tenants:
        st.warning("No tenants onboarded yet. Please onboard a tenant first.")
    else:
        if st.button("🔄 Fetch Latest Meetings"):
            output = fetch_all_tenant_meetings()
            if output:
                st.success(f"Fetched meeting data for {len(output)} meetings.")
                st.json(output)
            else:
                st.info("No new meetings found in last 24 hours.")

# ================================================================
# TAB 3: View Stored Transcripts
# ================================================================
with tabs[2]:
    st.subheader("🗒️ Stored Meeting Transcripts")

    transcripts_data = load_json(TRANSCRIPTS_FILE)
    if not transcripts_data:
        st.info("No transcripts saved yet. Try fetching meetings first.")
    else:
        for tenant_id, meetings in transcripts_data.items():
            with st.expander(f"🏢 Tenant: {tenant_id} ({len(meetings)} meetings)"):
                for m in meetings:
                    st.markdown(f"### {m['subject']}")
                    st.markdown(f"👤 **Organizer:** {m['Organiser_name']} ({m['Organiser_mail']})")
                    st.markdown(f"🆔 **Meeting ID:** {m['meeting_id']}")
                    with st.expander("🗣️ Show Transcript"):
                        for entry in m["meeting_transcript"]:
                            st.write(f"**{entry['speaker']}** ({entry['start']} - {entry['end']}): {entry['text']}")

# ================================================================
# TAB 4: Recognition Moment Extraction
# ================================================================
with tabs[3]:
    st.subheader("🏆 Recognition Moment Extraction via Llama 3.3 70B")

    transcripts_data = load_json(TRANSCRIPTS_FILE)
    tenants = list(transcripts_data.keys()) if transcripts_data else []

    if not tenants:
        st.warning("⚠️ No tenants with transcripts found. Fetch meetings first.")
    else:
        tenant_choice = st.selectbox("Select Tenant", tenants)
        meeting_titles = [m["subject"] for m in transcripts_data[tenant_choice]]
        meeting_choice = st.selectbox("Select Meeting", meeting_titles)

        selected_meeting = next((m for m in transcripts_data[tenant_choice] if m["subject"] == meeting_choice), None)
        # print(selected_meeting)

        if selected_meeting:
            st.markdown(f"**Organizer:** {selected_meeting['Organiser_name']} ({selected_meeting['Organiser_mail']})")

            if st.button("🎯 Get Recognition Insights"):
                with st.spinner("Analyzing transcript with Bedrock Llama 3.3... ⏳"):
                    # Prepare transcript text
                    transcript_text = "\n".join(
                        [f"{seg['speaker']}: {seg['text']}" for seg in selected_meeting["meeting_transcript"]]
                    )

                    # print(transcript_text)

                    # If attendees are present
                    attendees = selected_meeting.get("attendees", [])
                    attendance_text = "\n".join(
                        [f"{a['name']} ({a.get('role', 'N/A')}) — {a.get('email', 'N/A')}" for a in attendees]
                    )

                    # print(attendance_text)

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

                    ### STRICT NOTE 
                    # If the transcript is in French, Hindi, Spanish, German or so on then, the values should be in the same language but the keys should strictly be in English.
                    Example 1:
                    ```json
                    {
                    "meeting_context": "स्ट्रिंग",
                        "participants": {
                        "Dhawal Bajaj": {
                            "Reason": "मजबूत नेतृत्व का प्रदर्शन किया और तकनीकी दिशा प्रदान की",
                            "Summary": "डेटाबेस अनुकूलन रणनीति को सरल बनाकर और सर्वोत्तम प्रथाओं को अनुक्रमित करने पर टीम का मार्गदर्शन किया",
                            "Overall score": 90
                        }
                        }
                    }
                    Example 2:
                    {
                        "meeting_context": "Reunión de coordinación de procesos DevOps y Cloud",
                        "participants": {
                        "Anna Weber": {
                            "Reason": "Liderazgo demostrado al coordinar la reunión y guiar la discusión sobre la optimización de los procesos DevOps y Cloud",
                            "Summary": "Dirigió la reunión, resumió los objetivos y aseguró que se abordaran los temas clave",
                            "Overall score": 90
                        }
                        }
                    }
                    ```json
                    """

                    # -----------------------------
                    # Combined prompt
                    # -----------------------------
                    combined_prompt = f"""
                    {SYSTEM_PROMPT}

                    Attendance JSON:
                    {json.dumps(attendance_text, indent=2)}

                    Transcript:
                    {transcript_text}

                    Now generate the structured recognition output as valid JSON.
                    Respond with exactly one JSON object.
                    Do not repeat, rephrase, or surround it with LaTeX, markdown, or explanations.
                    """

                    import time, json, datetime, re, os
                    import requests
                    AZURE_OPENAI_URL = os.getenv("AZURE_OPENAI_URL")
                    AZURE_OPENAI_KEY = os.getenv("AZURE_OPENAI_KEY")

                    headers = {
                        "Content-Type": "application/json",
                        "api-key": AZURE_OPENAI_KEY
                    }

                    payload = {
                        "messages": [
                            {"role": "user", "content": combined_prompt}
                        ],
                        "temperature": 0.2,
                        "top_p": 0.9,
                        "max_tokens": 8192
                    }

                    # -------------------------------
                    # Call Azure OpenAI
                    # -------------------------------
                    start = time.time()

                    try:
                        response = requests.post(
                            AZURE_OPENAI_URL,
                            headers=headers,
                            data=json.dumps(payload)
                        )
                        end = time.time()

                        if response.status_code != 200:
                            st.error(f"Azure error: {response.text}")
                            raise Exception(response.text)

                        response_json = response.json()

                        # -----------------------------
                        # Extract model output
                        # -----------------------------
                        raw_output = response_json["choices"][0]["message"]["content"]

                        # Azure token fields
                        usage = response_json.get("usage", {})
                        input_tokens = usage.get("prompt_tokens", "N/A")
                        output_tokens = usage.get("completion_tokens", "N/A")

                        # Metrics
                        latency = end - start
                        cost_per_meeting = (input_tokens / 1000) * 0.0000011+ (output_tokens / 1000) * 0.0000044

                        # -----------------------------
                        # Extract clean JSON from model output
                        # -----------------------------
                        match = re.search(r"\{[\s\S]*\}", raw_output)
                        if match:
                            final_json = json.loads(match.group(0))

                            st.success("✅ Recognition insights extracted successfully!")
                            st.json(final_json)

                            st.json({
                                "input_tokens": input_tokens,
                                "output_tokens": output_tokens,
                                "latency_seconds": f"{latency:.2f}s",
                                "cost_per_meeting": f"${cost_per_meeting:.4f}"
                            })

                        else:
                            st.warning("No valid JSON found in model output.")
                            st.text(raw_output)

                    except Exception as e:
                        st.error(f"Error: {str(e)}")
