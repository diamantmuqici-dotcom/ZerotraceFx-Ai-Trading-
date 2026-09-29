import { createRouter } from "./router.js";
import { createTheme } from "./theme.js";
import { bindSidebar } from "./sidebar.js";
import { createNavbar } from "./navbar.js";
import { renderEquityChart } from "./charts.js";
import { renderPositions } from "./trades.js";
import { renderJournal } from "./journal.js";
import { renderWatchlist } from "./watchlist.js";
import { bindSettings } from "./settings.js";
import { createNotifications } from "./notifications.js";
import { enableMotion } from "./animations.js";
import { seedParticles } from "./particles.js";
import { createSearch } from "./search.js";
import { announce } from "./voice.js";

const bridge = window.zerotrace;
const api = {
  request: async (method, path, body = null) => {
    if (bridge) return bridge.request(method, path, body);
    const response = await fetch(`/api${path}`, {method, headers: {"Content-Type": "application/json"}, body: body ? JSON.stringify(body) : undefined});
    if (!response.ok) throw new Error(`API ${response.status}`);
    return response.json();
  }
};

const state = {snapshot: null, ai: {}, journal: [], query: ""};
const notifications = createNotifications();
const theme = createTheme();
const router = createRouter(name => {
  document.querySelectorAll("[data-page]").forEach(page => page.classList.toggle("is-active", page.dataset.page === name));
  document.querySelectorAll("[data-route]").forEach(link => link.classList.toggle("is-active", link.dataset.route === name));
  const kicker = document.querySelector("[data-page-kicker]");
  if (kicker) kicker.textContent = name === "dashboard" ? "Real-time execution" : name.replace("-", " ");
});
const sidebar = bindSidebar(router);
const navbar = createNavbar({
  onSearch: createSearch(router),
  onTheme: () => theme.cycle(),
  onNotifications: () => notifications.show("Notifications are generated from real terminal events.")
});

function money(value) {
  if (typeof value !== "number" || !Number.isFinite(value)) return "—";
  return new Intl.NumberFormat(undefined, {style: "currency", currency: "USD", maximumFractionDigits: 2}).format(value);
}
function signedMoney(value) {
  if (typeof value !== "number" || !Number.isFinite(value)) return "—";
  return `${value >= 0 ? "+" : "−"}${money(Math.abs(value))}`;
}
function number(value, suffix = "") { return typeof value === "number" && Number.isFinite(value) ? `${value.toFixed(2)}${suffix}` : "—"; }
function field(name, value, tone = "") { document.querySelectorAll(`[data-field="${name}"]`).forEach(node => { node.textContent = value; node.classList.remove("positive", "negative"); if (tone) node.classList.add(tone); }); }

function renderThemes() {
  const root = document.querySelector("[data-themes]");
  if (!root || root.childElementCount) return;
  theme.all().forEach(item => {
    const card = document.createElement("article"); card.className = "card glass";
    const title = document.createElement("h2"); title.className = "section-title"; title.textContent = item.name;
    const copy = document.createElement("p"); copy.className = "page-copy"; copy.textContent = item.note;
    const button = document.createElement("button"); button.className = "button button-primary"; button.type = "button"; button.textContent = "Apply theme";
    button.addEventListener("click", () => { theme.apply(item.id); notifications.show(`${item.name} applied`); });
    card.append(title, copy, button); root.append(card);
  });
}

