
const $=s=>document.querySelector(s), $$=s=>[...document.querySelectorAll(s)];
let token=sessionStorage.getItem("neura_token")||"";
let sessionId=localStorage.getItem("neura_session")||crypto.randomUUID();
localStorage.setItem("neura_session",sessionId);
let speak=localStorage.getItem("neura_speak")==="1";
let internetApproved=false;
const headers=()=>({"Content-Type":"application/json","Authorization":`Bearer ${token}`});
async function api(url,opt={}){const r=await fetch(url,{...opt,headers:{...headers(),...(opt.headers||{})}});const d=await r.json().catch(()=>({}));if(!r.ok)throw new Error(d.detail||"Errore");return d}
function showApp(){ $("#login").classList.add("hidden");$("#app").classList.remove("hidden");checkModel()}
if(token)showApp();
$("#loginBtn").onclick=async()=>{try{const r=await fetch("/api/login",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({password:$("#password").value})});if(!r.ok)throw 0;token=(await r.json()).token;sessionStorage.setItem("neura_token",token);showApp()}catch{$("#loginError").textContent="Password errata"}}
const titles={chat:["Conversazione","Parla con NÈURA"],conversations:["Chat passate","Cerca e riprendi"],library:["Libreria","Documenti e conoscenza"],vision:["Visione","Analisi immagini locale"],constitution:["Costituzione","Regole fondamentali"],dashboard:["Panoramica","Stato e attività"],memories:["Memorie","Informazioni ricordate"],diary:["Diario","Note e riflessioni"],laboratory:["Laboratorio","Proposte di miglioramento"],versions:["Versioni","Storico dell'apprendimento"],backups:["Backup","Copie di sicurezza"],settings:["Impostazioni","Preferenze dell'interfaccia"]};
async function openView(name){$$(".nav").forEach(x=>x.classList.toggle("active",x.dataset.view===name));$$(".view").forEach(x=>x.classList.toggle("active",x.id===`view-${name}`));[$("#viewTitle").textContent,$("#viewSubtitle").textContent]=titles[name];$(".sidebar").classList.remove("open");if(name==="conversations")loadConversations();if(name==="library")loadLibrary();if(name==="constitution")loadConstitution();if(name==="dashboard")loadDashboard();if(name==="memories")loadMemories();if(name==="diary")loadDiary();if(name==="laboratory")loadLab();if(name==="versions")loadVersions();if(name==="backups"){loadBackups();loadCodeBackups()}if(name==="settings")loadProviderSettings()}
$$(".nav").forEach(x=>x.onclick=()=>openView(x.dataset.view));$("#menuBtn").onclick=()=>$(".sidebar").classList.toggle("open");
function msg(role,text,id){const a=document.createElement("article");a.className=`message ${role}`;if(role==="assistant"){a.innerHTML='<div class="avatar">N</div>';const b=document.createElement("div");b.className="message-body";b.textContent=text;if(id){const f=document.createElement("div");f.className="feedback";[["Utile",1],["Da migliorare",-1]].forEach(([l,r])=>{const bt=document.createElement("button");bt.textContent=l;bt.onclick=async()=>{const note=r<0?(prompt("Cosa doveva capire meglio?")||""):"";await api("/api/feedback",{method:"POST",body:JSON.stringify({message_id:id,rating:r,note})});f.textContent="Feedback salvato"};f.append(bt)});b.append(f)}a.append(b)}else{const b=document.createElement("div");b.className="message-body";b.textContent=text;a.append(b)}$("#messages").append(a);$("#messages").scrollTop=$("#messages").scrollHeight;if(role==="assistant"&&speak)speechSynthesis.speak(new SpeechSynthesisUtterance(text));return a}
async function send(){const t=$("#message").value.trim();if(!t)return;$("#message").value="";msg("user",t);$("#sendBtn").disabled=true;const wait=msg("assistant","Sto riflettendo…");try{const d=await api("/api/chat",{method:"POST",body:JSON.stringify({session_id:sessionId,message:t,use_web:internetApproved,internet_approved:internetApproved})});wait.remove();msg("assistant",d.answer,d.message_id);internetApproved=false;updateWebButton()}catch(e){wait.querySelector(".message-body").textContent=e.message}finally{$("#sendBtn").disabled=false}}
$("#sendBtn").onclick=send;$("#message").onkeydown=e=>{if(e.key==="Enter"&&!e.shiftKey){e.preventDefault();send()}};
async function checkModel(){try{const d=await (await fetch("/api/model-status")).json();$("#modelDot").classList.toggle("ready",d.ready);$("#modelStatus").textContent=d.ready?`${d.model} pronto`:"Motore da configurare"}catch{}}
setInterval(checkModel,15000);
async function loadDashboard(){const d=await api("/api/dashboard");const cards=[["Conversazioni",d.conversations],["Memorie",d.memories],["Feedback utili",d.positive_feedback],["Da migliorare",d.negative_feedback],["Aggiornamenti",d.updates],["Note diario",d.diary_entries]];$("#stats").innerHTML=cards.map(([a,b])=>`<div class="stat"><strong>${b}</strong><span>${a}</span></div>`).join("");drawChart(d.timeline)}
function drawChart(rows){const c=$("#activityChart"),x=c.getContext("2d"),dpr=devicePixelRatio||1,w=c.clientWidth||700,h=180;c.width=w*dpr;c.height=h*dpr;x.scale(dpr,dpr);x.clearRect(0,0,w,h);const max=Math.max(1,...rows.map(r=>r.value));x.strokeStyle=getComputedStyle(document.documentElement).getPropertyValue("--border");x.beginPath();x.moveTo(0,h-20);x.lineTo(w,h-20);x.stroke();x.strokeStyle=getComputedStyle(document.documentElement).getPropertyValue("--text");x.lineWidth=2;x.beginPath();rows.forEach((r,i)=>{const px=rows.length<2?w/2:i*w/(rows.length-1),py=h-20-(r.value/max)*(h-40);i?x.lineTo(px,py):x.moveTo(px,py)});x.stroke()}
async function loadMemories(){const d=await api("/api/memories");$("#memoryList").innerHTML=d.memories.map(m=>`<div class="item"><div class="item-head"><strong>${esc(m.content)}</strong><button data-del="${m.id}" class="secondary">Dimentica</button></div><div class="meta">${m.kind} · importanza ${m.importance}/10</div></div>`).join("");$$("[data-del]").forEach(b=>b.onclick=async()=>{await api(`/api/memories/${b.dataset.del}`,{method:"DELETE"});loadMemories()})}
$("#saveMemory").onclick=async()=>{const content=$("#newMemory").value.trim();if(!content)return;await api("/api/memories",{method:"POST",body:JSON.stringify({content,kind:"secret",importance:9})});$("#newMemory").value="";loadMemories()}
async function loadDiary(){const d=await api("/api/diary");$("#diaryList").innerHTML=d.entries.map(e=>`<div class="item"><strong>${esc(e.title)}</strong><p>${esc(e.content)}</p><div class="meta">${e.created_at}</div></div>`).join("")}
$("#newDiaryBtn").onclick=()=>$("#diaryEditor").classList.toggle("hidden");$("#saveDiary").onclick=async()=>{await api("/api/diary",{method:"POST",body:JSON.stringify({title:$("#diaryTitle").value,content:$("#diaryContent").value})});$("#diaryTitle").value=$("#diaryContent").value="";$("#diaryEditor").classList.add("hidden");loadDiary()}
async function loadLab(){
  const [d,l]=await Promise.all([api("/api/lab/proposals"),api("/api/coding/lessons")]);
  $("#lessonList").innerHTML=l.lessons.slice(0,8).map(x=>`<div class="item"><strong>${esc(x.category)}</strong><p>${esc(x.lesson)}</p><div class="meta">${Math.round(x.confidence*100)}% · ${x.source}</div></div>`).join("");
  $("#proposalList").innerHTML=d.proposals.map(p=>{
    const files=(p.changes||[]).map(c=>c.path).join(", ")||"nessun file";
    const valid=p.validation&&p.validation.tests_passed;
    return `<div class="item proposal">
      <div class="item-head"><strong>${esc(p.title)}</strong><span class="meta">${esc(p.status)} · rischio ${esc(p.risk)}</span></div>
      <p>${esc(p.rationale)}</p>
      <div class="meta">File: ${esc(files)}</div>
      <details><summary>Modifiche, test e validazione</summary>
        <p><strong>Risultato atteso:</strong> ${esc(p.expected_result)}</p>
        <pre>${esc(JSON.stringify(p.changes||[],null,2))}</pre>
        <pre>${esc((p.tests||[]).join("\n"))}</pre>
        <pre>${esc(p.validation?.test_output||JSON.stringify(p.validation||{},null,2))}</pre>
      </details>
      <div class="item-actions">
        <button data-validate="${p.id}" class="secondary">Prova in sicurezza</button>
        <button data-approve="${p.id}" ${valid?"":"disabled"}>Approva</button>
        <button data-apply="${p.id}" ${p.status==="approved"?"":"disabled"}>Applica</button>
        <button data-reject="${p.id}" class="secondary">Rifiuta</button>
      </div></div>`}).join("");
  $$("[data-validate]").forEach(b=>b.onclick=async()=>{b.disabled=true;try{await api(`/api/lab/proposals/${b.dataset.validate}/validate`,{method:"POST"});await loadLab()}catch(e){alert(e.message)}});
  $$("[data-approve]").forEach(b=>b.onclick=async()=>{await api(`/api/lab/proposals/${b.dataset.approve}`,{method:"PATCH",body:JSON.stringify({status:"approved"})});loadLab()});
  $$("[data-reject]").forEach(b=>b.onclick=async()=>{await api(`/api/lab/proposals/${b.dataset.reject}`,{method:"PATCH",body:JSON.stringify({status:"rejected"})});loadLab()});
  $$("[data-apply]").forEach(b=>b.onclick=async()=>{
    const id=b.dataset.apply,confirmation=prompt(`Per applicare la modifica scrivi esattamente: APPLICA ${id}`);
    if(!confirmation)return;
    try{const r=await api(`/api/lab/proposals/${id}/apply`,{method:"POST",body:JSON.stringify({confirmation})});alert(`Modifica applicata. Backup: ${r.snapshot}. Riavvia NÈURA.`);loadLab()}catch(e){alert(e.message)}
  });
}
$("#createProposal").onclick=async()=>{const goal=$("#labGoal").value.trim();if(!goal)return;$("#createProposal").disabled=true;try{await api("/api/lab/proposals",{method:"POST",body:JSON.stringify({goal})});$("#labGoal").value="";loadLab()}finally{$("#createProposal").disabled=false}}
async function loadVersions(){const d=await api("/api/update/versions");$("#versionList").innerHTML=d.versions.map(v=>`<div class="item"><div class="item-head"><strong>${v.version}</strong><span class="meta">${v.status}</span></div><p>${esc(v.summary)}</p><div class="meta">${v.created_at}</div></div>`).join("")}
$("#updateBtn").onclick=async()=>{if(!confirm("Avviare il consolidamento dell'apprendimento?"))return;$("#updateBtn").disabled=true;try{const d=await api("/api/update",{method:"POST"});alert(`Aggiornamento ${d.version} completato`)}finally{$("#updateBtn").disabled=false}}
async function loadBackups(){const d=await api("/api/backups");$("#backupList").innerHTML=d.backups.map(b=>`<div class="item"><strong>${b.filename}</strong><div class="meta">${Math.round(b.size/1024)} KB · ${b.created_at}</div></div>`).join("")}
$("#backupBtn").onclick=async()=>{await api("/api/backup",{method:"POST"});loadBackups()}
function applyTheme(dark){document.documentElement.dataset.theme=dark?"dark":"light";localStorage.setItem("neura_theme",dark?"dark":"light");$("#darkSwitch").checked=dark;$("#themeToggle").textContent=dark?"Tema chiaro":"Tema scuro"}
applyTheme(localStorage.getItem("neura_theme")==="dark");$("#themeToggle").onclick=()=>applyTheme(document.documentElement.dataset.theme!=="dark");$("#darkSwitch").onchange=e=>applyTheme(e.target.checked);$("#speakSwitch").checked=speak;$("#speakSwitch").onchange=e=>{speak=e.target.checked;localStorage.setItem("neura_speak",speak?"1":"0")}
$("#newSession").onclick=newChat
$("#voiceBtn").onclick=()=>{const R=window.SpeechRecognition||window.webkitSpeechRecognition;if(!R)return alert("La dettatura non è supportata da questo browser.");const r=new R();r.lang="it-IT";r.onresult=e=>{$("#message").value=e.results[0][0].transcript};r.start()}
function esc(s=""){return String(s).replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]))}

