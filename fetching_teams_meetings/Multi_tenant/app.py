import os
import json
import logging
from flask import Flask, redirect, session, request, jsonify
from dotenv import load_dotenv
import msal
import requests
from datetime import datetime, timedelta
import re

# -------------------------------
# ENV + LOGGING SETUP
# -------------------------------
load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

app = Flask(__name__)
app.secret_key = os.urandom(24)

CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
REDIRECT_URI = os.getenv("REDIRECT_URI")
AUTHORITY = os.getenv("AUTHORITY", "https://login.microsoftonline.com/common")
GRAPH_API = os.getenv("GRAPH_API", "https://graph.microsoft.com/v1.0")

TENANTS_FILE = "tenants.json"
USERS_FILE = "users.json"
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

def parse_vtt(vtt_text):
    """Parses VTT caption text into structured JSON."""
    pattern = r"(\d{2}:\d{2}:\d{2}\.\d{3}) --> (\d{2}:\d{2}:\d{2}\.\d{3})\r?\n<v ([^>]+)>(.*?)</v>"
    entries = re.findall(pattern, vtt_text, flags=re.DOTALL)
    return [
        {"start": s, "end": e, "speaker": speaker.strip(), "text": text.strip()}
        for s, e, speaker, text in entries
    ]

# -------------------------------
# MSAL APP BUILDERS
# -------------------------------
def _build_msal_app(authority=None):
    return msal.ConfidentialClientApplication(
        CLIENT_ID,
        authority=authority or AUTHORITY,
        client_credential=CLIENT_SECRET,
    )

def get_app_token_for_tenant(tenant_id):
    """Get an app-only token for a specific tenant."""
    app_instance = _build_msal_app(f"https://login.microsoftonline.com/{tenant_id}")
    result = app_instance.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])
    if "access_token" in result:
        logging.info(f"Token acquired for tenant {tenant_id}")
        return result["access_token"]
    logging.error(f"Failed to get token for {tenant_id}: {result}")
    return None

# -------------------------------
# ROUTE: Admin Consent
# -------------------------------
@app.route("/admin_consent")
def admin_consent():
    consent_url = (
        f"https://login.microsoftonline.com/common/adminconsent"
        f"?client_id={CLIENT_ID}"
        f"&redirect_uri={REDIRECT_URI}"
    )
    return f"<h3>Admin Consent</h3><p>Share this URL with tenant admins:</p><a href='{consent_url}'>{consent_url}</a>"

# -------------------------------
# ROUTE: Callback after consent
# -------------------------------
@app.route("/consent_return")
def consent_return():
    tenant_id = request.args.get("tenant")
    if not tenant_id:
        return "No tenant ID returned."

    tenants_data = load_json(TENANTS_FILE)
    tenants = tenants_data.get("tenants", [])

    if tenant_id not in tenants:
        tenants.append(tenant_id)
        tenants_data["tenants"] = tenants
        save_json(TENANTS_FILE, tenants_data)
        logging.info(f"Tenant onboarded: {tenant_id}")

    return f"<h3>Tenant {tenant_id} onboarded successfully!</h3>"

# -------------------------------
# ROUTE: List onboarded tenants
# -------------------------------
@app.route("/tenants")
def list_tenants():
    tenants = load_json(TENANTS_FILE).get("tenants", [])
    if not tenants:
        return "<h3>No tenants onboarded yet.</h3>"
    html = "<h3>Onboarded Tenants</h3><ul>"
    for t in tenants:
        html += f"<li>{t}</li>"
    html += "</ul>"
    return html

