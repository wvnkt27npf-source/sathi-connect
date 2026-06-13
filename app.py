import os, json, hashlib, hmac, time, threading, webbrowser
from flask import Flask, render_template, request, jsonify, Response
import requests as req

# -- Paths -------------------------------------------------------------------
BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")
SATHI_BASE  = "https://seedtrace.gov.in/inv-apis2/billing"

app = Flask(__name__)

# -- CORS for web access -----------------------------------------------------
@app.after_request
def add_cors(resp):
    resp.headers['Access-Control-Allow-Origin'] = '*'
    resp.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    resp.headers['Access-Control-Allow-Methods'] = 'GET,POST,OPTIONS'
    return resp

# -- Config Helpers ----------------------------------------------------------
def load_cfg():
    """Load config: env vars take priority (Railway), fallback to config.json (local)"""
    env_cfg = {
        "tally_url":              os.environ.get("TALLY_URL", ""),
        "selected_company":       os.environ.get("SELECTED_COMPANY", ""),
        "tally_timeout_ms":       int(os.environ.get("TALLY_TIMEOUT_MS", 15000)),
        "app_theme":              os.environ.get("APP_THEME", "Blue theme - classic"),
        "purchase_voucher_type":  os.environ.get("PURCHASE_VOUCHER_TYPE", "Sathi Purchase"),
        "sales_voucher_type":     os.environ.get("SALES_VOUCHER_TYPE", "Sathi Sales"),
        "purchase_ledger":        os.environ.get("PURCHASE_LEDGER", "Sathi Purchase A/c"),
        "party_ledger_from":      os.environ.get("PARTY_LEDGER_FROM", ""),
        "godown":                 os.environ.get("GODOWN", ""),
        "base_url":               os.environ.get("BASE_URL", "https://seedtrace.gov.in/inv-apis2/billing"),
        "api_key":                os.environ.get("API_KEY", ""),
        "client_id":              os.environ.get("CLIENT_ID", ""),
        "client_secret":          os.environ.get("CLIENT_SECRET", ""),
        "owner_code":             os.environ.get("OWNER_CODE", ""),
        "location_code":          os.environ.get("LOCATION_CODE", ""),
        "state_code":             os.environ.get("STATE_CODE", "27"),
        "port":                   int(os.environ.get("PORT", 5000)),
    }
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            file_cfg = json.load(f)
        for k, v in file_cfg.items():
            if not env_cfg.get(k):
                env_cfg[k] = v
    except Exception:
        pass
    return env_cfg

def save_cfg(data):
    existing = load_cfg()
    existing.update(data)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(existing, f, indent=2)

# -- SATHI Security ----------------------------------------------------------
def key_hash(api_key, ts):
    return hashlib.sha512((api_key + ts).encode()).hexdigest()

def signature(api_key, body):
    return hmac.new(api_key.encode(), body.encode(), hashlib.sha512).hexdigest()

def call_sathi(endpoint, body):
    cfg     = load_cfg()
    api_key = cfg.get("api_key", "")
    cid     = cfg.get("client_id", "")
    csec    = cfg.get("client_secret", "")
    base    = cfg.get("base_url", SATHI_BASE).rstrip("/")

    if not all([api_key, cid, csec]):
        return {"statusCode": 400, "status": "Error",
                "message": "Missing credentials. Go to Settings page."}

    ts = str(int(time.time() * 1000))
    body["ts"]      = int(ts)
    body["keyHash"] = key_hash(api_key, ts)
    raw = json.dumps(body, separators=(",", ":"))
    sig = signature(api_key, raw)

    headers = {
        "Content-Type":  "application/json",
        "signature":     sig,
        "clientid":      cid,
        "clientsecret":  csec,
    }
    url = f"{base}/{endpoint}"
    for attempt in range(2):
        try:
            r = req.post(url, data=raw, headers=headers, timeout=30)
            return r.json()
        except req.exceptions.Timeout:
            if attempt == 1:
                return {"statusCode": 504, "status": "Error", "message": "SATHI API timeout."}
        except req.exceptions.ConnectionError:
            return {"statusCode": 503, "status": "Error", "message": "Cannot reach SATHI Portal."}
        except Exception as e:
            return {"statusCode": 500, "status": "Error", "message": str(e)}

