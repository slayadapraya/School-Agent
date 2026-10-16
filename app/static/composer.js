'use strict';
// One composer layout replaces the older nested row/wrapper combinations.
function toolLock(locked){return `<svg class="tool-lock" viewBox="0 0 20 20" aria-hidden="true"><rect x="4" y="8" width="12" height="9" rx="2"/><path d="${locked?'M6 8V5a4 4 0 0 1 8 0v3':'M7 8V5a4 4 0 0 1 7-2'}"/></svg>`;}
function codeToolAvailable(){if(studentView||adminTutorFilters)return false;return state.user?.role==='admin'||!!selectorCache?.models.some(m=>!m.locked&&/coder/i.test(m.key));}
composer=function(){
 const uploads=course()?.policy?.upload_images!==false&&(state.user.role==='admin'||state.user.permissions?.upload_images!==false);
 const research=course()?.policy?.web_research!==false&&(state.user.role==='admin'||state.user.permissions?.web_research!==false);
 const code=codeToolAvailable(),running=busy||!!replyAnimation;
 return `<div class="composer-wrap"><form id="chat-form" class="composer modern-composer"><div class="attachment-tray">${stagedImages.map((f,i)=>`<span class="attachment-chip">▧ ${esc(f.name)}<button type="button" data-staged-image="${i}" aria-label="Remove ${esc(f.name)}">×</button></span>`).join('')}${(pendingImages[active?.id]||[]).map(a=>`<span class="attachment-chip">▧ ${esc(a.name)}<button type="button" data-remove-image="${esc(a.id)}" aria-label="Remove ${esc(a.name)}">×</button></span>`).join('')}</div><input type="file" id="image-upload" accept="image/jpeg,image/png,image/webp,.pdf,.docx,.txt,.md,.csv,.json" multiple hidden><textarea rows="1" aria-label="Ask School Agent" id="message" maxlength="4000" placeholder="Type here…"></textarea><div class="composer-footer"><div class="composer-tool-group">${uploads?'<button type="button" class="tool" data-action="attach" aria-label="Attach files">＋ File / photo</button>':''}${research?'<button type="button" class="tool" data-action="research">⌕ Research</button>':''}<button type="button" class="tool" data-action="sources">▧ Course sources</button><button type="button" class="tool ${code?'is-unlocked':'is-locked'}" data-code-assist="1" aria-disabled="${!code}" title="${code?'Code help':'A teacher must grant access to a coding model'}">${toolLock(!code)}Code</button><button type="button" class="tool is-locked" data-image-assist="1" aria-disabled="true" title="No image generation service is connected">${toolLock(true)}Image</button></div><div class="composer-right-controls"><button type="button" class="tool files-control" data-open-files="1">▤ Files</button><button type="button" data-input-model="1" class="input-model-selector" aria-label="Choose chat model" aria-haspopup="menu" aria-expanded="false">${esc(windowModelLabel||'Choose model')}${adminTutorFilters?' · Student filters':''} ▾</button><button type="${running?'button':'submit'}" class="send composer-send ${running?'is-running':''}" aria-label="${running?'Stop response':'Send message'}" ${running?'data-stop-response="1"':''} ${!running&&(uploadBusy||creatingThread)?'disabled':''}>${running?'■':'↑'}</button></div></div></form><p class="disclosure">Saved to this conversation · Authorised staff can review</p></div>`;
};
function updateSendControl(){const b=document.querySelector('.composer-send');if(!b)return;const running=busy||!!replyAnimation;b.type=running?'button':'submit';b.setAttribute('aria-label',running?'Stop response':'Send message');b.classList.toggle('is-running',running);b.textContent=running?'■':'↑';b.toggleAttribute('data-stop-response',running);b.disabled=!running&&(uploadBusy||creatingThread);}
function closeModelPopover(){document.querySelectorAll('[id="model-popover"]').forEach(el=>el.remove());document.querySelector('[data-input-model]')?.setAttribute('aria-expanded','false');}
chooseInputModel=async function(){
 if(document.getElementById('model-popover')){closeModelPopover();return;}
 const trigger=document.querySelector('[data-input-model]');if(!trigger)return;
 // Mount before requesting models so a second click closes this exact pending picker.
 const preview=studentView,owner=state.user?.id;
 const popup=document.createElement('div');popup.id='model-popover';popup.className='model-popover';popup.setAttribute('role','menu');popup.setAttribute('aria-label','Choose model');
 popup.innerHTML='<div class="model-popover-heading"><span>Model</span><button type="button" data-close-model-picker="1" aria-label="Close model picker">×</button></div><p class="model-popover-label" role="status">Loading models…</p>';
 document.body.append(popup);trigger.setAttribute('aria-expanded','true');const rect=trigger.getBoundingClientRect();popup.style.right=Math.max(10,innerWidth-rect.right)+'px';popup.style.bottom=Math.max(10,innerHeight-rect.top+8)+'px';
 try{
 const data=await api('/api/models'+(preview?'?student_preview=1':''));
 if(!popup.isConnected||document.getElementById('model-popover')!==popup)return;
 if(!trigger.isConnected||state.user?.id!==owner||studentView!==preview){closeModelPopover();return;}selectorCache=data;
 popup.innerHTML=`<div class="model-popover-heading"><span>Model</span><button type="button" data-close-model-picker="1" aria-label="Close model picker">×</button></div>${data.models.map(m=>`<div class="model-choice-row"><button type="button" role="menuitem" data-pick-input-model="${esc(m.key)}" ${m.locked||studentView&&m.key!==data.main?'disabled':''}>${m.locked||studentView&&m.key!==data.main?toolLock(true):''}<span>${esc(m.name)}</span>${m.key===data.selected?'<span aria-hidden="true">✓</span>':''}</button>${!studentView&&state.user.role==='admin'&&m.key===data.main?`<label class="model-student-toggle"><input type="checkbox" id="picker-student-filters" ${adminTutorFilters?'checked':''}>Student filters</label>`:''}</div>`).join('')}`;

 const toggle=popup.querySelector('#picker-student-filters');if(toggle)toggle.onchange=async e=>{const enabled=e.target.checked;try{const lastModel=[...messages].reverse().find(m=>m.role==='assistant'&&m.meta?.model)?.meta.model;const switchModel=enabled&&(data.selected!==data.main||(lastModel&&lastModel!==data.main));const draft=$('#message')?.value||'';const scroll=$('#content')?.scrollTop||0;if(switchModel){await api('/api/models/select',{model:data.main});state=await api('/api/bootstrap');}if(enabled)windowModelLabel=data.models.find(m=>m.key===data.main)?.name||'Main tutor';adminTutorFilters=enabled;closeModelPopover();if(switchModel)selectSubject(active?.course_id||'GENERAL');else{render();if($('#message'))$('#message').value=draft;if($('#content'))$('#content').scrollTop=scroll;}toast(enabled?(switchModel?'Main tutor selected with student filters.':'Student filters on for this chat.'):'Student filters off for this chat.');}catch(err){toast(err.message);e.target.checked=!enabled;}};
 }catch(err){if(popup.isConnected){const status=document.createElement('p');status.className='model-popover-label';status.setAttribute('role','status');status.textContent=err.message;popup.replaceChildren();popup.innerHTML='<div class="model-popover-heading"><span>Model</span><button type="button" data-close-model-picker="1" aria-label="Close model picker">×</button></div>';popup.append(status);}}
};
// Preserve Markdown source when stopping its visible, rendered prefix.
function visibleSourcePrefix(animation){
 const visible=animation.nodes.map(item=>item.node.textContent).join('');const source=animation.source;let position=0;
 for(const character of visible){
  while(position<source.length){
   if(source.startsWith('```',position)){const end=source.indexOf('\n',position);position=end<0?source.length:end+1;continue;}
   if(source.startsWith(character,position)){position+=character.length;break;}
   position++;
  }
 }
 return source.slice(0,position).replace(/[\uD800-\uDBFF]$/,'');
}
async function stopResponse(){
 const animation=replyAnimation;
 if(animation){const draft=$('#message')?.value||'';const scroll=$('#content')?.scrollTop||0;const prefix=visibleSourcePrefix(animation);cancelAnimationFrame(animation.frame);animation.cleanup?.();animation.element.classList.remove('reply-typing');replyAnimation=null;const latest=messages.at(-1);if(latest?.role==='assistant'){latest.content=prefix;latest.meta={...latest.meta,stopped:true};}render();if($('#message'))$('#message').value=draft;if($('#content'))$('#content').scrollTop=scroll;try{await api('/api/chat/stop',{thread_id:animation.threadId,visible_text:prefix});}catch(err){toast(err.message);}return;}
 if(busy&&active?.id){replyStopRequested=true;const b=document.querySelector('.composer-send');if(b){b.disabled=true;b.classList.add('is-stopping');}try{await api('/api/chat/stop',{thread_id:active.id});}catch(err){toast(err.message);updateSendControl();}}
}
document.addEventListener('click',e=>{const b=e.target.closest('button');if(b?.hasAttribute('data-stop-response')){e.preventDefault();e.stopImmediatePropagation();stopResponse();return;}if(document.getElementById('model-popover')&&!e.target.closest('#model-popover')&&!e.target.closest('[data-input-model]'))closeModelPopover();if(b?.dataset.pickInputModel){const checkbox=document.querySelector('#picker-student-filters');if(checkbox)b.dataset.studentFilters=String(checkbox.checked);setTimeout(closeModelPopover,0);}if(b?.dataset.codeAssist){if(!codeToolAvailable())toast('Code help is locked. Ask your teacher for access to a coding model.');else{const input=$('#message');input.value=input.value||'Help me understand and improve this code: ';input.focus();}}if(b?.dataset.imageAssist)toast('Image generation is not connected. File / photo can upload an existing image.');},true);
document.addEventListener('keydown',e=>{if(e.key==='Escape')closeModelPopover();});

// A fast bootstrap can finish before the final deferred script is loaded.
if(state.user&&active&&screen==='chat'){const draft=$('#message')?.value||'';const top=$('#content')?.scrollTop||0;render();if($('#message'))$('#message').value=draft;if($('#content'))$('#content').scrollTop=top;}

// Match content height on desktop and mobile; stop growing at 180px.
function resizeComposerInput(){const input=document.getElementById('message');if(!input)return;input.style.height='34px';const height=Math.max(34,Math.min(180,input.scrollHeight));input.style.height=height+'px';input.style.overflowY=input.scrollHeight>180?'auto':'hidden';}
window.addEventListener('resize',resizeComposerInput);
const renderBeforeInputSizing=render;
render=function(){const result=renderBeforeInputSizing();requestAnimationFrame(resizeComposerInput);return result;};
requestAnimationFrame(resizeComposerInput);

document.addEventListener('keydown',e=>{if(e.key==='Escape'&&document.getElementById('model-popover')){e.preventDefault();closeModelPopover();document.querySelector('[data-input-model]')?.focus({preventScroll:true});}});
document.addEventListener('click',e=>{if(e.target.closest('[data-close-model-picker]')){e.preventDefault();closeModelPopover();}},true);