# -------------------------------
# ROUTE: Fetch meetings + transcripts
# -------------------------------
@app.route("/fetch_all_tenant_meetings")
def fetch_all_tenant_meetings():
    tenants = load_json(TENANTS_FILE).get("tenants", [])
    if not tenants:
        return jsonify({"error": "No tenants onboarded yet"}), 400

    users_store = load_json(USERS_FILE)
    transcripts_store = load_json(TRANSCRIPTS_FILE)

    final_output = []

    for tenant_id in tenants:
        logging.info(f"Processing tenant: {tenant_id}")
        token = get_app_token_for_tenant(tenant_id)
        if not token:
            continue
        headers = {"Authorization": f"Bearer {token}"}

        # -------------------------------
        # STEP 1 — FETCH USERS
        # -------------------------------
        tenant_users = users_store.get(tenant_id, [])
        if not tenant_users:
            logging.info(f"📥 Fetching users for tenant {tenant_id}...")
            users_resp = requests.get(f"{GRAPH_API}/users?$select=id,displayName,mail", headers=headers)
            if users_resp.status_code != 200:
                logging.error(f"Failed to fetch users: {users_resp.text}")
                continue
            tenant_users = users_resp.json().get("value", [])
            users_store[tenant_id] = tenant_users
            save_json(USERS_FILE, users_store)
        else:
            logging.info(f"Loaded {len(tenant_users)} users from cache.")

        # -------------------------------
        # STEP 2 — FETCH MEETINGS (LAST 1 DAY)
        # -------------------------------
        for user in tenant_users:
            uid = user["id"]
            uname = user.get("displayName", "Unknown User")
            mail = user.get("mail", "N/A")

            end = datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
            start = (datetime.utcnow() - timedelta(days=1)).replace(microsecond=0).isoformat() + "Z"

            cal_url = f"{GRAPH_API}/users/{uid}/calendarView?startDateTime={start}&endDateTime={end}"
            meet_resp = requests.get(cal_url, headers=headers)

            if meet_resp.status_code != 200:
                logging.warning(f"⚠️ Failed to fetch meetings for {uname}: {meet_resp.text}")
                continue

            events = meet_resp.json().get("value", [])
            user_meetings = []

            for e in events:
                organizer_info = e.get("organizer", {}).get("emailAddress", {})
                organizer_email = organizer_info.get("address", "")
                if organizer_email.lower() != mail.lower():
                    continue  # only meetings organized by this user

                subject = e.get("subject", "Untitled Meeting")
                start_time = e.get("start", {}).get("dateTime", "N/A")
                meeting_id = e.get("id")
                join_url = e.get("onlineMeeting", {}).get("joinUrl")

                # ✅ Skip if already stored
                existing_meetings = transcripts_store.get(tenant_id, [])
                if any(m.get("meeting_id") == meeting_id for m in existing_meetings):
                    logging.info(f"⏩ Skipping already saved meeting {subject}")
                    continue

                # ✅ Include organizer + attendees
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

                meeting_data = {
                    "meeting_id": meeting_id,
                    "subject": subject,
                    "start_time": start_time,
                    "attendees": attendees,
                    "join_url": join_url,
                    "transcripts": []
                }

                # -------------------------------
                # STEP 3 — TRANSCRIPTS LOOKUP
                # -------------------------------
                if join_url:
                    encoded_url = join_url.replace("'", "%27")
                    meeting_lookup_url = f"{GRAPH_API}/users/{uid}/onlineMeetings?$filter=JoinWebUrl eq '{encoded_url}'"
                    meet_lookup_resp = requests.get(meeting_lookup_url, headers=headers)

                    if meet_lookup_resp.status_code == 200:
                        meetings_found = meet_lookup_resp.json().get("value", [])
                        if meetings_found:
                            actual_meeting_id = meetings_found[0].get("id")

                            transcripts_url = f"{GRAPH_API}/users/{uid}/onlineMeetings/{actual_meeting_id}/transcripts"
                            trans_resp = requests.get(transcripts_url, headers=headers)

                            if trans_resp.status_code == 200:
                                transcripts = trans_resp.json().get("value", [])

                                merged_transcript = []  # 🧩 To store all transcript segments together

                                for t in transcripts:
                                    tid = t.get("id")
                                    content_url = f"{GRAPH_API}/users/{uid}/onlineMeetings/{actual_meeting_id}/transcripts/{tid}/content"
                                    content_resp = requests.get(content_url, headers={**headers, "Accept": "text/vtt"})

                                    if content_resp.status_code == 200 and content_resp.text:
                                        parsed_content = parse_vtt(content_resp.text)
                                        if parsed_content:  # ✅ Only add if transcript not empty
                                            merged_transcript.extend(parsed_content)
                                    else:
                                        logging.warning(f"⚠️ Failed to fetch transcript content for {subject}")

                                # 🧠 Sort merged transcript by start timestamp (chronologically)
                                def time_to_seconds(t):
                                    try:
                                        h, m, s = t.split(":")
                                        return int(h) * 3600 + int(m) * 60 + float(s)
                                    except:
                                        return 0.0

                                merged_transcript.sort(key=lambda x: time_to_seconds(x.get("start", "00:00:00.000")))

                                # 🧩 Skip this meeting entirely if transcript is empty
                                if not merged_transcript:
                                    logging.info(f"🚫 Skipping meeting '{subject}' — no transcript data found.")
                                else:
                                    # ✅ Store merged transcript
                                    meeting_data["transcripts"] = merged_transcript

                                    # ✅ Save persistently (merge if meeting already exists)
                                    existing_meetings = transcripts_store.get(tenant_id, [])
                                    existing_meeting = next(
                                        (m for m in existing_meetings if m.get("meeting_id") == meeting_id),
                                        None
                                    )

                                    if existing_meeting:
                                        existing_meeting["meeting_transcript"].extend(merged_transcript)
                                        existing_meeting["meeting_transcript"].sort(
                                            key=lambda x: time_to_seconds(x.get("start", "00:00:00.000"))
                                        )
                                        logging.info(f"🧩 Merged multiple transcripts for meeting {subject}")
                                    else:
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

                                    # ✅ Add to user_meetings only if transcript is valid
                                    user_meetings.append(meeting_data)

                # ✅ Append to final output only if user_meetings contain valid data
                if user_meetings:
                    final_output.append({
                        "tenant_id": tenant_id,
                        "Organiser_name": uname,
                        "Organiser_mail": mail,
                        "meetings": user_meetings
                    })



    save_json(TRANSCRIPTS_FILE, transcripts_store)
    return jsonify(final_output)


@app.route("/logout")
def logout():
    session.clear()
    logout_url = (
        "https://login.microsoftonline.com/common/oauth2/v2.0/logout"
        "?post_logout_redirect_uri=http://127.0.0.1:5000/"
    )
    return redirect(logout_url)

# -------------------------------
# MAIN APP ENTRY
# -------------------------------
if __name__ == "__main__":
    app.run(port=5000, debug=True)
