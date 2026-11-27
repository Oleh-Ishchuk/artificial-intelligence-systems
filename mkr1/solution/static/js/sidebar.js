import { $, S, el, api, saveView, saveChats, askedCount, activeChat, DEFAULT_NAME } from "./core.js";
import { icon } from "./icons.js";
import { createChat, deleteChat, pruneChats } from "./chats.js";
import { renderFiles } from "./files.js";
import { renderChat } from "./chat.js";

const plural = (n, one, few, many) => {
  const m10 = n % 10, m100 = n % 100;
  return n + " " + (m10 === 1 && m100 !== 11 ? one : m10 >= 2 && m10 <= 4 && (m100 < 10 || m100 >= 20) ? few : many);
};
export const filesLabel = (n) => plural(n, "файл", "файли", "файлів");
export const questionsLabel = (n) => plural(n, "питання", "питання", "питань");

export function renderList() {
  const box = $("list"); box.textContent = "";

  const home = el("button", "item" + (S.view === "home" ? " active" : "")); home.type = "button";
  const homeBadge = el("span", "badge home"); homeBadge.append(icon("home"));
  const homeText = el("span", "text"); homeText.append(el("span", "name", "Головна"), el("span", "meta", "огляд чатів і підказки"));
  home.append(homeBadge, homeText); home.onclick = goHome;
  box.append(home);

  const add = el("button", "item new"); add.type = "button";
  const addBadge = el("span", "badge home"); addBadge.append(icon("plus"));
  const addText = el("span", "text"); addText.append(el("span", "name", "Новий чат"), el("span", "meta", "окремий набір файлів"));
  add.append(addBadge, addText); add.onclick = newChat;
  box.append(add);

  if (S.chats.length) box.append(el("div", "label", "Чати"));
  S.chats.forEach(c => {
    const item = el("div", "item" + (S.view === "chat" && c.id === S.chatId ? " active" : "")); item.setAttribute("role", "button"); item.tabIndex = 0;
    const badge = el("span", "badge all"); badge.append(icon("message"));
    const text = el("span", "text");
    const name = el("span", "name", c.name); name.title = c.name;
    const asked = askedCount(c.id);
    text.append(name, el("span", "meta", filesLabel(c.docs.length) + (asked ? " · " + questionsLabel(asked) : "")));
    const del = el("button", "del"); del.type = "button"; del.append(icon("trash")); del.title = "Видалити чат"; del.setAttribute("aria-label", "Видалити чат " + c.name);
    del.onclick = async (e) => {
      e.stopPropagation();
      if (S.busy) return;
      if (!confirm("Видалити чат «" + c.name + "», його файли та історію питань?")) return;
      await deleteChat(c);
      if (S.chatId === c.id) { S.chatId = ""; S.view = "home"; saveView(); }
      await refreshDocs(); renderChat();
    };
    item.append(badge, text, del);
    item.onclick = () => selectChat(c.id);
    item.onkeydown = (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); selectChat(c.id); } };
    box.append(item);
  });
}

export async function refreshDocs() {
  S.docs = (await api("/api/docs")).docs;
  pruneChats();
  if (S.chatId && !activeChat()) { S.chatId = ""; S.view = "home"; saveView(); }
  renderList(); renderFiles();
}

export function selectChat(id) {
  if (S.busy || (id === S.chatId && S.view === "chat")) return;
  S.chatId = id; S.view = "chat"; saveView();
  renderList(); renderChat();
  $("question").focus();
}

export function goHome() {
  if (S.busy || S.view === "home") return;
  S.view = "home"; saveView();
  renderList(); renderChat();
}

export function newChat() {
  if (S.busy) return;
  const open = S.view === "chat" ? activeChat() : null;
  if (open && !open.docs.length && open.name === DEFAULT_NAME) { $("question").focus(); return; }
  const chat = createChat();
  selectChat(chat.id);
}

export function renameChat() {
  const chat = activeChat(); if (!chat) return;
  const name = (prompt("Назва чату", chat.name) || "").trim().slice(0, 60);
  if (!name || name === chat.name) return;
  chat.name = name; saveChats(); renderList(); renderChat();
}
