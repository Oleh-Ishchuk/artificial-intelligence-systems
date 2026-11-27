import { $, S, el, loadHist, saveHist, post, activeChat, chatDocs } from "./core.js";
import { icon } from "./icons.js";
import { filesLabel } from "./sidebar.js";
import { renderFiles } from "./files.js";
import { renderHome } from "./home.js";
import { send } from "./composer.js";

export function renderChat() {
  if (S.view === "chat" && !activeChat()) S.view = "home";
  const home = S.view === "home";
  $("chat").classList.toggle("home", home); $("app").classList.toggle("home", home);
  if (home) return renderHome();
  const chat = activeChat();
  const docs = chatDocs(chat);
  const badge = $("scopeBadge"); badge.className = "badge all"; badge.textContent = ""; badge.append(icon("message"));
  $("scopeTitle").textContent = chat.name;
  $("scopeSub").textContent = docs.length ? filesLabel(docs.length) + " · відповіді лише з них" : "У чаті ще немає файлів";
  $("question").placeholder = docs.length ? "Поставте питання по файлах чату…" : "Спершу додайте файли в цей чат";
  const col = $("col"); col.textContent = "";
  col.classList.remove("swap"); void col.offsetWidth; col.classList.add("swap");
  const hist = loadHist(chat.id);
  if (!hist.length) { col.append(emptyState(docs)); }
  hist.forEach((entry) => { col.append(userBubble(entry.q)); col.append(botCard(entry, hist)); });
  $("thread").scrollTop = $("thread").scrollHeight;
  renderFiles();
}

function emptyState(docs) {
  const box = el("div", "empty");
  const big = el("div", "big"); big.append(icon("fileSearch")); box.append(big);
  if (!docs.length) {
    box.append(el("h2", null, "Додайте файли в цей чат"), el("p", null, "Натисніть скріпку біля поля питання або перетягніть документи у вікно чату. Формати: pdf, docx, pptx, txt, md. Після індексації можна ставити питання."));
    const add = el("button", "primary"); add.type = "button"; add.append(icon("upload", "sm"), document.createTextNode("Додати файли"));
    add.onclick = () => $("files").click(); box.append(add);
    return box;
  }
  box.append(el("h2", null, docs.length === 1 ? "Запитайте щось про цей файл" : "Запитайте щось по файлах чату"),
             el("p", null, "Відповідь буде лише з тексту документів чату. Якщо там цього немає, програма так і скаже."));
  const chips = el("div", "chips");
  (docs.length === 1 ? ["Яка тема цього документа?", "Які основні поняття тут розглядаються?"] : ["Про що ці документи?"]).forEach(t => {
    const b = el("button", "chip"); b.type = "button"; b.append(icon("sparkles"), document.createTextNode(t));
    b.onclick = () => { $("question").value = t; send(); }; chips.append(b);
  });
  box.append(chips);
  return box;
}

export const userBubble = (q) => el("div", "user", q);

export function botCard(entry, hist) {
  const card = el("div", "bot");
  card.append(el("div", "answer" + (entry.r.found ? "" : " none"), entry.r.answer));
  fillCard(card, entry, hist);
  return card;
}

export function fillCard(card, entry, hist) {
  const r = entry.r;
  if (r.low_confidence) {
    const n = el("div", "note"); n.append(icon("alert", "sm"), el("span", null, "У файлах немає фрагментів, схожих на це питання, тому модель не викликалась."));
    card.append(n);
  }
  if (r.found && r.verified != null) {
    const v = el("div", "verify " + (r.verified ? "ok" : "warn"));
    v.append(icon(r.verified ? "check" : "alert", "sm"), el("span", null, r.verified ? "Підтверджено цитатою з файлу" : "Цитату не вдалося знайти в файлі, перевірте джерело"));
    card.append(v);
  }
  const used = r.sources.filter(s => s.used);
  if (used.length) {
    const wrap = el("div", "srcs"), quotes = el("div");
    used.forEach(s => {
      const chip = el("button", "src-chip"); chip.type = "button"; chip.setAttribute("aria-expanded", "false");
      chip.append(icon("file", "sm"), document.createTextNode(s.file + (s.page ? ", стор. " + s.page : "")));
      let quote = null;
      chip.onclick = () => {
        if (quote) { quote.remove(); quote = null; chip.setAttribute("aria-expanded", "false"); return; }
        quote = el("div", "quote", s.text); quotes.append(quote); chip.setAttribute("aria-expanded", "true");
      };
      wrap.append(chip);
    });
    card.append(wrap, quotes);
  }
  const foot = el("div", "foot");
  foot.append(rate("Відповідь правильна?", "correct", entry, hist), rate("Джерело правильне?", "source_ok", entry, hist));
  const time = el("span", "time"); time.append(icon("clock", "sm"));
  const parts = ["пошук " + r.retrieval_s + " с"]; if (r.llm_s) parts.push("відповідь " + r.llm_s + " с");
  time.append(document.createTextNode(parts.join(" · ")));
  foot.append(time, copyButton(r.answer));
  card.append(foot);
}

export function copyButton(text) {
  const b = el("button", "copy"); b.type = "button"; b.title = "Копіювати відповідь"; b.setAttribute("aria-label", "Копіювати відповідь");
  const idle = icon("copy", "idle"), done = icon("check", "done"); b.append(idle, done);
  b.onclick = async () => {
    try { await navigator.clipboard.writeText(text); } catch (e) { return; }
    b.classList.add("copied"); setTimeout(() => b.classList.remove("copied"), 1500);
  };
  return b;
}

export function rate(label, key, entry, hist) {
  const g = el("span", "grp"); g.append(label);
  const yes = el("button"), no = el("button"); yes.type = no.type = "button";
  yes.append(icon("check", "sm"), document.createTextNode("Так")); no.append(icon("x", "sm"), document.createTextNode("Ні"));
  const paint = () => { yes.className = entry.fb[key] === true ? "yes" : ""; no.className = entry.fb[key] === false ? "no" : ""; };
  const set = (value) => {
    if (!entry.fb.first) entry.fb.first = Date.now();
    entry.fb[key] = value; paint();
    saveHist(entry.scope, hist);
    post("/api/feedback", { id: entry.r.id, correct: entry.fb.correct, source_ok: entry.fb.source_ok, elapsed_s: Math.round((entry.fb.first - entry.asked) / 1000) }).catch(() => {});
  };
  yes.onclick = () => set(true); no.onclick = () => set(false); paint();
  g.append(yes, no); return g;
}
