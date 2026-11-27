import { $, S, api, loadChats, activeChat } from "./core.js";
import { svg } from "./icons.js";
import { adoptOrphans } from "./chats.js";
import { refreshDocs, renderList } from "./sidebar.js";
import { renderChat } from "./chat.js";
import "./upload.js";
import "./composer.js";

document.querySelectorAll("[data-i]").forEach(n => { n.innerHTML = svg(n.dataset.i); });

api("/api/status").then(s => {
  $("statusDot").className = "dot " + (s.ok ? "ok" : "bad");
  $("statusText").textContent = s.ok ? s.model + " · " + s.message : s.message;
}).catch(() => { $("statusDot").className = "dot bad"; $("statusText").textContent = "сервер недоступний"; });

(async function init() {
  S.chats = loadChats();
  try { S.chatId = localStorage.getItem("mkr1-active") || ""; S.view = localStorage.getItem("mkr1-view") === "chat" ? "chat" : "home"; } catch (e) { S.chatId = ""; S.view = "home"; }
  try { await refreshDocs(); adoptOrphans(); } catch (e) {}
  if (!activeChat()) { S.chatId = ""; S.view = "home"; }
  renderList(); renderChat();
})();

(function trackComposer() {
  const chat = $("chat"), composer = document.querySelector(".composer"), thread = $("thread");
  const sync = () => {
    chat.style.setProperty("--composer-h", composer.offsetHeight + "px");
    chat.style.setProperty("--sbw", (thread.offsetWidth - thread.clientWidth) + "px");
  };
  new ResizeObserver(sync).observe(composer);
  new ResizeObserver(sync).observe(thread);
  sync();
})();
