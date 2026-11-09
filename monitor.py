import os, json, time, urllib.request

RAILWAY = os.environ["RAILWAY_TOKEN"]
BOT = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT = str(os.environ["TELEGRAM_CHAT_ID"])
UA = "railway-monitor-bot"
STATE_FILE = "state.json"

TRIAL_ALERT_DAYS = 5     # هشدار وقتی روز باقی‌مانده کمتر یا مساوی این باشد
CREDIT_ALERT_USD = 0.5     # هشدار وقتی اعتبار کمتر یا مساوی این باشد
TRIAL_REPEAT_H = 12       # هر چند ساعت یادآوری هشدار روزها
CREDIT_REPEAT_H = 3       # هر چند ساعت یادآوری هشدار اعتبار

FIELDS = "state isTrialing trialDaysRemaining creditBalance remainingUsageCreditBalance currentUsage"
QUERIES = [
    "{ me { customer { %s } } }",
    "{ me { workspaces { name customer { %s } } } }",
]
KB = {"keyboard": [[{"text": "📊 وضعیت"}]], "resize_keyboard": True}


def http(url, payload=None, headers=None):
    h = {"Content-Type": "application/json", "User-Agent": UA}
    if headers:
        h.update(headers)
    data = json.dumps(payload).encode() if payload is not None else None
    last = None
    for _ in range(3):
        try:
            req = urllib.request.Request(url, data=data, headers=h)
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.load(r)
        except Exception as e:
            last = e
            time.sleep(2)
    raise last


def gql(q):
    return http("https://backboard.railway.com/graphql/v2", {"query": q},
                {"Authorization": "Bearer " + RAILWAY})


def tg(method, payload):
    return http("https://api.telegram.org/bot%s/%s" % (BOT, method), payload)


def send(text):
    try:
        tg("sendMessage", {"chat_id": CHAT, "text": text[:4000], "reply_markup": KB})
        return True
    except Exception as e:
        print("send failed:", e)
        return False


def dig(x):
    if isinstance(x, dict):
        if "trialDaysRemaining" in x:
            return x
        for v in x.values():
            r = dig(v)
            if r:
                return r
    elif isinstance(x, list):
        for v in x:
            r = dig(v)
            if r:
                return r
    return None


def find_customer():
    errs = []
    for q in QUERIES:
        try:
            r = gql(q % FIELDS)
        except Exception as e:
            errs.append(str(e)[:150])
            continue
        if r.get("errors"):
            errs.append(str(r["errors"][0].get("message", ""))[:150])
        c = dig(r.get("data") or {})
        if c:
            return c, errs
    return None, errs


def status_text(c):
    return (
        "📊 وضعیت Railway\n"
        "دوره آزمایشی: %s\n"
        "روز باقی‌مانده: %s\n"
        "اعتبار باقی‌مانده: %s\n"
        "مصرف فعلی: %s\n"
        "creditBalance (خام): %s\n"
        "زمان: %s"
        % (c.get("isTrialing"), c.get("trialDaysRemaining"),
           c.get("remainingUsageCreditBalance"), c.get("currentUsage"),
           c.get("creditBalance"), time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()))
    )


def load_state():
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except Exception:
        return {}


def main():
    state = load_state()
    c, errs = find_customer()

    asked = False
    ups = []
    try:
        ups = tg("getUpdates", {"timeout": 0, "allowed_updates": ["message"]}).get("result", [])
    except Exception as e:
        print("getUpdates failed:", e)
    for u in ups:
        m = u.get("message") or {}
        if str((m.get("chat") or {}).get("id")) != CHAT:
            continue
        t = m.get("text", "")
        if t.startswith("/start") or t.startswith("/status") or "وضعیت" in t:
            asked = True
    if ups:
        try:
            tg("getUpdates", {"offset": ups[-1]["update_id"] + 1, "timeout": 0})
        except Exception as e:
            print("confirm failed:", e)

    if c is None:
        if asked:
            send("⚠️ نتوانستم وضعیت را از Railway بگیرم.\n" + "\n".join(errs))
        return

    if asked:
        send(status_text(c))

    now = time.time()
    changed = False
    try:
        days = float(c.get("trialDaysRemaining"))
    except Exception:
        days = None
    try:
        credit = float(c.get("remainingUsageCreditBalance"))
    except Exception:
        credit = None

    if (c.get("isTrialing") and days is not None and days <= TRIAL_ALERT_DAYS
            and now - state.get("trial", 0) > TRIAL_REPEAT_H * 3600):
        if send("⏳ هشدار: %s روز تا پایان دوره آزمایشی Railway مانده.\n\n%s" % (c.get("trialDaysRemaining"), status_text(c))):
            state["trial"] = now
            changed = True

    if (credit is not None and credit <= CREDIT_ALERT_USD
            and now - state.get("credit", 0) > CREDIT_REPEAT_H * 3600):
        if send("💸 هشدار: اعتبار Railway رو به اتمام است.\n\n" + status_text(c)):
            state["credit"] = now
            changed = True

    if changed:
        with open(STATE_FILE, "w") as f:
            json.dump(state, f)


main()
