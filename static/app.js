// ═══════════════════════════════════════════════════════════════
//  Sathi-Connect — app.js   (Degitalservice)
// ═══════════════════════════════════════════════════════════════

// ── State ────────────────────────────────────────────────────────
let currentPage  = 'dashboard';
let fetchedOrders = [];
let cfg = {};

// ── Init ─────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  loadConfig().then(() => {
    navigate('dashboard');
    refreshDashboard();
  });
  document.getElementById('refresh-btn').onclick = () => refreshCurrentPage();
});

// ── Navigation ────────────────────────────────────────────────────
function navigate(page) {
  currentPage = page;
  document.querySelectorAll('.nav-item').forEach(el => el.classList.toggle('active', el.dataset.page === page));
  document.querySelectorAll('.page').forEach(el => el.classList.toggle('hidden', el.id !== 'page-' + page));
  const titles = {
    dashboard: 'Dashboard', sathi_tally: 'SATHI to Tally',
    tally_sathi: 'Tally to SATHI', reports: 'Reports',
    item_mapping: 'Item Mapping', settings: 'Settings',
    tally_setup: 'Tally Setup', license: 'License', issues: 'Issues'
  };
  document.getElementById('page-title').textContent = titles[page] || page;
  refreshCurrentPage();
}

function refreshCurrentPage() {
  if (currentPage === 'dashboard')   refreshDashboard();
  if (currentPage === 'settings')    loadSettingsPage();
  if (currentPage === 'sathi_tally') { /* orders already loaded */ }
  if (currentPage === 'reports')     { /* use date filter */ }
}

// ── API Helper ────────────────────────────────────────────────────
async function api(url, method='GET', body=null) {
  const opts = { method, headers: { 'Content-Type': 'application/json' } };
  if (body) opts.body = JSON.stringify(body);
  const r = await fetch(url, opts);
  return r.json();
}

// ── Config ────────────────────────────────────────────────────────
async function loadConfig() {
  cfg = await api('/api/config');
  updateRightPanel();
}

function updateRightPanel() {
  setEl('rp-licence',  cfg.client_id  || '—');
  setEl('rp-company',  cfg.selected_company || '—');
  setEl('rp-tally-url', cfg.tally_url || '—');
  setEl('rp-owner',    cfg.owner_code || '—');
  // Populate company dropdown if available
}

// ── Dashboard ─────────────────────────────────────────────────────
async function refreshDashboard() {
  if (currentPage !== 'dashboard') return;
  try {
    const s = await api('/api/dashboard/status');
    setEl('stat-sathi-val', s.sathi.ok ? 'Success' : 'Error');
    setEl('stat-sathi-sub', s.sathi.message);
    document.getElementById('stat-sathi')?.classList.toggle('green', s.sathi.ok);
    document.getElementById('stat-sathi')?.classList.toggle('orange', !s.sathi.ok);

    setEl('stat-tally-val', s.tally.ok ? 'Connected' : 'Offline');
    setEl('stat-tally-sub', s.tally.message);
    document.getElementById('stat-tally')?.classList.toggle('blue', s.tally.ok);
    document.getElementById('stat-tally')?.classList.toggle('orange', !s.tally.ok);

    setEl('rp-licence', s.licence || '—');
    setEl('rp-company', s.company || '—');
  } catch(e) {
    console.warn('Dashboard status error:', e);
  }
}

// ── SATHI → Tally ─────────────────────────────────────────────────
async function fetchOrders() {
  const btn = document.getElementById('btn-fetch-orders');
  setLoading(btn, true);
  setEl('orders-table-body', '<tr class="loading-row"><td colspan="7">Fetching orders from SATHI...</td></tr>');
  try {
    const res = await api('/api/fetch-orders', 'POST');
    if (res.statusCode === 200 && res.data) {
      fetchedOrders = res.data;
      renderOrdersTable(res.data);
      toast(`Fetched ${res.data.length} order(s).`, 'ok');
    } else {
      setEl('orders-table-body', `<tr class="empty-row"><td colspan="7">${res.message || 'No orders found.'}</td></tr>`);
      toast(res.message || 'Failed to fetch orders.', 'err');
    }
  } catch(e) {
    setEl('orders-table-body', '<tr class="empty-row"><td colspan="7">Network error. Is the server running?</td></tr>');
  }
  setLoading(btn, false, 'Fetch Orders');
}

