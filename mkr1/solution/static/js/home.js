import { $, S, el, askedCount } from "./core.js";
import { icon } from "./icons.js";
import { selectChat, newChat, filesLabel, questionsLabel } from "./sidebar.js";

export function renderHome() {
  const badge = $("scopeBadge"); badge.className = "badge home"; badge.textContent = ""; badge.append(icon("home"));
  $("scopeTitle").textContent = "Головна";
  $("scopeSub").textContent = S.chats.length ? "Оберіть чат або створіть новий" : "Почніть зі створення чату";
  const col = $("col"); col.textContent = "";
  col.classList.remove("swap"); void col.offsetWidth; col.classList.add("swap");
  const box = el("div", "home-view");

  const hero = el("div", "hero");
  hero.append(el("h2", null, "Питайте свої документи"), el("p", null, "Створіть чат і додайте в нього лекції, конспекти чи презентації. Відповідь буде лише з файлів цього чату і з посиланням на джерело. Якщо відповіді там немає, програма так і скаже."));
  const actions = el("div", "actions");
  const add = el("button", "primary"); add.type = "button"; add.append(icon("plus", "sm"), document.createTextNode("Новий чат"));
  add.onclick = newChat; actions.append(add);
  const up = el("button", "ghost"); up.type = "button"; up.append(icon("upload", "sm"), document.createTextNode("Додати файли"));
  up.onclick = () => $("files").click(); actions.append(up);
  hero.append(actions);
  box.append(hero);

  if (S.chats.length) {
    const files = S.chats.reduce((a, c) => a + c.docs.length, 0);
    const questions = S.chats.reduce((a, c) => a + askedCount(c.id), 0);
    const stats = el("div", "stats");
    [["Чатів", S.chats.length], ["Файлів", files], ["Питань поставлено", questions]].forEach(([label, value]) => {
      const tile = el("div", "stat"); tile.append(el("b", null, String(value)), el("span", null, label)); stats.append(tile);
    });
    box.append(stats, el("div", "label", "Відкрити чат"));

    const cards = el("div", "cards");
    S.chats.forEach(c => {
      const card = el("button", "doc-card"); card.type = "button";
      const b = el("span", "badge all"); b.append(icon("message")); card.append(b);
      const text = el("span", "text"); const name = el("span", "name", c.name); name.title = c.name;
      text.append(name, el("span", "meta", filesLabel(c.docs.length))); card.append(text);
      const go = el("span", "go"); const n = askedCount(c.id); if (n) go.append(el("span", "count", questionsLabel(n)));
      go.append(icon("arrow", "sm")); card.append(go);
      card.onclick = () => selectChat(c.id); cards.append(card);
    });
    cards.querySelectorAll(".doc-card").forEach((c, i) => { c.style.animationDelay = Math.min(i, 8) * 40 + "ms"; });
    box.append(cards);
  } else {
    const tips = el("div", "tips");
    [["plus", "Створіть чат", "Один чат: один набір файлів, наприклад «Лекції з Linux»"], ["upload", "Додайте файли", "pdf, docx, pptx, txt або md: кілька одночасно"], ["shield", "Перевірте джерело", "Кожна відповідь має цитату з файлу, яку можна розгорнути"]].forEach(([ic, title, text]) => {
      const t = el("div", "tip"); t.append(icon(ic)); const b = el("div"); b.append(el("b", null, title), el("span", null, text)); t.append(b); tips.append(t);
    });
    box.append(tips);
  }
  col.append(box);
  $("thread").scrollTop = 0;
}
