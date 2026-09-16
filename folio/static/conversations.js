"use strict";
let currentConversation=null;
function renderSources(sources){
  $("sources").replaceChildren();
  if(!sources.length)$("sources").append(node("p","No supporting passages for this message."));
  sources.forEach((s,i)=>{
    const card=node("div",undefined,"source-card");
    card.append(node("strong","["+(s.source_number||i+1)+"] "+s.filename+" - page "+s.page),node("p",s.text));
    if(docs.some(d=>d.id===s.document_id)){
      const open=node("button","Open document");open.onclick=()=>openDoc(s.document_id);card.append(open);
    }else card.append(node("small","Original document is no longer in the library."));
    $("sources").append(card);
  });
}
async function loadHistory(){
  const owner=accountUser?.id;const chats=await api("/conversations");if(accountUser?.id!==owner)return;$("chat-history").replaceChildren();
  chats.forEach(c=>{
    const button=node("button",c.title,"history-item"+(currentConversation===c.id?" active":""));
    button.title=c.title;button.onclick=()=>resumeChat(c.id).catch(e=>toast(e.message));$("chat-history").append(button);
  });
  $("delete-chat").hidden=!currentConversation;
}
async function resumeChat(id){
  const owner=accountUser?.id;const chat=await api("/conversations/"+id);if(accountUser?.id!==owner)return;
  currentConversation=id;$("chat-title").textContent=chat.title;
  $("messages").replaceChildren();$("question").value="";$("scope").value=chat.document_id||"";
  chat.messages.forEach(m=>{
    const element=bubble(m.content,m.role);
    if(m.role==="assistant"){
      element.append(node("small",m.payload.mode||"saved answer"));
      const inspect=node("button","View sources","text-button");
      inspect.onclick=()=>renderSources(m.payload.sources||[]);element.append(inspect);
    }
  });
  const last=[...chat.messages].reverse().find(m=>m.role==="assistant");
  renderSources(last?.payload.sources||[]);
  await loadHistory();view("chat");
}
function resetChat(){
  currentConversation=null;$("chat-title").textContent="New chat";$("delete-chat").hidden=true;
  $("messages").replaceChildren();$("sources").replaceChildren(node("p","Ask a question to see supporting passages."));
  $("question").value="";document.querySelectorAll(".history-item").forEach(b=>b.classList.remove("active"));
}
$("new-chat").onclick=()=>{resetChat();$("question").focus();};
$("scope").addEventListener("change",resetChat);
$("delete-chat").onclick=async()=>{
  if(!currentConversation||!confirm("Delete this saved conversation?"))return;
  try{await api("/conversations/"+currentConversation,{method:"DELETE"});resetChat();await loadHistory();}
  catch(e){toast(e.message);}
};
