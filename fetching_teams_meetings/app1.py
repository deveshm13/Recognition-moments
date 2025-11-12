# app_diagnose_transcripts.py
import os
import json
import urllib.parse
from flask import Flask, redirect, session, url_for, request
import requests
import msal

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET", "replace_me")

# ---------- Configure these from env or inline (secure in env for real use) ----------
CLIENT_ID = os.getenv("AZURE_CLIENT_ID", "a41a076d-abfc-4d60-8eb6-ee6c36fde3ac")
CLIENT_SECRET = os.getenv("AZURE_CLIENT_SECRET", "2798Q~NoyMJiryz6eH5egDkh2VDvyJn-R_UmrbjT")
AUTHORITY = os.getenv("AZURE_AUTHORITY", "https://login.microsoftonline.com/common")
REDIRECT_PATH = "/getAToken"
SCOPES = [
    "User.Read",
    "Calendars.Read",
    "Files.Read.All",
    "Chat.Read",
    "OnlineMeetingTranscript.Read.All"
]
GRAPH_API = "https://graph.microsoft.com/v1.0"
BETA_GRAPH = "https://graph.microsoft.com/beta"

# ---------- MSAL helper ----------
def build_msal_app(cache=None):
    return msal.ConfidentialClientApplication(
        CLIENT_ID,
        authority=AUTHORITY,
        client_credential=CLIENT_SECRET,
        token_cache=cache
    )

def get_token():
    return session.get("token")

def api_get(url, token, method_name="GET", accept=None):
    """Helper to call Graph and return structured result for logging"""
    headers = {"Authorization": f"Bearer {token}"}
    if accept:
        headers["Accept"] = accept
    try:
        r = requests.get(url, headers=headers, timeout=30)
    except Exception as e:
        return {"url": url, "status": "request-failed", "error": str(e)}
    # attempt to parse json safely
    text = r.text
    parsed = None
    try:
        parsed = r.json()
    except Exception:
        parsed = text[:2000]  # text snippet
    return {"url": url, "status_code": r.status_code, "body": parsed, "raw_text": text[:2000]}

# ---------- Routes ----------
@app.route("/")
def index():
    if not session.get("user"):
        return '<a href="/login">Sign in with Microsoft</a>'
    u = session["user"]
    return f"""
    <h3>Signed in as: {u.get('name') or u.get('preferred_username') or ''}</h3>
    <a href="/diagnose">🔎 Diagnose meeting transcripts (full check)</a><br>
    <a href="/meetings">📋 Show recent meetings</a><br>
    <a href="/logout">Logout</a>
    """

@app.route("/login")
def login():
    msal_app = build_msal_app()
    auth_url = msal_app.get_authorization_request_url(
        SCOPES, redirect_uri=url_for("authorized", _external=True)
    )
    return redirect(auth_url)

@app.route(REDIRECT_PATH)
def authorized():
    code = request.args.get("code")
    if not code:
        return "No code returned in callback."
    msal_app = build_msal_app()
    result = msal_app.acquire_token_by_authorization_code(
        code,
        scopes=SCOPES,
        redirect_uri=url_for("authorized", _external=True)
    )
    if "access_token" in result:
        session["token"] = result["access_token"]
        # store some user info for display
        id_claims = result.get("id_token_claims") or {}
        session["user"] = {"name": id_claims.get("name"), "oid": id_claims.get("oid"), "tid": id_claims.get("tid")}
        return redirect(url_for("index"))
    return f"Login failed: {json.dumps(result, indent=2)}"

@app.route("/logout")
def logout():
    session.clear()
    logout_url = "https://login.microsoftonline.com/common/oauth2/v2.0/logout?post_logout_redirect_uri=http://127.0.0.1:5000/"
    return redirect(logout_url)