async function loadCodeBackups(){const d=await api("/api/code-backups");$("#codeBackupList").innerHTML=d.backups.map(b=>`<div class="item"><div class="item-head"><strong>${b.filename}</strong><button class="secondary" data-rollback="${b.filename}">Rollback</button></div><div class="meta">${Math.round(b.size/1024)} KB · ${b.created_at}</div></div>`).join("")||'<div class="meta">Nessuno snapshot del codice.</div>';$$('[data-rollback]').forEach(b=>b.onclick=async()=>{if(!confirm('Ripristinare questo snapshot? Verrà creato prima un backup di sicurezza. Dopo il rollback dovrai riavviare NÈURA.'))return;const d=await api(`/api/code-backups/${encodeURIComponent(b.dataset.rollback)}/rollback`,{method:'POST'});alert(`Ripristino completato. Riavvia NÈURA. Backup di sicurezza: ${d.safety_snapshot}`)})}
$("#codeBackupBtn").onclick=async()=>{await api("/api/code-backups",{method:"POST"});loadCodeBackups()}

$("#saveCodingLesson").onclick=async()=>{
  const lesson=$("#codingLesson").value.trim();if(!lesson)return;
  await api("/api/coding/lessons",{method:"POST",body:JSON.stringify({lesson,category:"manual",confidence:.85})});
  $("#codingLesson").value="";loadLab();
};
$("#diagnosticBtn").onclick=async()=>{
  const d=await api("/api/self-diagnostic",{method:"POST"});
  $("#diagnosticResult").classList.remove("hidden");
  $("#diagnosticResult").textContent=`${d.status}: ${d.report}`;
};

