'use strict';
const $ = id => document.getElementById(id);
const state = { report: null, currency: 'USD', tab: 'exceptions', search: '', status: '', page: 1 };
const PAGE_SIZE = 8;
const money = value => value === null || value === undefined ? '—' : new Intl.NumberFormat('en-US', { style: 'currency', currency: state.currency, minimumFractionDigits: 2 }).format(value / 100);
const label = value => String(value).toLowerCase().replaceAll('_', ' ').replace(/\b\w/g, c => c.toUpperCase());
const dateLabel = value => new Date(`${value}T12:00:00Z`).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric', timeZone: 'UTC' });
function element(tag, text, className) { const node = document.createElement(tag); if (text !== undefined) node.textContent = text; if (className) node.className = className; return node; }
function inCurrency(key) { return state.report[key].filter(row => row.currency === state.currency); }
function badge(value) {
  const kind = value.startsWith('MATCHED') ? 'good' : ['LOW', 'MEDIUM', 'DUPLICATE_IMPORT', 'LATE_SETTLEMENT', 'PENDING_SETTLEMENT', 'PENDING_BANK_CREDIT', 'NOT_DUE'].includes(value) ? 'warning' : value === 'EXCLUDED' ? '' : 'bad';
  return element('span', label(value), `status ${kind}`);
}
function renderSummary() {
  const metric = state.report.metrics[state.currency];
  $('match-rate').textContent = metric.match_rate_pct === null ? 'N/A' : `${metric.match_rate_pct.toFixed(2)}%`;
  $('match-detail').textContent = `${metric.matched_due.toLocaleString()} of ${metric.eligible_due.toLocaleString()} eligible due transactions`;
  $('match-progress').style.width = `${metric.match_rate_pct || 0}%`;
  $('expected-net').textContent = money(metric.expected_due_net_minor);
  $('ledger-variance').textContent = money(metric.ledger_abs_variance_minor);
  $('bank-variance').textContent = money(metric.bank_abs_variance_minor);
  $('bank-detail').textContent = `Separate control · ${metric.bank_due_batches} due batches`;
  $('bank-health').textContent = `${metric.bank_matched_batches} / ${metric.bank_due_batches}`;
  $('attention-count').textContent = `${inCurrency('exceptions').filter(row => row.severity === 'HIGH').length} high-priority exception records`;
  $('incompatible-note').textContent = metric.ledger_incompatible_count ? `${metric.ledger_incompatible_count} incompatible ledger reference(s) require review. Expected net of ${money(metric.ledger_incompatible_expected_minor)} is excluded from the variance calculation. The two control variances must not be added together.` : 'The two control variances must not be added together. Pending items already due are included; not-yet-due items are excluded.';
  for (const key of ['exceptions', 'transactions', 'batches']) $('count-' + key).textContent = inCurrency(key).length;
  const transactions = inCurrency('transactions');
  const due = transactions.filter(row => row.eligible && row.due_date <= state.report.as_of);
  const groups = new Map();
  for (const row of due) {
    if (!groups.has(row.due_date)) groups.set(row.due_date, { matched: 0, open: 0 });
    groups.get(row.due_date)[row.matched ? 'matched' : 'open']++;
  }
  const days = [...groups.entries()].sort((a, b) => a[0].localeCompare(b[0]));
  const max = Math.max(1, ...days.map(([, counts]) => counts.matched + counts.open));
  const chart = $('daily-chart'); chart.replaceChildren();
  chart.setAttribute('aria-label', `${due.length} eligible due ${state.currency} transactions by settlement due date; ${metric.matched_due} matched and ${due.length - metric.matched_due} open.`);
  for (const [day, counts] of days) {
    const bar = element('div', undefined, 'bar-stack');
    bar.title = `${dateLabel(day)}: ${counts.matched} matched, ${counts.open} open`;
    const open = element('div', undefined, 'bar-open'); open.style.height = `${100 * counts.open / max}%`;
    const matched = element('div', undefined, 'bar-match'); matched.style.height = `${100 * counts.matched / max}%`;
    bar.append(open, matched); chart.append(bar);
  }
  $('chart-first').textContent = days.length ? dateLabel(days[0][0]).replace(' 2026', '') : 'No due records';
  $('chart-last').textContent = days.length ? dateLabel(days[days.length - 1][0]).replace(' 2026', '') : '';
  $('breakdown').replaceChildren();
  for (const [name, count, color] of [
    ['Matched due transactions', metric.matched_due, '#119d8e'],
    ['Open due transactions', metric.eligible_due - metric.matched_due, '#d9983f'],
    ['Not yet due', transactions.filter(row => row.status === 'NOT_DUE').length, '#9aacc1'],
    ['Failed / voided ledger records', transactions.filter(row => !row.eligible).length, '#bc9bb0'],
  ]) {
    const row = element('div', undefined, 'breakdown-row');
    const dot = element('i', undefined, 'breakdown-dot'); dot.style.backgroundColor = color;
    row.append(dot, element('span', name), element('strong', count.toLocaleString())); $('breakdown').append(row);
  }
}
function filteredRecords() {
  const rows = inCurrency(state.tab).filter(row => {
    const status = state.tab === 'exceptions' ? row.code : row.status;
    return (!state.status || status === state.status) && (!state.search || Object.values(row).join(' ').toLowerCase().includes(state.search));
  });
  if (state.tab === 'exceptions') {
    const priority = { HIGH: 0, MEDIUM: 1, LOW: 2 };
    rows.sort((a, b) => priority[a.severity] - priority[b.severity] || b.age_business_days - a.age_business_days || a.reference.localeCompare(b.reference));
  }
  return rows;
}
function setupStatusOptions() {
  const select = $('status-filter'); select.replaceChildren(new Option('All statuses / issues', ''));
  const values = [...new Set(inCurrency(state.tab).map(row => state.tab === 'exceptions' ? row.code : row.status))].sort();
  for (const value of values) select.add(new Option(label(value), value));
  state.status = ''; select.value = '';
}
function moneyCell(value, highlight = false) {
  return element('td', money(value), 'money' + (highlight && value ? ' positive-gap' : ''));
}
function renderTable() {
  const rows = filteredRecords();
  const totalPages = Math.max(1, Math.ceil(rows.length / PAGE_SIZE));
  $('table-note').textContent = state.tab === 'exceptions' ? 'Reported amounts are issue-specific, not a combined financial exposure. Open a record for its definition and follow-up.' : 'Net difference = expected minus actual. A dash means the amounts cannot be compared safely.';
  state.page = Math.min(state.page, totalPages);
  const columns = state.tab === 'exceptions' ? ['Reference / owner', 'Issue', 'Reported amount', 'Age (business days)', 'Priority', ''] : state.tab === 'transactions' ? ['Transaction / type', 'Expected net', 'Actual net', 'Net difference', 'Status', ''] : ['Batch', 'Expected payout', 'Bank amount', 'Net difference', 'Status', ''];
  const header = element('tr');
  columns.forEach((column, index) => { const th = element('th', column); th.scope = 'col'; if (index > 0 && index < (state.tab === 'exceptions' ? 0 : 4)) th.className = 'money'; header.append(th); });
  $('table-head').replaceChildren(header);
  $('table-body').replaceChildren();
  for (const row of rows.slice((state.page - 1) * PAGE_SIZE, state.page * PAGE_SIZE)) {
    const tr = element('tr');
    const id = state.tab === 'exceptions' ? row.reference : state.tab === 'transactions' ? row.transaction_id : row.batch_id;
    const ref = element('td', id);
    if (state.tab === 'exceptions') {
      ref.append(element('small', `${row.layer} · ${row.owner}`));
      const code = element('td'); code.append(badge(row.code));
      const priority = element('td'); priority.append(badge(row.severity));
      tr.append(ref, code, moneyCell(row.amount_minor), element('td', row.age_business_days), priority);
    } else {
      if (state.tab === 'transactions') ref.append(element('small', `${label(row.transaction_type)} · ${label(row.channel)}`));
      const status = element('td'); status.append(badge(row.status));
      tr.append(ref, moneyCell(row.expected_net_minor), moneyCell(row.actual_net_minor), moneyCell(row.net_delta_minor, true), status);
    }
    const action = element('td'); const button = element('button', 'Review →', 'review');
    button.setAttribute('aria-label', `Review ${id}`); button.addEventListener('click', () => openDetail(row));
    action.append(button); tr.append(action); $('table-body').append(tr);
  }
  $('empty-state').hidden = rows.length > 0;
  const first = rows.length ? (state.page - 1) * PAGE_SIZE + 1 : 0;
  $('page-summary').textContent = `Showing ${first}–${Math.min(state.page * PAGE_SIZE, rows.length)} of ${rows.length} records · ${state.currency}`;
  $('page-number').textContent = `${state.page} / ${totalPages}`;
  $('previous').disabled = state.page <= 1;
  $('next').disabled = state.page >= totalPages;
  $('export').disabled = rows.length === 0;
  $('records-panel').setAttribute('aria-labelledby', `tab-${state.tab}`);
}
function selectTab(tab) {
  state.tab = tab; state.page = 1;
  document.querySelectorAll('[data-tab]').forEach(button => { const active = button.dataset.tab === tab; button.setAttribute('aria-selected', active); button.tabIndex = active ? 0 : -1; });
  setupStatusOptions(); renderTable();
}
function openDetail(row) {
  $('dialog-label').textContent = state.tab === 'exceptions' ? `${row.layer} EXCEPTION` : state.tab === 'transactions' ? 'LEDGER RECONCILIATION' : 'BANK PAYOUT CONTROL';
  $('dialog-title').textContent = row.reference || row.transaction_id || row.batch_id;
  const grid = element('dl', undefined, 'detail-grid');
  for (const [key, value] of Object.entries(row)) {
    if (['action', 'description'].includes(key)) continue;
    const block = element('div');
    const name = label(key.replace('_minor', ''));
    const display = key.endsWith('_minor') ? money(value) : value === null ? 'Not comparable' : typeof value === 'boolean' ? value ? 'Yes' : 'No' : String(value || '—');
    block.append(element('dt', name), element('dd', display)); grid.append(block);
  }
  const note = element('div', undefined, 'detail-action'); note.append(element('h3', 'Follow-up'));
  note.append(element('p', row.action || (row.matched ? 'The amounts reconcile at this control layer. Review any independent timing or data-quality exceptions before closing the overall case.' : 'Review the source transaction, processor settlement, and bank reference. Amounts in different currencies or identities are never automatically matched.')));
  if (row.description) note.append(element('p', row.description));
  if (row.code === 'CURRENCY_MISMATCH' || row.status === 'CURRENCY_MISMATCH') note.append(element('p', 'The reported expected amount is in the ledger/batch currency. Incompatible actual amounts are not converted or included in the variance. Inspect the source feed for the actual currency and amount.'));
  if (state.tab === 'exceptions') note.append(element('p', 'Reported amounts depend on the issue: monetary gaps use expected minus actual; orphan items show unallocated source amounts; audit and SLA-only events use zero. Do not sum this column as financial exposure.'));
  $('dialog-content').replaceChildren(grid, note); $('detail-dialog').showModal();
}
function exportRows() {
  const rows = filteredRecords(); if (!rows.length) return;
  const keys = Object.keys(rows[0]);
  const quote = value => {
    let text = value === null ? '' : String(value);
    if (typeof value === 'string' && /^[=+\-@]/.test(text)) text = "'" + text;
    return '"' + text.replaceAll('"', '""') + '"';
  };
  const csv = [keys.map(quote).join(','), ...rows.map(row => keys.map(key => quote(row[key])).join(','))].join('\r\n');
  const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }));
  const link = element('a'); link.href = url; link.download = `${state.tab}-${state.currency}-${state.report.as_of}.csv`; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