# ---------- List recent meetings (calendar events) ----------
@app.route("/meetings")
def meetings():
    token = get_token()
    if not token:
        return redirect(url_for("login"))

    url = f"{GRAPH_API}/me/events?$orderby=start/dateTime desc&$top=50"
    info = api_get(url, token)
    if info.get("status_code") != 200:
        return f"<h3>Error fetching events</h3><pre>{json.dumps(info, indent=2)}</pre>"

    events = info["body"].get("value", [])
    html = "<h3>Recent calendar events (showing those with onlineMeeting)</h3><ul>"
    for e in events:
        if not e.get("onlineMeeting"):
            continue
        subject = e.get("subject") or ""
        start = e.get("start", {}).get("dateTime")
        om = e.get("onlineMeeting", {})
        om_id = om.get("id") or ""
        join = om.get("joinUrl") or ""
        html += "<li>"
        html += f"<b>{subject}</b><br>Start: {start}<br>"
        html += f"onlineMeeting.id: <code>{om_id}</code><br>"
        html += f"joinUrl: <a href='{join}' target='_blank'>{join}</a><br>"
        # actions
        html += f"<a href='/diagnose?meeting_id={urllib.parse.quote(om_id)}'>Diagnose this meeting</a> | "
        html += f"<a href='/diagnose?meeting_id={urllib.parse.quote(om_id)}&beta=1'>Diagnose (beta)</a>"
        html += "</li><br>"
    html += "</ul>"
    html += "<a href='/'>Back</a>"
    return html