function updateWebButton(){const b=$("#webAskBtn");if(!b)return;b.textContent=internetApproved?"Internet: autorizzato":"Internet: no";b.classList.toggle("active",internetApproved)}
$("#webAskBtn").onclick=()=>{if(internetApproved){internetApproved=false}else{internetApproved=confirm("Autorizzi NÈURA ad accedere a Internet esclusivamente per il prossimo messaggio?")}updateWebButton()};updateWebButton();

async function loadConversations(q=""){
  const d=await api(`/api/conversations?q=${encodeURIComponent(q)}`);
  $("#conversationList").innerHTML=d.conversations.map(c=>`<div class="item conversation-row" data-open-chat="${c.session_id}"><div class="item-head"><strong>${esc(c.title)}</strong><span class="meta">${c.message_count||""} messaggi</span></div><p>${esc(c.snippet||"")}</p><div class="meta">${c.updated_at}</div><div class="item-actions"><button class="secondary" data-rename-chat="${c.session_id}">Rinomina</button><button class="secondary" data-archive-chat="${c.session_id}">${c.archived?"Ripristina":"Archivia"}</button><button class="secondary" data-delete-chat="${c.session_id}">Elimina</button></div></div>`).join("")||'<div class="meta">Nessuna conversazione trovata.</div>';
  $$('[data-open-chat]').forEach(x=>x.onclick=async e=>{if(e.target.closest('button'))return;await openConversation(x.dataset.openChat)});
  $$('[data-rename-chat]').forEach(b=>b.onclick=async()=>{const title=prompt('Nuovo titolo');if(title){await api(`/api/conversations/${b.dataset.renameChat}/title`,{method:'PATCH',body:JSON.stringify({title})});loadConversations($("#chatSearch").value)}});
  $$('[data-archive-chat]').forEach(b=>b.onclick=async()=>{const row=d.conversations.find(x=>x.session_id===b.dataset.archiveChat);await api(`/api/conversations/${b.dataset.archiveChat}/archive`,{method:'PATCH',body:JSON.stringify({archived:!row.archived})});loadConversations()});
  $$('[data-delete-chat]').forEach(b=>b.onclick=async()=>{if(confirm('Eliminare definitivamente questa chat?')){await api(`/api/conversations/${b.dataset.deleteChat}`,{method:'DELETE'});loadConversations()}})
}
async function openConversation(id){const d=await api(`/api/conversations/${id}`);sessionId=id;localStorage.setItem('neura_session',id);$("#messages").innerHTML='';d.messages.forEach(m=>msg(m.role,m.content,m.role==='assistant'?m.id:null));openView('chat')}
let chatTimer;$("#chatSearch").oninput=e=>{clearTimeout(chatTimer);chatTimer=setTimeout(()=>loadConversations(e.target.value),250)};
function newChat(){sessionId=crypto.randomUUID();localStorage.setItem('neura_session',sessionId);$("#messages").innerHTML='<article class="message assistant"><div class="avatar">N</div><div class="message-body">Nuova conversazione avviata.</div></article>';openView('chat')}
$("#newChatTop").onclick=newChat;

