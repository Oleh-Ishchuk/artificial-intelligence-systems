import { $, S, el, ext, activeChat, chatDocs } from "./core.js";
import { icon } from "./icons.js";
import { removeDocFromChat } from "./chats.js";
import { refreshDocs } from "./sidebar.js";
import { renderChat } from "./chat.js";

export function pendingMeta(f) {
  if (f.status === "queued") return "у черзі";
  if (f.status === "done" || f.status === "skipped") return f.status === "skipped" ? "вже було проіндексовано" : "готово";
  return f.total ? "індексація " + f.done + "/" + f.total : "читання файлу…";
}

export function paintPending(f) {
  if (!f.refs || f.status === "error") return;
  const finished = f.status === "done" || f.status === "skipped";
  f.refs.meta.textContent = pendingMeta(f);
  f.refs.item.classList.toggle("working", f.status === "indexing");
  f.refs.item.classList.toggle("ready", finished);
  f.refs.bar.style.width = (finished ? 100 : f.total ? Math.max(4, Math.round(100 * f.done / f.total)) : f.status === "queued" ? 0 : 4) + "%";
}

export function renderFiles() {
  const box = $("filesList"); box.textContent = "";
  const chat = S.view === "chat" ? activeChat() : null;
  const docs = chatDocs(chat);
  const pending = chat ? S.pending.filter(f => f.chatId === chat.id) : [];
  $("app").classList.toggle("no-files", !docs.length && !pending.length);
  if (!chat) { $("filesCount").textContent = ""; return; }
  $("filesCount").textContent = docs.length ? String(docs.length) : "";

  pending.forEach(f => {
    const item = el("div", "item pending" + (f.status === "error" ? " failed" : ""));
    item.append(el("span", "badge " + ext(f.name), ext(f.name).toUpperCase().slice(0, 4)));
    const text = el("span", "text"); text.append(el("span", "name", f.name));
    if (f.status === "error") {
      text.append(el("span", "meta", f.error || "Помилка"));
      const x = el("button", "del"); x.type = "button"; x.append(icon("x")); x.setAttribute("aria-label", "Закрити"); x.style.opacity = 1;
      x.onclick = () => { S.pending = S.pending.filter(p => p !== f); renderFiles(); };
      item.append(text, x); f.refs = null;
    } else {
      const meta = el("span", "meta"), track = el("div", "track"), bar = document.createElement("i");
      track.append(bar); text.append(meta, track); item.append(text);
      f.refs = { item, meta, bar }; paintPending(f);
    }
    box.append(item);
  });

  docs.forEach(d => {
    const item = el("div", "item file");
    item.append(el("span", "badge " + ext(d.name), ext(d.name).toUpperCase().slice(0, 4)));
    const text = el("span", "text");
    const name = el("span", "name", d.name); name.title = d.name;
    text.append(name, el("span", "meta", d.chunks + " фрагм." + (d.pages ? " · " + d.pages + " стор." : "")));
    const del = el("button", "del"); del.type = "button"; del.append(icon("trash")); del.title = "Прибрати з чату"; del.setAttribute("aria-label", "Прибрати " + d.name + " з чату");
    del.onclick = async () => {
      if (S.busy) return;
      if (!confirm("Прибрати «" + d.name + "» з цього чату?")) return;
      await removeDocFromChat(chat, d.id);
      await refreshDocs(); renderChat();
    };
    item.append(text, del);
    box.append(item);
  });
}