# ---------- Main diagnostic endpoint ----------
@app.route("/diagnose")
def diagnose():
    token = get_token()
    if not token:
        return redirect(url_for("login"))

    # gather diagnostic logs in a list
    logs = []
    user_info = api_get(f"{GRAPH_API}/me", token)
    logs.append({"section": "Signed-in user (/me)", "result": user_info})

    # 1) Fetch events (calendar)
    events_info = api_get(f"{GRAPH_API}/me/events?$orderby=start/dateTime desc&$top=50", token)
    logs.append({"section": "Calendar events (/me/events)", "result": events_info})

    events = []
    if isinstance(events_info.get("body"), dict):
        events = events_info["body"].get("value", [])

    # if meeting_id query param provided, filter to it
    query_mid = request.args.get("meeting_id")
    if query_mid:
        events = [e for e in events if (e.get("onlineMeeting") and (e["onlineMeeting"].get("id") == query_mid or query_mid in (e["onlineMeeting"].get("joinUrl") or "")) )]

    # for each meeting, attempt transcripts + searches
    meeting_sections = []
    for e in events:
        if not e.get("onlineMeeting"):
            continue
        mlog = {"meeting": {"subject": e.get("subject"), "start": e.get("start"), "onlineMeeting": e.get("onlineMeeting")}, "checks": []}
        om = e.get("onlineMeeting", {})
        om_id = om.get("id")
        join = om.get("joinUrl")
        # record the joinUrl and parsed meeting id
        mlog["meeting"]["joinUrl"] = join
        mlog["meeting"]["onlineMeeting.id"] = om_id

        # A) Try /me/onlineMeetings/{id}/transcripts
        if om_id:
            url_v1 = f"{GRAPH_API}/me/onlineMeetings/{urllib.parse.quote(om_id)}/transcripts"
            res_v1 = api_get(url_v1, token)
            mlog["checks"].append({"name": "GET /me/onlineMeetings/{id}/transcripts", "request": url_v1, "result": res_v1})

            # B) Try /communications/onlineMeetings/{id}/transcripts
            url_comm = f"{GRAPH_API}/communications/onlineMeetings/{urllib.parse.quote(om_id)}/transcripts"
            res_comm = api_get(url_comm, token)
            mlog["checks"].append({"name": "GET /communications/onlineMeetings/{id}/transcripts", "request": url_comm, "result": res_comm})

            # C) Try beta endpoint: /beta/users/{userId}/onlineMeetings/{id}/transcripts
            user_oid = user_info.get("body", {}).get("id") or session.get("user", {}).get("oid")
            if user_oid:
                url_beta = f"{BETA_GRAPH}/users/{urllib.parse.quote(user_oid)}/onlineMeetings/{urllib.parse.quote(om_id)}/transcripts"
                res_beta = api_get(url_beta, token)
                mlog["checks"].append({"name": "GET /beta/users/{userId}/onlineMeetings/{id}/transcripts", "request": url_beta, "result": res_beta})
            else:
                mlog["checks"].append({"name": "GET /beta/users/... (skipped)", "note": "could not determine user id for beta request"})

        else:
            mlog["checks"].append({"name": "No onlineMeeting.id present", "note": "cannot call transcript endpoints without id"})

        # D) Search OneDrive for files matching subject and meeting id
        subject = e.get("subject") or ""
        # Search by subject
        if subject:
            od_search_subject = f"{GRAPH_API}/me/drive/root/search(q='{urllib.parse.quote(subject)}')"
            ssub = api_get(od_search_subject, token)
            mlog["checks"].append({"name": "OneDrive search by subject", "request": od_search_subject, "result": ssub})
        # Search by meeting id (if present)
        if om_id:
            od_search_mid = f"{GRAPH_API}/me/drive/root/search(q='{urllib.parse.quote(om_id)}')"
            smid = api_get(od_search_mid, token)
            mlog["checks"].append({"name": "OneDrive search by meeting id", "request": od_search_mid, "result": smid})

        # E) Generic OneDrive "Meeting Transcript" search
        od_search_generic = f"{GRAPH_API}/me/drive/root/search(q='Meeting Transcript')"
        sgen = api_get(od_search_generic, token)
        mlog["checks"].append({"name": "OneDrive search 'Meeting Transcript'", "request": od_search_generic, "result": sgen})

        # F) Search SharePoint via /search/query (modern search)
        search_query_url = f"{GRAPH_API}/search/query"
        search_body = {
            "requests": [
                {
                    "entityTypes": ["site", "driveItem", "listItem"],
                    "query": {"queryString": subject or om_id or "Meeting Transcript"},
                    "from": 0,
                    "size": 25
                }
            ]
        }
        try:
            r = requests.post(search_query_url, headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}, json=search_body, timeout=30)
            search_resp = {"url": search_query_url, "status_code": r.status_code, "body": None}
            try:
                search_resp["body"] = r.json()
            except Exception:
                search_resp["body"] = r.text[:2000]
        except Exception as ex:
            search_resp = {"url": search_query_url, "status_code": "request-failed", "error": str(ex)}
        mlog["checks"].append({"name": "SharePoint /search/query", "request": search_query_url, "result": search_resp})

        # G) Inspect chats: look for meeting id or subject mentions
        chats_url = f"{GRAPH_API}/me/chats"
        chats_res = api_get(chats_url, token)
        mlog["checks"].append({"name": "GET /me/chats (list)", "request": chats_url, "result": chats_res})
        if chats_res.get("status_code") == 200 and isinstance(chats_res.get("body"), dict):
            hits = []
            for chat in chats_res["body"].get("value", [])[:8]:
                cid = chat.get("id")
                if not cid:
                    continue
                msg_url = f"{GRAPH_API}/chats/{urllib.parse.quote(cid)}/messages"
                msg_res = api_get(msg_url, token)
                # scan returned messages for the subject or meeting id strings
                found_snips = []
                if msg_res.get("status_code") == 200 and isinstance(msg_res.get("body"), dict):
                    for msg in msg_res["body"].get("value", [])[:20]:
                        content = ""
                        try:
                            content = (msg.get("body") or {}).get("content", "") or ""
                        except Exception:
                            content = ""
                        if content and (subject.lower() in content.lower() or (om_id and om_id in content)):
                            found_snips.append({"msg": content[:800], "created": msg.get("createdDateTime"), "from": msg.get("from")})
                mlog["checks"].append({"name": f"Chat messages for chat {cid}", "request": msg_url, "result": msg_res, "matches": found_snips})

        meeting_sections.append(mlog)

    # final assembly: produce HTML with everything
    html_parts = []
    html_parts.append("<h2>Diagnosis Report</h2>")
    html_parts.append("<p>Use this to cross-check where transcripts may be stored or why they are not accessible via Graph.</p>")
    html_parts.append("<h3>/me (user info)</h3>")
    html_parts.append("<pre>" + json.dumps(user_info, indent=2) + "</pre>")

    html_parts.append("<h3>Events fetch</h3>")
    html_parts.append("<pre>" + json.dumps(events_info, indent=2) + "</pre>")

    html_parts.append("<h3>Per-meeting checks</h3>")
    for ms in meeting_sections:
        html_parts.append("<hr>")
        html_parts.append(f"<h4>Meeting: {ms['meeting'].get('subject')}</h4>")
        html_parts.append("<pre>" + json.dumps(ms['meeting'], indent=2) + "</pre>")
        for check in ms["checks"]:
            html_parts.append(f"<h5>{check.get('name')}</h5>")
            html_parts.append("<pre>" + json.dumps(check.get("result"), indent=2, default=str) + "</pre>")

    html_parts.append("<hr><p>Done. <a href='/'>Back</a></p>")
    return "\n".join(html_parts)


if __name__ == "__main__":
    app.run(debug=True, port=5000)