async function loadLibrary(){const d=await api('/api/library');$("#libraryList").innerHTML=d.documents.map(x=>`<div class="item"><div class="item-head"><strong>${esc(x.filename)}</strong><span class="meta">${x.learned?'Studiato':'Solo lettura'}</span></div><div class="meta">${esc(x.category)} · ${x.char_count} caratteri · ${x.created_at}</div></div>`).join('')||'<div class="meta">La libreria è vuota.</div>'}
$("#libraryUploadBtn").onclick=async()=>{const f=$("#libraryFile").files[0];if(!f)return alert('Scegli un file');const fd=new FormData();fd.append('file',f);fd.append('category',$("#libraryCategory").value||'Generale');fd.append('learn',$("#libraryLearn").checked?'true':'false');const b=$("#libraryUploadBtn");b.disabled=true;try{const r=await fetch('/api/library/upload',{method:'POST',headers:{Authorization:`Bearer ${token}`},body:fd});const d=await r.json();if(!r.ok)throw new Error(d.detail||'Errore');$("#libraryStatus").classList.remove('hidden');$("#libraryStatus").textContent=`${d.filename} acquisito: ${d.characters} caratteri.`;loadLibrary()}catch(e){alert(e.message)}finally{b.disabled=false}}

async function loadConstitution(){const d=await api('/api/constitution');$("#constitutionText").value=d.content}
$("#saveConstitution").onclick=async()=>{if(!confirm('Salvare queste regole fondamentali?'))return;await api('/api/constitution',{method:'PUT',body:JSON.stringify({content:$("#constitutionText").value})});alert('Costituzione salvata')}

