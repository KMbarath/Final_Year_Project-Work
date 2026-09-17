"use strict";
const $=id=>document.getElementById(id);
let docs=[],activeDoc=null,status={},recorder=null,audioChunks=[];
const titles={library:"Document library",chat:"Ask your documents",reminders:"Reminders",training:"Model lab"};
async function api(path,options={}) {
  let r;
  try { r=await fetch("/api"+path,options); }
  catch(e) {
    if(e.name!=="TypeError")throw e;
    throw Error("Cannot reach the local Folio server. Start it with .\\scripts\\start.ps1 -Background, then refresh this page and try again.");
  }
  if(r.status===401&&!path.startsWith("/auth/"))showAuth();
  if(!r.ok){let detail="Request failed.";try{const b=await r.json();detail=typeof b.detail==="string"?b.detail:JSON.stringify(b.detail);}catch(_){}throw Error(detail);}
  return r.status===204?null:r.json();
}
function body(value,method="POST"){return{method,headers:{"Content-Type":"application/json"},body:JSON.stringify(value)};}
function node(tag,text,cls){const el=document.createElement(tag);if(text!==undefined)el.textContent=text;if(cls)el.className=cls;return el;}
function toast(text){$("toast").textContent=text;$("toast").hidden=false;clearTimeout(toast.timer);toast.timer=setTimeout(()=>$("toast").hidden=true,6000);}
function view(name){document.querySelectorAll(".view").forEach(v=>v.hidden=v.id!==name);document.querySelectorAll(".nav").forEach(b=>b.classList.toggle("active",b.dataset.view===name));$("breadcrumb").textContent=titles[name];if(name==="reminders")loadReminders();if(name==="training")loadTraining();}
document.querySelectorAll(".nav").forEach(b=>b.onclick=()=>view(b.dataset.view));
function renderDocs(){
 const query=$("filter").value.toLowerCase(),shown=docs.filter(d=>(d.filename+" "+d.classification.label).toLowerCase().includes(query));
 $("documents").replaceChildren();$("empty").hidden=docs.length>0;
 shown.forEach(d=>{const card=node("button",undefined,"document-card");card.append(node("div","▤","file-icon"),node("span",d.classification.label,"tag"),node("h3",d.filename),node("small",d.pages.length+" page(s) · "+new Date(d.created_at).toLocaleDateString()));const foot=node("div",undefined,"card-footer");foot.append(node("span",d.expiry_date?(d.expiry_confirmed?"Expires ":"Review: ")+d.expiry_date:"Details extracted"),node("span","↗"));card.append(foot);card.onclick=()=>openDoc(d.id);$("documents").append(card);});
 if(docs.length&&!shown.length)$("documents").append(node("p","No documents match.","no-items"));
 ["doc-count","nav-count","library-count"].forEach(id=>$(id).textContent=docs.length);
 const previous=$("scope").value;$("scope").replaceChildren(new Option("All documents",""));docs.forEach(d=>$("scope").add(new Option(d.filename,d.id)));if(docs.some(d=>d.id===previous))$("scope").value=previous;
}
const accessibilityStyle=document.createElement("style");accessibilityStyle.textContent=".dashboard-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px;margin-top:28px}.dashboard-card{background:#fff;border:1px solid var(--line);border-radius:10px;padding:20px}.dashboard-card h2{margin-top:0}.dashboard-row{display:flex;align-items:center;gap:12px;padding:10px 0;border-top:1px solid var(--line)}.dashboard-row p{margin:0;flex:1;font-size:12px}.dashboard-row small{margin-left:auto;color:var(--muted);font-size:10px}.dashboard-row strong{text-transform:capitalize;font-size:12px}.accessibility-controls{display:flex;gap:8px}.large-text{font-size:17px}.large-text .nav,.large-text .document-card,.large-text .bubble{font-size:15px}.high-contrast{--paper:#fff;--ink:#000;--muted:#222;--green:#005a3c;--line:#333;--mint:#d8f1e5}.high-contrast button,.high-contrast input,.high-contrast select{border-color:#111}@media(max-width:720px){.dashboard-grid{grid-template-columns:1fr}.accessibility-controls{display:none}}";document.head.append(accessibilityStyle);
function formatBytes(bytes){if(bytes<1024)return bytes+" B";if(bytes<1024*1024)return (bytes/1024).toFixed(1)+" KB";return (bytes/(1024*1024)).toFixed(1)+" MB";}
async function loadDashboard(){const owner=accountUser?.id;const data=await api("/dashboard");if(accountUser?.id!==owner)return;$("search-mode").textContent=formatBytes(data.storage_bytes);$("search-caption").textContent="Private storage used";const recommendations=$("recommendations"),activity=$("activity");recommendations.replaceChildren();activity.replaceChildren();if(!data.recommendations.length)recommendations.append(node("p","No renewal actions are needed.","no-items"));data.recommendations.forEach(item=>{const row=node("div",undefined,"dashboard-row");row.append(node("p",item.message));const open=node("button","View document","text-button");open.onclick=()=>openDoc(item.document_id);row.append(open);recommendations.append(row);});if(!data.recent_activity.length)activity.append(node("p","Your account activity will appear here.","no-items"));data.recent_activity.forEach(item=>{const row=node("div",undefined,"dashboard-row");row.append(node("strong",item.event.replaceAll("_"," ")),node("small",new Date(item.created_at).toLocaleString()));activity.append(row);});}
async function refresh(){const owner=accountUser?.id;const loaded=await api("/documents");if(accountUser?.id!==owner)return;docs=loaded;renderDocs();await loadReminders();}
$("filter").oninput=renderDocs;$("demo-help").onclick=()=>$("demo-path").hidden=!$("demo-path").hidden;
const accessibilityControls=document.createElement("div");accessibilityControls.className="accessibility-controls";const textSize=node("button","A+","text-button"),contrast=node("button","High contrast","text-button");textSize.type=contrast.type="button";textSize.onclick=()=>{document.body.classList.toggle("large-text");localStorage.setItem("folio-large-text",document.body.classList.contains("large-text")?"1":"0");};contrast.onclick=()=>{document.body.classList.toggle("high-contrast");localStorage.setItem("folio-high-contrast",document.body.classList.contains("high-contrast")?"1":"0");};accessibilityControls.append(textSize,contrast);document.querySelector(".account-menu").prepend(accessibilityControls);if(localStorage.getItem("folio-large-text")==="1")document.body.classList.add("large-text");if(localStorage.getItem("folio-high-contrast")==="1")document.body.classList.add("high-contrast");
$("upload").accept += ",.doc,.docx";
async function upload(files){
 let successes=0,failures=[];$("dropzone").setAttribute("aria-busy","true");
 for(const file of files){$("upload-status").textContent="Reading "+file.name+"…";if(file.size>20*1024*1024){failures.push(file.name+": exceeds 20 MB");continue;}const form=new FormData();form.append("file",file);try{await api("/documents",{method:"POST",body:form});successes++;}catch(e){failures.push(file.name+": "+e.message);}}
 $("upload-status").textContent=successes+" document(s) added. "+failures.join(" ");$("dropzone").removeAttribute("aria-busy");$("upload").value="";await refresh().catch(e=>toast(e.message));
}
$("upload").onchange=e=>upload(Array.from(e.target.files));
$("dropzone").onkeydown=e=>{if(e.key==="Enter"||e.key===" "){e.preventDefault();$("upload").click();}};
["dragenter","dragover"].forEach(n=>$("dropzone").addEventListener(n,e=>{e.preventDefault();$("dropzone").classList.add("drag");}));
["dragleave","drop"].forEach(n=>$("dropzone").addEventListener(n,e=>{e.preventDefault();$("dropzone").classList.remove("drag");}));
$("dropzone").addEventListener("drop",e=>upload(Array.from(e.dataTransfer.files)));
function openDoc(id){
 const d=docs.find(d=>d.id===id);if(!d)return;activeDoc=d;$("detail-title").textContent=d.filename;$("detail-content").replaceChildren(node("p","Suggested type: "+d.classification.label+" · "+Math.round(d.classification.confidence*100)+"% model score"));
 for(const e of d.entities){const row=node("div",undefined,"entity");row.append(node("span",e.label.replaceAll("_"," ")),node("strong",e.text));$("detail-content").append(row);}
 const download=node("a","Download original document","text-button");download.href="/api/documents/"+d.id+"/download";$("detail-content").append(download);
 if(!d.entities.length)$("detail-content").append(node("p","No labelled fields detected. You can still search the text."));
 $("expiry-date").value=d.expiry_date||"";$("detail-text").textContent=d.pages.map(p=>"PAGE "+p.page+" · "+p.method+"\n"+p.text).join("\n\n");if(!$("detail").open)$("detail").showModal();
}
$("close-detail").onclick=()=>$("detail").close();
$("expiry-form").onsubmit=async e=>{e.preventDefault();try{await api("/documents/"+activeDoc.id+"/expiry",body({expiry_date:$("expiry-date").value||null},"PATCH"));await refresh();openDoc(activeDoc.id);toast("Expiry date saved.");}catch(e){toast(e.message);}};
$("ask-document").onclick=()=>{$("detail").close();view("chat");$("scope").value=activeDoc.id;resetChat();$("question").focus();};
$("delete-document").onclick=async()=>{if(!confirm("Delete "+activeDoc.filename+" and its extracted details?"))return;try{await api("/documents/"+activeDoc.id,{method:"DELETE"});$("detail").close();await refresh();toast("Document deleted.");}catch(e){toast(e.message);}};
async function loadReminders(){const owner=accountUser?.id;try{const rows=await api("/reminders");if(accountUser?.id!==owner)return;$("due-count").textContent=rows.length;$("reminder-count").textContent=rows.length;$("reminders-list").replaceChildren();if(!rows.length)$("reminders-list").append(node("p","You're all caught up. No documents are due within 30 days.","no-items"));rows.forEach(r=>{const el=node("div",undefined,"reminder");el.append(node("span","◷","stat-icon amber"));const content=node("div");content.append(node("h3",r.message),node("p","Expiry date · "+r.expiry_date));const b=node("button","View document","text-button");b.onclick=()=>openDoc(r.document_id);el.append(content,b);$("reminders-list").append(el);});}catch(e){toast(e.message);}}
function bubble(text,role){const welcome=document.querySelector(".welcome");if(welcome)welcome.remove();const el=node("div",text,"bubble "+role);$("messages").append(el);$("messages").scrollTop=$("messages").scrollHeight;return el;}
$("chat-form").onsubmit=async e=>{
 e.preventDefault();const requestOwner=accountUser?.id;const question=$("question").value.trim();if(question.length<2)return;bubble(question,"user");$("question").value="";$("send").disabled=true;const pending=bubble("Finding supporting passages…","assistant");
 try{const result=await api("/chat",body({question,document_id:$("scope").value||null,conversation_id:currentConversation,language:$("language").value}));if(accountUser?.id!==requestOwner)return;currentConversation=result.conversation_id;$("chat-title").textContent=question.slice(0,70);await loadHistory();pending.textContent=result.answer;pending.append(node("small",result.mode==="extractive"?"Exact source excerpts · no generative model":result.mode+(result.note?" · "+result.note:"")));
 if(status.piper_configured&&result.language==="en"){const speak=node("button","Listen to answer","speak");speak.onclick=async()=>{speak.disabled=true;try{const r=await fetch("/api/speak",body({text:result.answer.slice(0,4000)}));if(!r.ok)throw Error("Voice playback failed. Check Piper setup.");const url=URL.createObjectURL(await r.blob()),audio=document.createElement("audio");audio.controls=true;audio.src=url;audio.onended=()=>URL.revokeObjectURL(url);pending.append(audio);await audio.play();}catch(e){toast(e.message);}finally{speak.disabled=false;}};pending.append(speak);}
 $("sources").replaceChildren();if(!result.sources.length)$("sources").append(node("p","No supporting passages were found."));result.sources.forEach((s,i)=>{const card=node("div",undefined,"source-card");card.append(node("strong","["+(s.source_number||i+1)+"] "+s.filename+" · page "+s.page),node("p",s.text));const open=node("button","Open document ↗");open.onclick=()=>openDoc(s.document_id);card.append(open);$("sources").append(card);});
 }catch(e){pending.textContent=e.message;$("question").value=accountUser?.id===requestOwner?question:"";$("sources").replaceChildren(node("p","No answer was received. Retry your question once the connection is restored."));}finally{$("send").disabled=false;$("messages").scrollTop=$("messages").scrollHeight;}
};
document.querySelectorAll("[data-question]").forEach(b=>b.onclick=()=>{$("question").value=b.dataset.question;$("chat-form").requestSubmit();});
$("record").onclick=async()=>{
 if(recorder&&recorder.state==="recording"){recorder.stop();return;}
 if(!status.whisper_installed){toast("Install the voice extra and FFmpeg to enable Whisper.");return;}
 try{const stream=await navigator.mediaDevices.getUserMedia({audio:true});audioChunks=[];recorder=new MediaRecorder(stream);recorder.ondataavailable=e=>audioChunks.push(e.data);
 recorder.onstop=async()=>{clearTimeout(recorder.timer);stream.getTracks().forEach(t=>t.stop());$("record").classList.remove("recording");$("record").disabled=true;$("voice-status").textContent="Transcribing…";const mime=recorder.mimeType,ext=mime.includes("ogg")?"ogg":mime.includes("mp4")?"m4a":"webm",form=new FormData();form.append("file",new Blob(audioChunks,{type:mime}),"question."+ext);try{const result=await api("/transcribe",{method:"POST",body:form});$("question").value=result.text;$("voice-status").textContent="Check the transcription, then press Ask.";}catch(e){$("voice-status").textContent=e.message;}finally{$("record").disabled=false;}};
 recorder.start();recorder.timer=setTimeout(()=>{if(recorder.state==="recording")recorder.stop();},60000);$("record").classList.add("recording");$("voice-status").textContent="Recording… press again to stop (maximum 60 seconds).";
 }catch(e){toast("Microphone unavailable: "+e.message);}
};
async function loadTraining(){try{const reports=await api("/training");$("training-results").replaceChildren();if(!Object.keys(reports).length)$("training-results").append(node("p","Run the training notebook to generate reports.","no-items"));
 for(const [name,r] of Object.entries(reports)){const card=node("div",undefined,"report");card.append(node("h2",name==="baseline"?"Character TF-IDF classifier":name==="minilm"?"MiniLM document classifier":name==="optional"?"Local model verification":"Pipeline evaluation"));if(r.test){const row=node("div",undefined,"metric-row");for(const [key,label] of [["accuracy","Test accuracy"],["macro_f1","Test macro F1"]]){const v=node("div");v.append(node("strong",(r.test[key]*100).toFixed(1)+"%"),node("small",label));row.append(v);}card.append(row);}if(r.split_sizes)card.append(node("p",Object.entries(r.split_sizes).map(([k,v])=>k+": "+v).join(" · ")+" examples, with disjoint groups."));if(r.diagnostics)card.append(node("p","Fit diagnostics: "+(r.diagnostics.possible_overfit?"possible overfitting":"no large train-validation gap detected")+"; "+(r.diagnostics.possible_underfit?"possible underfitting":"training F1 meets the heuristic threshold")+"."));if(r.metrics)card.append(node("pre",JSON.stringify(r.metrics,null,2)));card.append(node("p",r.warning||"Synthetic results are for demonstration only."));$("training-results").append(card);}
 $("capabilities").replaceChildren();for(const [key,value] of Object.entries(status)){const row=node("div",undefined,"capability");row.append(node("strong",key.replaceAll("_"," ")),node("span",value===null?"Not configured":String(value)));$("capabilities").append(row);}
 }catch(e){toast(e.message);}
}
