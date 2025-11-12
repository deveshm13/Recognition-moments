import os
import re
import requests
import urllib.parse
from flask import Flask, request, redirect, session, url_for
from pathlib import Path
import msal

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET", "replace_me")

# Azure credentials
CLIENT_ID = os.getenv("AZURE_CLIENT_ID", "a41a076d-abfc-4d60-8eb6-ee6c36fde3ac")
CLIENT_SECRET = os.getenv("AZURE_CLIENT_SECRET", "2798Q~NoyMJiryz6eH5egDkh2VDvyJn-R_UmrbjT")
AUTHORITY = "https://login.microsoftonline.com/common"
REDIRECT_PATH = "/getAToken"

SCOPES = [
    "User.Read",
    "Chat.Read",
    "Chat.Read.All",
    "OnlineMeetingTranscript.Read.All",
    "OnlineMeetingRecording.Read.All",
    "Files.Read.All",
]

GRAPH_API_ENDPOINT = "https://graph.microsoft.com/v1.0"
DOWNLOAD_DIR = Path("downloads")
DOWNLOAD_DIR.mkdir(exist_ok=True)

# ---------------- MSAL helpers ----------------
def build_msal_app(cache=None):
    return msal.ConfidentialClientApplication(
        CLIENT_ID, authority=AUTHORITY, client_credential=CLIENT_SECRET, token_cache=cache
    )

def get_token():
    return session.get("token")

# ---------------- ROUTES ----------------
@app.route("/")
def index():
    if not session.get("user"):
        return '<a href="/login">Sign in with Microsoft</a>'
    return f"""
    <h3>Welcome {session['user']['name']}</h3>
    <a href='/meetings'>View Teams Meetings</a><br>
    <a href='/recordings'>Fetch Meeting Recordings + Transcripts</a><br>
    <a href='/logout'>Logout</a>
    """

@app.route("/login")
def login():
    msal_app = build_msal_app()
    auth_url = msal_app.get_authorization_request_url(SCOPES, redirect_uri=url_for("authorized", _external=True))
    return redirect(auth_url)

@app.route(REDIRECT_PATH)
def authorized():
    code = request.args.get("code")
    msal_app = build_msal_app()
    result = msal_app.acquire_token_by_authorization_code(
        code,
        scopes=SCOPES,
        redirect_uri=url_for("authorized", _external=True)
    )
    if "access_token" in result:
        session["user"] = result.get("id_token_claims")
        session["token"] = result["access_token"]
        return redirect(url_for("meetings"))
    return f"Login failed: {result.get('error_description')}"

@app.route("/meetings")
def meetings():
    token = get_token()
    if not token:
        return redirect(url_for("login"))
    headers = {"Authorization": f"Bearer {token}"}
    url = f"{GRAPH_API_ENDPOINT}/me/events?$orderby=start/dateTime desc&$top=20"
    resp = requests.get(url, headers=headers)

    if resp.status_code != 200:
        return f"Error fetching meetings: <pre>{resp.text}</pre>"

    events = resp.json().get("value", [])
    meetings = [e for e in events if e.get("onlineMeeting")]

    if not meetings:
        return "<h3>No Teams meetings found.</h3>"

    html = "<h3>📅 Your Teams Meetings:</h3><ul>"
    for m in meetings:
        subject = m.get("subject", "Untitled")
        join_url = m["onlineMeeting"].get("joinUrl", "")
        chat_info = m["onlineMeeting"].get("chatInfo", {})
        thread_id = chat_info.get("threadId", "")
        html += f"<li><b>{subject}</b><br>"
        html += f"🧵 Chat ID: {thread_id or 'N/A'}<br>"
        html += f"🔗 <a href='{join_url}' target='_blank'>Join</a><br>"
        if thread_id:
            html += f"🎬 <a href='/chat_recordings?chat_id={urllib.parse.quote(thread_id)}'>View Recording / Transcript</a>"
        html += "</li><br>"
    html += "</ul>"
    return html