function renderOrdersTable(orders) {
  if (!orders.length) {
    setEl('orders-table-body', '<tr class="empty-row"><td colspan="7">No pending orders found.</td></tr>');
    return;
  }
  setEl('orders-table-body', orders.map((o, i) => `
    <tr onclick="toggleExpand(${i})" style="cursor:pointer">
      <td>
        <div class="voucher-num">${o.voucherNumber || '—'}
          <button class="copy-btn" onclick="event.stopPropagation();copyText('${o.voucherNumber}')">Copy</button>
        </div>
        <div class="voucher-date">${formatDate(o.voucherDate)}</div>
        <div class="voucher-type">Vch type: Sathi Purchase</div>
      </td>
      <td>${o.sellerName || '—'}</td>
      <td>₹ ${o.totalBillPrice || '0'}</td>
      <td><span class="badge badge-green">Ready</span></td>
      <td><span class="badge badge-orange">Pending for Tally</span></td>
      <td>
        <button class="btn btn-ghost btn-sm">Status</button>
        <button class="btn btn-primary btn-sm" onclick="event.stopPropagation();pushToTally('${o.voucherNumber}')">Push</button>
      </td>
    </tr>
    <tr id="expand-${i}" class="hidden expand-row">
      <td colspan="7">
        <div class="expand-detail" id="expand-detail-${i}">
          <div style="text-align:center;color:var(--subtext)">Loading lot details...</div>
        </div>
      </td>
    </tr>
  `).join(''));
}

let expandedRow = null;
async function toggleExpand(i) {
  const row = document.getElementById(`expand-${i}`);
  const order = fetchedOrders[i];
  if (!row) return;
  if (!row.classList.contains('hidden')) {
    row.classList.add('hidden');
    expandedRow = null;
    return;
  }
  if (expandedRow !== null) {
    document.getElementById(`expand-${expandedRow}`)?.classList.add('hidden');
  }
  row.classList.remove('hidden');
  expandedRow = i;

  // Fetch lot details
  const detail = document.getElementById(`expand-detail-${i}`);
  try {
    const res = await api('/api/fetch-lot', 'POST', { voucherNumber: order.voucherNumber });
    if (res.statusCode === 200 && res.data && res.data[0]) {
      const d = res.data[0];
      detail.innerHTML = renderLotDetail(d, order);
    } else {
      detail.innerHTML = `<p style="color:var(--subtext)">${res.message || 'Could not fetch lot details.'}</p>`;
    }
  } catch(e) {
    detail.innerHTML = `<p style="color:var(--subtext)">Error fetching lot details.</p>`;
  }
}

function renderLotDetail(d, order) {
  const lots = d.lotData || [];
  return `
    <div style="display:flex;gap:8px;margin-bottom:10px;flex-wrap:wrap">
      <span class="badge badge-grey">1 Item</span>
      <span class="badge badge-blue">Voucher type: Sathi Purchase</span>
      <span class="badge badge-green">Ready</span>
      <span class="badge badge-grey">Lot number will be used as Tally batch</span>
      <button class="btn btn-outlined btn-sm" onclick="reviewMapping()">Review item mapping</button>
    </div>
    <div class="detail-grid">
      <div class="detail-cell"><div class="label">Buyer</div><div class="value">${d.buyerName||'—'}</div></div>
      <div class="detail-cell"><div class="label">Seller</div><div class="value">${d.sellerName||'—'}</div></div>
      <div class="detail-cell"><div class="label">Bill Date</div><div class="value">${d.billDate||'—'}</div></div>
      <div class="detail-cell"><div class="label">Total</div><div class="value">₹ ${d.totalBillPrice||'0'}</div></div>
    </div>
    <div class="lot-table-wrap">
      <table class="lot-table">
        <thead><tr>
          <th>#</th><th>Portal Item</th><th>Batch / LOT</th><th>Tally Item</th>
          <th>Pack</th><th>Bags</th><th>Qty</th><th>Rate</th><th>GST</th><th>Expiry</th>
        </tr></thead>
        <tbody>
          ${lots.map((l, idx) => `
            <tr>
              <td><span class="lot-num">${idx+1}</span></td>
              <td>
                <div style="font-weight:600">${l.varietyName||l.cropName||'—'}</div>
                <div style="font-size:11px;color:var(--subtext)">${l.cropName||''}</div>
              </td>
              <td style="font-family:monospace;font-size:12px">${l.lotNum||'—'}</td>
              <td><span class="badge badge-orange">Not mapped</span></td>
              <td>${l.packingSize||'—'} ${l.packingUnit||''}</td>
              <td>${l.totalBags||'—'}</td>
              <td>${l.totalQty||'—'}</td>
              <td>${l.unitPrice||'—'}</td>
              <td>${l.tax?.igst||0}%</td>
              <td>${l.expiryDate||'—'}</td>
            </tr>
          `).join('')}
          ${!lots.length ? '<tr><td colspan="10" style="text-align:center;color:var(--subtext)">No lot data</td></tr>' : ''}
        </tbody>
      </table>
    </div>
    <div class="tally-result">
      <span class="label">Tally Result</span>
      <span class="badge badge-orange">PENDING FOR TALLY</span>
    </div>
  `;
}

