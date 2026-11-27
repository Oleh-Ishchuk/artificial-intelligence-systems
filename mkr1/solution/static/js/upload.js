import { $, S, api, stem, saveChats, saveView, activeChat, DEFAULT_NAME } from "./core.js";
import { createChat } from "./chats.js";
import { renderList, refreshDocs } from "./sidebar.js";
import { renderFiles, paintPending } from "./files.js";
import { renderChat } from "./chat.js";

$("attach").onclick = () => $("files").click();
$("files").onchange = (e) => { upload([...e.target.files]); e.target.value = ""; };

let dragDepth = 0;
const hasFiles = (e) => [...(e.dataTransfer ? e.dataTransfer.types : [])].includes("Files");
const zone = $("chat");
zone.addEventListener("dragenter", (e) => { if (hasFiles(e)) { e.preventDefault(); dragDepth++; zone.classList.add("dropping"); } });
zone.addEventListener("dragover", (e) => { if (hasFiles(e)) e.preventDefault(); });
zone.addEventListener("dragleave", () => { dragDepth = Math.max(0, dragDepth - 1); if (!dragDepth) zone.classList.remove("dropping"); });
zone.addEventListener("drop", (e) => { e.preventDefault(); dragDepth = 0; zone.classList.remove("dropping"); upload([...e.dataTransfer.files]); });
window.addEventListener("dragover", (e) => e.preventDefault());
window.addEventListener("drop", (e) => e.preventDefault());

export async function upload(files) {
  if (!files.length) return;

  let chat = S.view === "chat" ? activeChat() : null;
  if (!chat) { chat = createChat(stem(files[0].name)); S.chatId = chat.id; S.view = "chat"; saveView(); renderChat(); }
  else if (!chat.docs.length && chat.name === DEFAULT_NAME) { chat.name = stem(files[0].name); saveChats(); }
  const chatId = chat.id;
  const fd = new FormData(); files.forEach(f => fd.append("files", f));
  const batch = files.map(f => ({ name: f.name, chatId, status: "queued", done: 0, total: 0 }));
  S.pending.push(...batch); renderList(); renderFiles();
  let job_id;
  try { ({ job_id } = await api("/api/docs", { method: "POST", body: fd })); }
  catch (e) { batch.forEach(f => { f.status = "error"; f.error = e.message; }); renderFiles(); return; }

  let job;
  do {
    await new Promise(r => setTimeout(r, 500));
    let failedNow = false;
    try { job = await api("/api/jobs/" + job_id); } catch (e) { batch.forEach(f => { f.status = "error"; f.error = e.message; }); failedNow = true; }
    if (job && !failedNow) {
      job.files.forEach((jf, i) => {
        if (jf.status === "error" && batch[i].status !== "error") failedNow = true;
        Object.assign(batch[i], { status: jf.status, done: jf.done, total: jf.total, error: jf.error, doc_id: jf.doc_id });
      });
    }
    if (failedNow) { renderFiles(); if (!job) break; } else batch.forEach(paintPending);
  } while (!job || job.status !== "done");

  await new Promise(r => setTimeout(r, 600));
  S.pending = S.pending.filter(f => f.status === "error" || !batch.includes(f));
  await refreshDocs();
  const target = S.chats.find(c => c.id === chatId);
  if (target) {
    batch.forEach(f => { if (f.doc_id && !target.docs.includes(f.doc_id)) target.docs.push(f.doc_id); });
    saveChats();
  }
  renderList(); renderFiles();
  if (!S.busy && S.view === "chat" && S.chatId === chatId) renderChat();
}
