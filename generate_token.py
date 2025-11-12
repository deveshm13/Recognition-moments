import requests

TENANT_ID = "14311cad-f7fd-4ba5-9fd8-b42dabecabba"
CLIENT_ID = "a41a076d-abfc-4d60-8eb6-ee6c36fde3ac"
CLIENT_SECRET = "2798Q~NoyMJiryz6eH5egDkh2VDvyJn-R_UmrbjT"

token_url = f"https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/token"

data = {
    "client_id": CLIENT_ID,
    "scope": "https://graph.microsoft.com/.default",
    "client_secret": CLIENT_SECRET,
    "grant_type": "client_credentials"
}

response = requests.post(token_url, data=data)
token = response.json()

print(token)