$("#visionAnalyzeBtn").onclick=async()=>{const f=$("#visionFile").files[0];if(!f)return alert('Scegli un’immagine');const fd=new FormData();fd.append('file',f);fd.append('question',$("#visionQuestion").value||'Descrivi accuratamente questa immagine.');const b=$("#visionAnalyzeBtn");b.disabled=true;$("#visionResult").classList.remove('hidden');$("#visionResult").textContent='Analisi in corso…';try{const r=await fetch('/api/vision/analyze',{method:'POST',headers:{Authorization:`Bearer ${token}`},body:fd});const d=await r.json();if(!r.ok)throw new Error(d.detail||'Errore');$("#visionResult").textContent=d.answer}catch(e){$("#visionResult").textContent=e.message}finally{b.disabled=false}}


let providerCatalog={};
async function loadProviderSettings(){
  try{
    const d=await api('/api/provider-config');providerCatalog=d.providers||{};
    const sel=$('#providerSelect');
    sel.innerHTML=Object.entries(providerCatalog).map(([k,v])=>`<option value="${esc(k)}">${esc(v.label)}</option>`).join('');
    sel.value=d.provider||'custom';
    $('#providerBase').value=d.api_base||'';$('#providerModel').value=d.model||'';$('#providerVision').value=d.vision_model||'';$('#providerKey').value='';
    const box=$('#providerStatusBox');box.classList.remove('hidden');box.textContent=d.has_api_key?`Configurazione attiva (${d.source}). La chiave è già salvata.`:'Nessuna chiave API salvata.';
  }catch(e){const box=$('#providerStatusBox');box.classList.remove('hidden');box.textContent=e.message}
}
$('#providerSelect').onchange=e=>{const p=providerCatalog[e.target.value];if(!p)return;$('#providerBase').value=p.api_base||'';$('#providerModel').value=p.model||'';$('#providerVision').value=p.vision_model||p.model||''};
$('#saveProvider').onclick=async()=>{const b=$('#saveProvider'),box=$('#providerStatusBox');b.disabled=true;box.classList.remove('hidden');box.textContent='Salvataggio…';try{const d=await api('/api/provider-config',{method:'PUT',body:JSON.stringify({provider:$('#providerSelect').value,api_base:$('#providerBase').value,api_key:$('#providerKey').value,model:$('#providerModel').value,vision_model:$('#providerVision').value})});box.textContent='Configurazione salvata. Ora prova la connessione.';$('#providerKey').value='';checkModel()}catch(e){box.textContent=e.message}finally{b.disabled=false}};
$('#testProvider').onclick=async()=>{const b=$('#testProvider'),box=$('#providerStatusBox');b.disabled=true;box.classList.remove('hidden');box.textContent='Connessione al modello…';try{const d=await api('/api/provider-test',{method:'POST'});box.textContent=`Connessione riuscita: ${d.status.model}`;checkModel()}catch(e){box.textContent=`Test non riuscito: ${e.message}`}finally{b.disabled=false}};