# -- Tally XML Helper --------------------------------------------------------
def call_tally(xml):
    cfg     = load_cfg()
    url     = cfg.get("tally_url", "http://127.0.0.1:9000")
    timeout = int(cfg.get("tally_timeout_ms", 15000)) / 1000
    try:
        r = req.post(url, data=xml.encode("utf-8"),
                     headers={"Content-Type": "text/xml"}, timeout=timeout)
        return {"ok": True, "data": r.text}
    except req.exceptions.ConnectionError:
        return {"ok": False, "error": "Tally is not running or XML server is disabled."}
    except req.exceptions.Timeout:
        return {"ok": False, "error": "Tally connection timed out."}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def get_tally_companies():
    xml = ("<ENVELOPE><HEADER><VERSION>1</VERSION><TALLYREQUEST>EXPORT</TALLYREQUEST>"
           "<TYPE>COLLECTION</TYPE><ID>List of Companies</ID></HEADER>"
           "<BODY><DESC><STATICVARIABLES><SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>"
           "</STATICVARIABLES></DESC></BODY></ENVELOPE>")
    return call_tally(xml)

# -- Page Routes -------------------------------------------------------------
@app.route("/")
def index():
    return render_template("index.html")

# -- Config API --------------------------------------------------------------
@app.route("/api/config", methods=["GET"])
def get_config():
    return jsonify(load_cfg())

@app.route("/api/config", methods=["POST"])
def post_config():
    try:
        save_cfg(request.get_json(force=True) or {})
        return jsonify({"ok": True, "message": "Configuration saved successfully."})
    except Exception as e:
        return jsonify({"ok": False, "message": str(e)}), 500

# -- Dashboard API -----------------------------------------------------------
@app.route("/api/dashboard/status")
def dashboard_status():
    cfg = load_cfg()
    sathi_ok  = False
    sathi_msg = "Not configured"
    if cfg.get("api_key"):
        try:
            r = req.get(cfg.get("base_url", SATHI_BASE).replace("/billing", ""), timeout=5)
            sathi_ok  = r.status_code < 500
            sathi_msg = "Success" if sathi_ok else f"HTTP {r.status_code}"
        except Exception:
            sathi_msg = "Unreachable"

    tally_result = call_tally("<ENVELOPE><HEADER><VERSION>1</VERSION></HEADER></ENVELOPE>")
    tally_ok     = tally_result.get("ok", False)

    return jsonify({
        "sathi":   {"ok": sathi_ok,  "message": sathi_msg},
        "tally":   {"ok": tally_ok,  "message": "Connected" if tally_ok else tally_result.get("error", "Offline")},
        "licence": cfg.get("client_id", "Not set"),
        "company": cfg.get("selected_company", "Not set"),
        "tally_sno": cfg.get("tally_sno", "---"),
    })

# -- SATHI -> Tally ----------------------------------------------------------
@app.route("/api/fetch-orders", methods=["POST"])
def fetch_orders():
    cfg  = load_cfg()
    body = {"ownerCode": cfg.get("owner_code", ""), "stateCode": cfg.get("state_code", "27")}
    return jsonify(call_sathi("getOrderDetailsByBuyerCode", body))

@app.route("/api/pull-lot", methods=["POST"])
def pull_lot():
    cfg  = load_cfg()
    data = request.get_json(force=True) or {}
    body = {"voucherNumber": data.get("voucherNumber", ""),
            "ownerCode":     cfg.get("owner_code", ""),
            "stateCode":     cfg.get("state_code", "27"),
            "locationCode":  cfg.get("location_code", "")}
    return jsonify(call_sathi("pullLotDetailsByBuyerCode", body))

@app.route("/api/fetch-lot", methods=["POST"])
def fetch_lot():
    cfg  = load_cfg()
    data = request.get_json(force=True) or {}
    body = {"voucherNumber": data.get("voucherNumber", ""),
            "ownerCode":     cfg.get("owner_code", ""),
            "stateCode":     cfg.get("state_code", "27"),
            "locationCode":  cfg.get("location_code", "")}
    return jsonify(call_sathi("fetchLotDetailsByBuyerCode", body))