async function load() {
  $('loading').hidden = false; $('load-error').hidden = true; $('dashboard').hidden = true;
  try {
    const response = await fetch('data/report.json');
    if (!response.ok) throw new Error('Snapshot HTTP error');
    const report = await response.json();
    if (report.synthetic !== true || !report.metrics || !Array.isArray(report.transactions) || !Array.isArray(report.exceptions) || !Array.isArray(report.batches)) throw new Error('Invalid snapshot');
    state.report = report;
    $('as-of').textContent = dateLabel(report.as_of);
    renderSummary(); setupStatusOptions(); renderTable();
    $('dashboard').hidden = false;
  } catch (error) { $('load-error').hidden = false; }
  finally { $('loading').hidden = true; }
}
$('currency').addEventListener('change', event => { state.currency = event.target.value; state.page = 1; renderSummary(); setupStatusOptions(); renderTable(); });
$('search').addEventListener('input', event => { state.search = event.target.value.trim().toLowerCase(); state.page = 1; renderTable(); });
$('status-filter').addEventListener('change', event => { state.status = event.target.value; state.page = 1; renderTable(); });
$('previous').addEventListener('click', () => { state.page--; renderTable(); });
$('next').addEventListener('click', () => { state.page++; renderTable(); });
$('export').addEventListener('click', exportRows);
$('retry').addEventListener('click', load);
$('close-dialog').addEventListener('click', () => $('detail-dialog').close());
document.querySelectorAll('[data-tab]').forEach(button => {
  button.addEventListener('click', () => selectTab(button.dataset.tab));
  button.addEventListener('keydown', event => {
    if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
    event.preventDefault();
    const tabs = [...document.querySelectorAll('[data-tab]')];
    let index = tabs.indexOf(button);
    index = event.key === 'Home' ? 0 : event.key === 'End' ? tabs.length - 1 : (index + (event.key === 'ArrowRight' ? 1 : -1) + tabs.length) % tabs.length;
    selectTab(tabs[index].dataset.tab); tabs[index].focus();
  });
});
$('guide').addEventListener('click', () => {
  $('dialog-label').textContent = 'CONTROL METHODOLOGY'; $('dialog-title').textContent = 'Two layers of reconciliation';
  const copy = element('div', undefined, 'guide-copy');
  for (const [title, text] of [
    ['1. Ledger → processor', 'Match exact transaction references, merchant, provider, currency, signed gross, fee, net, and finality. Distinct partial settlement rows may combine into one transaction. Failed and voided transactions are not eligible.'],
    ['2. Processor batch → bank', 'Sum unique settlement portions within a single-currency batch and compare with bank entries referencing that batch. Split credits are permitted. Unreferenced cash stays unallocated.'],
    ['Amounts and timing', 'All amounts use integer minor units. Payment fees use basis points plus a fixed fee, rounded half up; refunds do not return the original fee. The demo uses T+2 business-day settlement, T+1 batch payouts, and one business day of grace. Country-specific holidays are not modeled.'],
    ['Read the metrics correctly', 'Match rate is matched captured transactions divided by eligible captured transactions due by the cutoff. Ledger and bank absolute variances are independent sums of absolute differences for comparable due items, including pending items. Incompatible currencies/identities and unallocated orphans are flagged separately; do not add layers or currencies.'],
    ['Demonstration only', 'All records are deterministic fictional data. The cutoff is fixed for reproducibility. No live bank connection, actual payment processing, or measured operational impact is claimed.'],
  ]) copy.append(element('h3', title), element('p', text));
  $('dialog-content').replaceChildren(copy); $('detail-dialog').showModal();
});
load();