async function pushToTally(voucherNumber) {
  toast('Pushing to Tally... (Tally XML integration required)', 'ok');
}

async function bulkPushToTally() {
  if (!fetchedOrders.length) { toast('Fetch orders first.', 'err'); return; }
  toast(`Bulk push: ${fetchedOrders.length} orders queued.`, 'ok');
}

function reviewMapping() { navigate('item_mapping'); }

// ── Tally → SATHI ─────────────────────────────────────────────────
async function fetchSalesEntries() {
  const from = document.getElementById('sales-from')?.value;
  const to   = document.getElementById('sales-to')?.value;
  if (!from || !to) { toast('Please select a date range.', 'err'); return; }
  setEl('sales-table-body', '<tr class="loading-row"><td colspan="7">Fetching sales from Tally...</td></tr>');
  const res = await api('/api/tally/test');
  if (!res.ok) {
    setEl('sales-table-body', `<tr class="empty-row"><td colspan="7">${res.error || 'Tally not connected.'}</td></tr>`);
    toast('Tally not connected. Check Settings.', 'err');
  } else {
    setEl('sales-table-body', '<tr class="empty-row"><td colspan="7">No Tally sales entries fetched yet.</td></tr>');
    toast('Connected to Tally. No entries for this date range.', 'ok');
  }
}

// ── Reports ───────────────────────────────────────────────────────
async function refreshReport() {
  const from = document.getElementById('rep-from')?.value;
  const to   = document.getElementById('rep-to')?.value;
  const res  = await api('/api/reports', 'POST', { from, to });
  if (res.ok) {
    setEl('rep-received', res.received_from_sathi);
    setEl('rep-sent',     res.sent_to_sathi);
    setEl('rep-licence',  res.active_licence);
    setEl('report-table-body', res.rows.length
      ? res.rows.map(r => `<tr><td>${r.voucher}</td><td>${r.party}</td><td>${r.items}</td><td>${r.buyer}</td><td>${r.amount}</td><td>${r.sathi}</td></tr>`).join('')
      : '<tr class="empty-row"><td colspan="6">No sales report rows loaded.</td></tr>'
    );
  }
}

// ── Settings ──────────────────────────────────────────────────────
async function loadSettingsPage() {
  const c = await api('/api/config');
  cfg = c;
  setVal('s-tally-url',        c.tally_url||'');
  setVal('s-company',          c.selected_company||'');
  setVal('s-timeout',          c.tally_timeout_ms||15000);
  setVal('s-theme',            c.app_theme||'');
  setVal('s-purch-voucher',    c.purchase_voucher_type||'');
  setVal('s-sales-voucher',    c.sales_voucher_type||'');
  setVal('s-purch-ledger',     c.purchase_ledger||'');
  setVal('s-party-ledger',     c.party_ledger_from||'');
  setVal('s-godown',           c.godown||'');
  setVal('s-base-url',         c.base_url||'');
  setVal('s-api-key',          c.api_key||'');
  setVal('s-client-id',        c.client_id||'');
  setVal('s-client-secret',    c.client_secret||'');
  setVal('s-owner-code',       c.owner_code||'');
  setVal('s-location-code',    c.location_code||'');
  setVal('s-state-code',       c.state_code||'27');
  // Load Tally companies
  loadTallyCompanies();
}