# -- Tally -> SATHI ----------------------------------------------------------
@app.route("/api/create-order", methods=["POST"])
def create_order():
    cfg  = load_cfg()
    data = request.get_json(force=True) or {}
    body = {
        "ownerCode":           cfg.get("owner_code", ""),
        "locationCode":        cfg.get("location_code", ""),
        "stateCode":           cfg.get("state_code", "27"),
        "sellerRole":          data.get("sellerRole", "DEALER"),
        "isRetailSell":        data.get("isRetailSell", "N"),
        "buyerRole":           data.get("buyerRole", "DEALER"),
        "buyerCode":           data.get("buyerCode", ""),
        "saleType":            data.get("saleType", "NORMAL"),
        "selfTransfer":        data.get("selfTransfer", "N"),
        "lotTypeStockDetails": data.get("lotTypeStockDetails", []),
        "villageName":         data.get("villageName", ""),
        "buyerStateCode":      data.get("buyerStateCode", cfg.get("state_code", "27")),
        "phoneNumber":         data.get("phoneNumber", ""),
        "userName":            data.get("userName", ""),
    }
    return jsonify(call_sathi("createSathiOrder", body))

@app.route("/api/cancel-voucher", methods=["POST"])
def cancel_voucher():
    cfg  = load_cfg()
    data = request.get_json(force=True) or {}
    body = {"voucherNumber": data.get("voucherNumber", ""),
            "ownerCode":     cfg.get("owner_code", ""),
            "stateCode":     cfg.get("state_code", "27"),
            "locationCode":  cfg.get("location_code", "")}
    return jsonify(call_sathi("cancelVoucherByBuyerCode", body))

# -- Tally -------------------------------------------------------------------
@app.route("/api/tally/companies")
def tally_companies():
    return jsonify(get_tally_companies())

@app.route("/api/tally/test")
def tally_test():
    return jsonify(call_tally("<ENVELOPE><HEADER><VERSION>1</VERSION></HEADER></ENVELOPE>"))

# -- Reports -----------------------------------------------------------------
@app.route("/api/reports", methods=["POST"])
def reports():
    cfg = load_cfg()
    return jsonify({"ok": True, "active_licence": cfg.get("client_id", "---"),
                    "received_from_sathi": 0, "sent_to_sathi": 0, "rows": []})

# -- Health ------------------------------------------------------------------
@app.route("/api/health")
def health():
    return jsonify({"status": "UP", "ts": int(time.time())})

