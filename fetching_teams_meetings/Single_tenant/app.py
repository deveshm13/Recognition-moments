from flask import Flask, redirect, url_for, session, request, send_file
import msal
import requests
import os
import urllib.parse
import logging
from dotenv import load_dotenv
import hashlib
import time
from io import BytesIO
from datetime import datetime, timedelta

# --------------------------------
# ENV SETUP
# --------------------------------
load_dotenv()
app = Flask(__name__)
app.secret_key = os.urandom(24)

# Logging setup
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s [%(levelname)s] %(message)s")

CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
AUTHORITY = os.getenv("AUTHORITY")  # e.g., https://login.microsoftonline.com/<tenant_id>
REDIRECT_PATH = os.getenv("REDIRECT_PATH", "/getAToken")
USER_EMAIL = os.getenv("USER_EMAIL")  # Add this to .env (e.g. devesh.mishra@6fdxfc.onmicrosoft.com)
SCOPE = [
    "User.Read",
    "Calendars.Read",
    "OnlineMeetingTranscript.Read.All",
    "OnlineMeetings.Read",
    "OnlineMeetings.ReadWrite"
]
GRAPH_API_ENDPOINT = "https://graph.microsoft.com/v1.0"

# --------------------------------
# MSAL HELPERS
# --------------------------------
def _build_msal_app(cache=None):
    return msal.ConfidentialClientApplication(
        CLIENT_ID,
        authority=AUTHORITY,
        client_credential=CLIENT_SECRET,
        token_cache=cache
    )

def _build_auth_url():
    return _build_msal_app().get_authorization_request_url(
        scopes=SCOPE,
        redirect_uri=url_for("authorized", _external=True)
    )

def _get_token_from_cache():
    return session.get("access_token")

# --------------------------------
# ROUTES
# --------------------------------
@app.route("/")
def index():
    if not session.get("user"):
        return '<a href="/login">Sign in with Microsoft</a>'
    return f"""
    <h2>Welcome, {session['user']['name']}</h2>
    <p><a href="/fetch_meetings">📅 View My Teams Calendar Meetings</a></p>
    <a href="/logout">Logout</a>
    """

@app.route("/login")
def login():
    return redirect(_build_auth_url())

@app.route(REDIRECT_PATH)
def authorized():
    code = request.args.get("code")
    if not code:
        return "Login failed or canceled."

    result = _build_msal_app().acquire_token_by_authorization_code(
        code,
        scopes=SCOPE,
        redirect_uri=url_for("authorized", _external=True)
    )

    if "error" in result:
        return f"Login error: {result.get('error_description')}"

    session["user"] = result.get("id_token_claims")
    session["access_token"] = result["access_token"]
    return redirect(url_for("index"))

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))

# --------------------------------
# NEW: Fetch meetings from /calendar/events
# --------------------------------
@app.route("/fetch_meetings")
def fetch_meetings():
    token = _get_token_from_cache()
    if not token:
        return redirect(url_for("login"))

    headers = {"Authorization": f"Bearer {token}"}
    start = (datetime.utcnow() - timedelta(days=180)).isoformat() + "Z"
    end = (datetime.utcnow() + timedelta(days=180)).isoformat() + "Z"
    events_url = f"{GRAPH_API_ENDPOINT}/me/calendarView?startDateTime={start}&endDateTime={end}&$top=100"
    logging.info(f"📅 Fetching calendar events via {events_url}")

    resp = requests.get(events_url, headers=headers)
    # print(resp.status_code, resp.text)
    if resp.status_code != 200:
        return f"❌ Error fetching calendar events: {resp.text}"

    events = resp.json().get("value", [])
    print(events)
    if not events:
        return "<h3>⚠️ No calendar events found for this user.</h3>"

    html = "<h2>📅 Your Calendar Meetings</h2><ul>"
    for e in events:
        subject = e.get("subject", "Untitled Meeting")
        start_time = e.get("start", {}).get("dateTime", "N/A")
        online_meeting = e.get("onlineMeeting", {})
        # print(online_meeting)
        join_url = online_meeting.get("joinUrl")

        # Some events have join URL directly
        if not join_url and "body" in e and "content" in e["body"]:
            # fallback: find a teams link in the body content
            import re
            match = re.search(r"https://teams\.microsoft\.com/l/meetup-join/[^\s<]+", e["body"]["content"])
            join_url = match.group(0) if match else None

        if join_url:
            html += f"<li><b>{subject}</b> ({start_time})<br>"
            html += f"<a href='/get_meeting_transcript?joinurl={urllib.parse.quote(join_url)}'>🎙️ Get Transcript</a></li><br>"

    html += "</ul>"
    if html == "<h2>📅 Your Calendar Meetings</h2><ul></ul>":
        html += "<p>⚠️ No Teams meeting links found in your calendar events.</p>"
    return html

# --------------------------------
# Meeting → Transcript (same logic)
# --------------------------------
@app.route("/get_meeting_transcript")
def get_meeting_transcript():
    token = _get_token_from_cache()
    if not token:
        return redirect(url_for("login"))

    join_url = request.args.get("joinurl")
    if not join_url:
        return "⚠️ Missing 'joinurl' parameter."

    encoded_url = join_url.replace("'", "%27")
    meetings_url = f"{GRAPH_API_ENDPOINT}/me/onlineMeetings?$filter=JoinWebUrl eq '{encoded_url}'"
    headers = {"Authorization": f"Bearer {token}"}

    logging.info(f"🔍 Fetching meeting via: {meetings_url}")
    resp = requests.get(meetings_url, headers=headers)

    if resp.status_code != 200:
        return f"❌ Error fetching meetings: {resp.text}"

    meetings = resp.json().get("value", [])
    if not meetings:
        return "⚠️ No meetings found for the provided JoinWebUrl."

    meeting = meetings[0]
    meeting_id = meeting.get("id")
    logging.info(f"✅ Found Meeting ID: {meeting_id}")

    # Step 2: Get transcripts
    transcripts_url = f"{GRAPH_API_ENDPOINT}/me/onlineMeetings/{meeting_id}/transcripts"
    trans_resp = requests.get(transcripts_url, headers=headers)

    if trans_resp.status_code != 200:
        return f"❌ Error fetching transcripts: {trans_resp.text}"

    transcripts = trans_resp.json().get("value", [])
    if not transcripts:
        return "⚠️ No transcripts found for this meeting."

    transcript_id = transcripts[0].get("id")
    logging.info(f"🧾 Found Transcript ID: {transcript_id}")

    # Step 3: Download transcript content
    user_id = session["user"].get("oid")
    content_url = (
        f"{GRAPH_API_ENDPOINT}/users/{user_id}/onlineMeetings/"
        f"{meeting_id}/transcripts/{transcript_id}/content"
    )
    headers["Accept"] = "text/vtt"
    content_resp = requests.get(content_url, headers=headers)

    if content_resp.status_code == 200 and content_resp.content:
        short_name = hashlib.sha1((meeting_id + transcript_id).encode()).hexdigest()[:10]
        timestamp = int(time.time())
        safe_filename = f"transcript_{short_name}_{timestamp}.vtt"

        return send_file(
            BytesIO(content_resp.content),
            as_attachment=True,
            download_name=safe_filename,
            mimetype="text/vtt"
        )

    return f"⚠️ Failed to fetch transcript content: {content_resp.text}"

# --------------------------------
# Run App
# --------------------------------
if __name__ == "__main__":
    app.run(debug=True, port=5000)
