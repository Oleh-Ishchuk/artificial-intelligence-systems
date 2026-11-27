import { S, api, saveChats, dropHist, histKey, DEFAULT_NAME } from "./core.js";

export function createChat(name) {
  const chat = { id: "c" + Date.now().toString(36) + Math.random().toString(36).slice(2, 6), name: name || DEFAULT_NAME, docs: [] };
  S.chats.push(chat); saveChats();
  return chat;
}

const usedElsewhere = (docId) => S.chats.some(c => c.docs.includes(docId));

async function dropUnused(docIds) {
  for (const id of docIds) if (!usedElsewhere(id)) await api("/api/docs/" + id, { method: "DELETE" }).catch(() => {});
}

export async function removeDocFromChat(chat, docId) {
  chat.docs = chat.docs.filter(id => id !== docId); saveChats();
  await dropUnused([docId]);
}

export async function deleteChat(chat) {
  S.chats = S.chats.filter(c => c !== chat); saveChats(); dropHist(chat.id);
  await dropUnused(chat.docs);
}

export function pruneChats() {
  const ids = new Set(S.docs.map(d => d.id));
  S.chats.forEach(c => { c.docs = c.docs.filter(id => ids.has(id)); });
  saveChats();
}

export function adoptOrphans() {
  const used = new Set(S.chats.flatMap(c => c.docs));
  const orphans = S.docs.map(d => d.id).filter(id => !used.has(id));
  if (!orphans.length) return;
  let chat = S.chats.find(c => c.name === "Мої файли");
  if (!chat) {
    chat = createChat("Мої файли");
    try {
      const old = JSON.parse(localStorage.getItem(histKey("all")) || "null");
      if (Array.isArray(old)) { old.forEach(e => { e.scope = chat.id; }); localStorage.setItem(histKey(chat.id), JSON.stringify(old)); localStorage.removeItem(histKey("all")); }
    } catch (e) {}
  }
  chat.docs.push(...orphans); saveChats();
}