# -- TDL Download ------------------------------------------------------------
@app.route("/api/download-tdl")
def download_tdl():
    cfg   = load_cfg()
    railway_domain = os.environ.get("RAILWAY_PUBLIC_DOMAIN", "")
    if railway_domain:
        base = "https://" + railway_domain
    else:
        port = cfg.get("port", 5000)
        base = "http://localhost:" + str(port)

    owner = cfg.get("owner_code",    "YOUR_OWNER_CODE")
    state = cfg.get("state_code",    "27")
    loc   = cfg.get("location_code", "YOUR_LOCATION_CODE")

    lines = [
        ";; ==========================================================",
        ";; Sathi-Connect TDL File - Generated by Degitalservice",
        ";; Middleware URL : " + base,
        ";; Owner Code     : " + owner,
        ";; State Code     : " + state,
        ";; Location Code  : " + loc,
        ";; ==========================================================",
        ";;",
        ";; HOW TO LOAD IN TALLY PRIME:",
        ";; 1. Open Tally Prime",
        ";; 2. Press F12 -> Product & Features -> TDL Management",
        ";; 3. Set 'Load TDL files on Startup' = YES",
        ";; 4. Add this file path and press Enter",
        ";; 5. Restart Tally Prime",
        ";;",
        ";; IMPORTANT: Sathi-Connect must be RUNNING before use.",
        ";; ==========================================================",
        "",
        "[Function: SathiGetOrders]",
        "    Variable  : vURL     : String",
        "    Variable  : vBody    : String",
        "    Variable  : vResp    : String",
        '    00 : Set  : vURL     : "' + base + '/api/fetch-orders"',
        '    10 : Set  : vBody    : |{"ownerCode":"' + owner + '","stateCode":"' + state + '"}|',
        "    20 : Set  : vResp    : $$HttpPost:vURL:vBody",
        "    30 : Log Message     : @@vResp",
        "",
        "[Function: SathiPullLot]",
        "    Parameter : pVoucher : String",
        "    Variable  : vURL     : String",
        "    Variable  : vBody    : String",
        "    Variable  : vResp    : String",
        '    00 : Set  : vURL     : "' + base + '/api/pull-lot"',
        '    10 : Set  : vBody    : |{"voucherNumber":"| + @@pVoucher + |","stateCode":"' + state + '","locationCode":"' + loc + '"}|',
        "    20 : Set  : vResp    : $$HttpPost:vURL:vBody",
        "    30 : Log Message     : @@vResp",
        "",
        "[Function: SathiFetchLot]",
        "    Parameter : pVoucher : String",
        "    Variable  : vURL     : String",
        "    Variable  : vBody    : String",
        "    Variable  : vResp    : String",
        '    00 : Set  : vURL     : "' + base + '/api/fetch-lot"',
        '    10 : Set  : vBody    : |{"voucherNumber":"| + @@pVoucher + |","stateCode":"' + state + '","locationCode":"' + loc + '"}|',
        "    20 : Set  : vResp    : $$HttpPost:vURL:vBody",
        "    30 : Log Message     : @@vResp",
        "",
        "[Function: SathiCreateOrder]",
        "    Variable  : vURL     : String",
        "    Variable  : vBody    : String",
        "    Variable  : vResp    : String",
        '    00 : Set  : vURL     : "' + base + '/api/create-order"',
        '    10 : Set  : vBody    : |{"ownerCode":"' + owner + '","locationCode":"' + loc + '","stateCode":"' + state + '","sellerRole":"DEALER","isRetailSell":"N","buyerRole":"DEALER","saleType":"NORMAL","selfTransfer":"N","lotTypeStockDetails":[]}|',
        "    20 : Set  : vResp    : $$HttpPost:vURL:vBody",
        "    30 : Log Message     : @@vResp",
        "",
        "[Function: SathiCancelVoucher]",
        "    Parameter : pVoucher : String",
        "    Variable  : vURL     : String",
        "    Variable  : vBody    : String",
        "    Variable  : vResp    : String",
        '    00 : Set  : vURL     : "' + base + '/api/cancel-voucher"',
        '    10 : Set  : vBody    : |{"voucherNumber":"| + @@pVoucher + |","stateCode":"' + state + '","locationCode":"' + loc + '"}|',
        "    20 : Set  : vResp    : $$HttpPost:vURL:vBody",
        "    30 : Log Message     : @@vResp",
        "",
        "[Button: SATHI Fetch Orders]",
        '    Title   : "Fetch SATHI Orders"',
        "    Action  : Call : SathiGetOrders",
        "    Key     : Alt+F",
        "",
        "[Button: SATHI Pull Lot]",
        '    Title   : "Pull Lot Details"',
        "    Action  : Call : SathiPullLot : $VoucherNumber",
        "    Key     : Alt+P",
        "",
        "[Button: SATHI Fetch Lot]",
        '    Title   : "Fetch Lot Details"',
        "    Action  : Call : SathiFetchLot : $VoucherNumber",
        "    Key     : Alt+L",
        "",
        "[Button: SATHI Create Order]",
        '    Title   : "Create SATHI Order"',
        "    Action  : Call : SathiCreateOrder",
        "    Key     : Alt+C",
        "",
        "[Button: SATHI Cancel Voucher]",
        '    Title   : "Cancel Voucher"',
        "    Action  : Call : SathiCancelVoucher : $VoucherNumber",
        "    Key     : Alt+X",
        "",
        "[Menu: SATHI Integration]",
        '    Add : Item : "Fetch SATHI Orders"   : Call : SathiGetOrders',
        '    Add : Item : "Pull Lot Details"     : Call : SathiPullLot    : $VoucherNumber',
        '    Add : Item : "Fetch Lot Details"    : Call : SathiFetchLot   : $VoucherNumber',
        '    Add : Item : "Create SATHI Order"   : Call : SathiCreateOrder',
        '    Add : Item : "Cancel Voucher"       : Call : SathiCancelVoucher : $VoucherNumber',
        "",
        "[System: Formula]",
        '    Add : Menu Item : "SATHI Integration" : "SATHI Integration"',
        "",
    ]
    tdl = "\n".join(lines)
    return Response(
        tdl,
        mimetype="text/plain",
        headers={"Content-Disposition": "attachment; filename=sathi_integration.tdl"}
    )

# -- Launch ------------------------------------------------------------------
if __name__ == "__main__":
    port    = int(os.environ.get("PORT", load_cfg().get("port", 5000)))
    is_local = not os.environ.get("RAILWAY_ENVIRONMENT")
    url      = "http://localhost:" + str(port)
    print("\n  +--------------------------------------+")
    print("  |   Sathi-Connect by Degitalservice    |")
    print("  |   Running at: " + url + "   |")
    print("  +--------------------------------------+\n")
    if is_local:
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    app.run(host="0.0.0.0", port=port, debug=False)
