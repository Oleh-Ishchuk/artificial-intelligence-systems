import { $, S, el, loadHist, saveHist, dropHist, activeChat, chatDocs } from "./core.js";
import { icon } from "./icons.js";
import { fillCard, userBubble, renderChat } from "./chat.js";
import { renameChat, renderList } from "./sidebar.js";

export function setBusy(on) {
  S.busy = on;
  const b = $("send"); b.className = "send" + (on ? " stop" : ""); b.textContent = ""; b.append(icon(on ? "stop" : "up"));
  b.setAttribute("aria-label", on ? "Зупинити" : "Запитати");
}

export async function send() {
  const q = $("question").value.trim();
  if (S.busy || q.length < 3) return;
  const chat = activeChat(), docs = chatDocs(chat);
  if (!docs.length) { $("question").placeholder = "Спершу додайте файли в цей чат"; return; }
  const scope = chat.id, hist = loadHist(scope);
  const col = $("col"); const empty = col.querySelector(".empty"); if (empty) empty.remove();
  $("question").value = ""; autosize();
  const bubble = userBubble(q); bubble.classList.add("enter"); col.append(bubble);
  const card = el("div", "bot enter"), answer = el("div", "answer live");
  const think = el("div", "thinking"), dots = el("span", "dots"), thinkText = el("span", null, "Шукаю у файлах…");
  dots.append(document.createElement("i"), document.createElement("i"), document.createElement("i")); think.append(dots, thinkText);
  card.append(think); col.append(card);
  const scroll = () => { $("thread").scrollTo({ top: $("thread").scrollHeight, behavior: "smooth" }); };
  scroll();

  const asked = Date.now(); let text = "", done = null, stopped = false, failed = null;
  S.ctrl = new AbortController(); setBusy(true);
  try {
    const res = await fetch("/api/ask/stream", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question: q, doc_ids: docs.map(d => d.id) }), signal: S.ctrl.signal });
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).error || "Помилка запиту");
    const reader = res.body.getReader(), decoder = new TextDecoder(); let buf = "";
    while (true) {
      const { value, done: end } = await reader.read();
      if (end) break;
      buf += decoder.decode(value, { stream: true });
      let nl;
      while ((nl = buf.indexOf("\n")) >= 0) {
        const line = buf.slice(0, nl).trim(); buf = buf.slice(nl + 1);
        if (!line) continue;
        const ev = JSON.parse(line);
        if (ev.type === "retrieval") { thinkText.textContent = ev.count ? "Знайдено " + ev.count + " фрагм., формую відповідь…" : "Фрагментів не знайдено"; }
        else if (ev.type === "delta") {
          if (think.isConnected) { think.replaceWith(answer); }
          text += ev.text; answer.textContent = text; $("thread").scrollTop = $("thread").scrollHeight;
        } else if (ev.type === "done") done = ev.result;
        else if (ev.type === "error") failed = ev.error;
      }
    }
  } catch (e) { if (e.name === "AbortError") stopped = true; else failed = e.message; }
  S.ctrl = null; setBusy(false);

  if (stopped) { card.textContent = ""; card.append(el("div", "answer none", "Зупинено. Питання не збережено.")); setTimeout(() => { card.remove(); bubble.remove(); }, 2000); return; }
  if (!done) { card.textContent = ""; card.append(el("div", "answer err", failed || "Відповіді не отримано")); return; }

  const entry = { q, r: done, asked, scope, fb: {} };
  hist.push(entry); saveHist(scope, hist);
  card.textContent = ""; card.append(el("div", "answer" + (done.found ? "" : " none"), done.answer));
  fillCard(card, entry, hist);
  scroll(); $("question").focus();
}

$("form").addEventListener("submit", (e) => { e.preventDefault(); if (S.busy && S.ctrl) S.ctrl.abort(); else send(); });
$("question").addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); if (!S.busy) send(); } });
export function autosize() { const t = $("question"); t.style.height = "auto"; t.style.height = Math.min(t.scrollHeight, 160) + "px"; t.style.overflowY = t.scrollHeight > 160 ? "auto" : "hidden"; }
$("question").addEventListener("input", autosize);
$("clear").onclick = () => {
  if (S.busy || !S.chatId) return;
  if (loadHist(S.chatId).length && !confirm("Очистити історію питань у цьому чаті?")) return;
  dropHist(S.chatId); renderList(); renderChat();
};
$("rename").onclick = () => { if (!S.busy) renameChat(); };
