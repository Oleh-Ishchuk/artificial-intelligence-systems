export const $ = (id) => document.getElementById(id);

export const el = (tag, cls, text) => { const n = document.createElement(tag); if (cls) n.className = cls; if (text != null) n.textContent = text; return n; };
export const S = { docs: [], chats: [], chatId: "", pending: [], view: "home", busy: false, ctrl: null };
export const ext = (name) => (name.split(".").pop() || "").toLowerCase();
export const stem = (name) => name.replace(/\.[^.]+$/, "");

export async function api(path, options) {
  const res = await fetch(path, options);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || "Помилка запиту");
  return data;
}
export const post = (path, body) => api(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

export const histKey = (chatId) => "mkr1-chat:" + chatId;
export function loadHist(chatId) { try { return JSON.parse(localStorage.getItem(histKey(chatId)) || "[]"); } catch (e) { return []; } }
export function saveHist(chatId, list) { try { localStorage.setItem(histKey(chatId), JSON.stringify(list.slice(-40))); } catch (e) {} }
export function dropHist(chatId) { try { localStorage.removeItem(histKey(chatId)); } catch (e) {} }
export const askedCount = (chatId) => loadHist(chatId).length;

export const DEFAULT_NAME = "Новий чат";
export function loadChats() {
  try { const v = JSON.parse(localStorage.getItem("mkr1-chats") || "[]"); return Array.isArray(v) ? v : []; } catch (e) { return []; }
}
export function saveChats() { try { localStorage.setItem("mkr1-chats", JSON.stringify(S.chats)); } catch (e) {} }
export function saveView() { try { localStorage.setItem("mkr1-active", S.chatId); localStorage.setItem("mkr1-view", S.view); } catch (e) {} }
export const activeChat = () => S.chats.find(c => c.id === S.chatId);
export const chatDocs = (chat) => (chat ? S.docs.filter(d => chat.docs.includes(d.id)) : []);