@app.route("/chat_recordings")
def chat_recordings():
    """Fetch callRecording URLs and directly download .vtt transcript"""
    token = get_token()
    if not token:
        return redirect(url_for("login"))

    chat_id = request.args.get("chat_id")
    if not chat_id:
        return "<p>❌ Missing chat_id</p>"

    headers = {"Authorization": f"Bearer {token}"}
    chat_url = f"{GRAPH_API_ENDPOINT}/chats/{urllib.parse.quote(chat_id)}/messages"

    resp = requests.get(chat_url, headers=headers)
    if resp.status_code != 200:
        return f"<p>❌ Failed to fetch messages: {resp.text}</p>"

    messages = resp.json().get("value", [])
    output = f"<h3>🎞️ Recordings & Transcripts for Chat {chat_id}</h3>"

    if not messages:
        return output + "<p>No chat messages found.</p>"

    for msg in messages:
        event = msg.get("eventDetail")
        if event and "#microsoft.graph.callRecordingEventMessageDetail" in event.get("@odata.type", ""):
            rec_name = event.get("callRecordingDisplayName", "Unknown")
            rec_url = event.get("callRecordingUrl")
            duration = event.get("callRecordingDuration", "N/A")
            output += f"<hr><b>🎥 {rec_name}</b><br>"
            output += f"🕓 Duration: {duration}<br>"
            output += f"🔗 Recording: <a href='{rec_url}' target='_blank'>{rec_url}</a><br>"

            # Fetch the .vtt directly via redirect
            try:
                with requests.get(rec_url, allow_redirects=True, stream=True) as r:
                    if r.status_code == 200:
                        # Look for .vtt file in content-disposition
                        cd = r.headers.get("content-disposition", "")
                        match = re.search(r'filename="(.+\.vtt)"', cd)
                        vtt_name = match.group(1) if match else rec_name.replace(".mp4", ".vtt")
                        local_path = DOWNLOAD_DIR / vtt_name
                        with open(local_path, "wb") as f:
                            for chunk in r.iter_content(8192):
                                f.write(chunk)
                        output += f"📝 Transcript downloaded: {local_path}<br>"
                    else:
                        output += f"⚠️ Could not download transcript (HTTP {r.status_code})<br>"
            except Exception as e:
                output += f"❌ Error downloading transcript: {e}<br>"

    return output

@app.route("/recordings")
def recordings_overview():
    token = get_token()
    if not token:
        return redirect(url_for("login"))

    headers = {"Authorization": f"Bearer {token}"}
    chats_url = f"{GRAPH_API_ENDPOINT}/me/chats?$top=20"
    resp = requests.get(chats_url, headers=headers)

    if resp.status_code != 200:
        return f"Error fetching chats: {resp.text}"

    chats = resp.json().get("value", [])
    html = "<h3>💬 Your Chat Threads (meetings likely appear here):</h3><ul>"
    for c in chats:
        topic = c.get("topic", "No Title")
        chat_id = c.get("id")
        html += f"<li><b>{topic}</b><br>"
        html += f"🧵 Chat ID: {chat_id}<br>"
        html += f"<a href='/chat_recordings?chat_id={urllib.parse.quote(chat_id)}'>Inspect Recordings</a></li><br>"
    html += "</ul>"
    return html

@app.route("/logout")
def logout():
    session.clear()
    logout_url = (
        "https://login.microsoftonline.com/common/oauth2/v2.0/logout"
        "?post_logout_redirect_uri=http://127.0.0.1:5000/"
    )
    code = request.args.get("code")
    msal_app = build_msal_app()
    result = msal_app.acquire_token_by_authorization_code(
        code,
        scopes=SCOPES,
        redirect_uri=url_for("authorized", _external=True)
    )
    if "access_token" in result:
        session["user"] = result.get("id_token_claims")
        session["token"] = result["access_token"]
        return redirect(url_for("meetings"))
    return f"Login failed: {result.get('error_description')}"
    return redirect(logout_url)

if __name__ == "__main__":
    app.run(debug=True, port=5000)