async function loadTallyCompanies() {
  const r = await api('/api/tally/companies');
  const sel = document.getElementById('s-company-list');
  if (!sel) return;
  if (r.ok) {
    const matches = [...(r.data||'').matchAll(/<BASICCOMPANYNAME>(.*?)<\/BASICCOMPANYNAME>/g)];
    sel.innerHTML = '<option value="">-- Select Company --</option>' +
      matches.map(m => `<option value="${m[1]}">${m[1]}</option>`).join('');
  } else {
    sel.innerHTML = `<option value="">${r.error||'Tally not connected'}</option>`;
  }
}

async function saveSettings() {
  const data = {
    tally_url:            getVal('s-tally-url'),
    selected_company:     getVal('s-company-list') || getVal('s-company'),
    tally_timeout_ms:     parseInt(getVal('s-timeout')||15000),
    app_theme:            getVal('s-theme'),
    purchase_voucher_type: getVal('s-purch-voucher'),
    sales_voucher_type:   getVal('s-sales-voucher'),
    purchase_ledger:      getVal('s-purch-ledger'),
    party_ledger_from:    getVal('s-party-ledger'),
    godown:               getVal('s-godown'),
    base_url:             getVal('s-base-url'),
    api_key:              getVal('s-api-key'),
    client_id:            getVal('s-client-id'),
    client_secret:        getVal('s-client-secret'),
    owner_code:           getVal('s-owner-code'),
    location_code:        getVal('s-location-code'),
    state_code:           getVal('s-state-code'),
  };
  const res = await api('/api/config', 'POST', data);
  if (res.ok) {
    cfg = { ...cfg, ...data };
    updateRightPanel();
    toast('Configuration saved successfully.', 'ok');
  } else {
    toast('Save failed: ' + res.message, 'err');
  }
}

async function testTally() {
  toast('Testing Tally connection...', '');
  const res = await api('/api/tally/test');
  if (res.ok) toast('Tally connection successful!', 'ok');
  else        toast('Tally error: ' + res.error, 'err');
}

// ── Tally Setup ───────────────────────────────────────────────────
async function downloadTDL() {
  window.location.href = '/api/download-tdl';
  toast('TDL file downloading...', 'ok');
}

// ── Cancel Voucher ────────────────────────────────────────────────
async function cancelVoucher(vNum) {
  if (!confirm(`Cancel voucher ${vNum}?`)) return;
  const res = await api('/api/cancel-voucher', 'POST', { voucherNumber: vNum });
  toast(res.message || 'Done', res.statusCode === 200 ? 'ok' : 'err');
}

// ── Toast ─────────────────────────────────────────────────────────
let toastTimer;
function toast(msg, type='') {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.className = 'show' + (type ? ` toast-${type}` : '');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.className = '', 3500);
}

// ── Helpers ───────────────────────────────────────────────────────
function setEl(id, html) {
  const el = document.getElementById(id);
  if (el) el.innerHTML = html;
}
function setVal(id, val) {
  const el = document.getElementById(id);
  if (el) el.value = val;
}
function getVal(id) {
  return document.getElementById(id)?.value || '';
}
function setLoading(btn, on, label='') {
  if (!btn) return;
  btn.disabled = on;
  btn.innerHTML = on ? '<span class="spinner"></span> Loading...' : label || btn.dataset.label || 'Done';
}
function copyText(text) {
  navigator.clipboard.writeText(text).then(() => toast('Copied!', 'ok'));
}
function formatDate(iso) {
  if (!iso) return '—';
  try { return new Date(iso).toLocaleDateString('en-IN'); } catch { return iso; }
}
function todayStr() {
  return new Date().toISOString().split('T')[0];
}

// Set default dates
document.addEventListener('DOMContentLoaded', () => {
  ['sales-from','sales-to','rep-from','rep-to'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.value = todayStr();
  });
  // rep-from = 30 days ago
  const repFrom = document.getElementById('rep-from');
  if (repFrom) {
    const d = new Date(); d.setDate(d.getDate()-30);
    repFrom.value = d.toISOString().split('T')[0];
  }
});
