import os, json, urllib.request

RAILWAY = os.environ["RAILWAY_TOKEN"]
BOT = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT = os.environ["TELEGRAM_CHAT_ID"]
URL = "https://backboard.railway.com/graphql/v2"
UA = "railway-monitor-bot"


def gql(query):
    req = urllib.request.Request(
        URL,
        data=json.dumps({"query": query}).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + RAILWAY,
            "User-Agent": UA,
        },
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def send(text):
    data = json.dumps({"chat_id": CHAT, "text": text[:4000]}).encode()
    req = urllib.request.Request(
        "https://api.telegram.org/bot" + BOT + "/sendMessage",
        data=data,
        headers={"Content-Type": "application/json", "User-Agent": UA},
    )
    urllib.request.urlopen(req, timeout=30).read()


words = ("credit", "trial", "usage", "balance", "bill", "day", "state", "plan")
lines = []
try:
    lines.append("me: " + json.dumps(gql("{ me { name email } }"))[:300])
    for t in ("Customer", "Workspace", "Query"):
        r = gql('{ __type(name:"%s"){ fields { name } } }' % t)
        info = (r.get("data") or {}).get("__type")
        if not info:
            lines.append(t + ": not found")
            continue
        names = [f["name"] for f in info["fields"] if any(w in f["name"].lower() for w in words)]
        lines.append(t + ": " + ", ".join(names))
except Exception as e:
    lines.append("error: " + str(e))

send("\n".join(lines))