function renderReasoning(lines) {
  const root = document.querySelector("[data-reasoning]"); if (!root) return; root.replaceChildren();
  if (!lines?.length) { const empty = document.createElement("div"); empty.className = "empty"; empty.textContent = "Waiting for the next authenticated market scan."; root.append(empty); return; }
  lines.forEach(line => { const row = document.createElement("div"); row.className = "list-row"; row.textContent = line; root.append(row); });
}
function renderSnapshot(snapshot, ai) {
  state.snapshot = snapshot; state.ai = ai || {}; state.journal = snapshot.recent_trades || [];
  const floating = Number(snapshot.floating) || 0; const daily = Number(snapshot.daily_pnl) || 0;
  field("balance", money(Number(snapshot.balance))); field("equity", money(Number(snapshot.equity)));
  field("equity-change", snapshot.updated_at ? `updated ${new Date(snapshot.updated_at).toLocaleTimeString()}` : "waiting for MT5");
  field("floating", signedMoney(floating), floating >= 0 ? "positive" : "negative");
  field("daily_pnl", signedMoney(daily), daily >= 0 ? "positive" : "negative");
  field("weekly_pnl", signedMoney(Number(snapshot.weekly_pnl) || 0));
  field("win_rate", number(Number(snapshot.win_rate), "%"));
  field("trade_count", `${snapshot.total_trades || 0} closed trades`);
  field("winning_trades", String(snapshot.winning_trades || 0));
  field("total_trades", String(snapshot.total_trades || 0));
  field("drawdown_pct", number(Number(snapshot.drawdown_pct), "%"));
  field("basket_profit", signedMoney(Number(snapshot.basket_profit) || 0));
  field("basket_target", `Target ${money(Number(snapshot.basket_target) || 0)}`);
  field("basket_highest", signedMoney(Number(snapshot.basket_highest) || 0));
  field("basket_direction", snapshot.basket_direction || "NEUTRAL");
  field("trailing_active", snapshot.trailing_active ? "ACTIVE" : "OFF");
  field("position_count", String(snapshot.open_positions?.length || 0));
  field("last_signal", snapshot.last_signal || "HOLD");
  field("last_confidence", number(Number(snapshot.last_confidence)));
  field("active_symbol", snapshot.active_symbol || "—"); field("session", snapshot.session || "—");
  field("ai_trades_learned", String(snapshot.ai_trades_learned || ai?.trades_learned || 0));
  field("kill_switch", snapshot.kill_switch ? "LATCHED" : "READY", snapshot.kill_switch ? "negative" : "positive");
  field("updated_at", snapshot.updated_at ? new Date(snapshot.updated_at).toLocaleTimeString() : "waiting");
  renderEquityChart(snapshot.equity_curve || []); renderPositions(snapshot.open_positions || []); renderWatchlist(snapshot);
  renderReasoning(snapshot.last_reasoning || []); renderJournal(state.journal, state.query);
  const ring = document.querySelector("[data-confidence-ring]"); if (ring) { ring.setAttribute("stroke-dasharray", "100"); ring.setAttribute("stroke-dashoffset", String(100 - Math.max(0, Math.min(100, Number(snapshot.last_confidence) || 0)))); }
  const ready = snapshot.status_message?.toLowerCase().includes("connected");
  navbar.setSession(ready ? "MT5 connected" : "MT5 waiting", ready);
  const dot = document.querySelector("[data-venue-dot]"); if (dot) dot.classList.toggle("connected", ready);
  const venue = document.querySelector("[data-venue-status]"); if (venue) venue.textContent = snapshot.status_message || "Waiting for authenticated MT5 session...";
}

async function refresh() {
  try {
    const [snapshot, ai] = await Promise.all([api.request("GET", "/status"), api.request("GET", "/ai")]);
    renderSnapshot(snapshot, ai);
  } catch (error) {
    const message = error instanceof Error ? error.message : "API unavailable";
    navbar.setSession("MT5 waiting", false);
    const venue = document.querySelector("[data-venue-status]"); if (venue) venue.textContent = "Waiting for authenticated MT5 session...";
    if (!state.snapshot) notifications.show(`Real terminal unavailable: ${message}`, "warn");
  }
}

async function closeAll() {
  if (!window.confirm("Close every real MT5 position now?")) return;
  try { await api.request("POST", "/close_all", {}); notifications.show("Close-all request sent to MT5", "success"); await refresh(); }
  catch (error) { notifications.show(error.message || "Close-all failed", "warn"); }
}

document.addEventListener("zt-close-all", closeAll);
document.querySelectorAll("[data-journal-search]").forEach(input => input.addEventListener("input", () => { state.query = input.value; renderJournal(state.journal, state.query); }));
bindSettings(); renderThemes(); enableMotion(); seedParticles(); sidebar.activate(router.current()); router.start();
setInterval(refresh, 2500); refresh();
window.addEventListener("beforeunload", () => announce("ZeroTrace terminal closed"));
