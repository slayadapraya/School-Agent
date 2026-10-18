'use strict';
// Keep the original checkbox inputs and form handlers: filtering never clears
// an off-screen selection or changes the server's assignment rules.
function enhanceSubjectPicker(container){
 if(container.dataset.subjectEnhanced)return;
 const inputs=[...container.querySelectorAll('input[type=checkbox]')];if(!inputs.length)return;
 container.dataset.subjectEnhanced='1';container.classList.add('grouped-subject-picker');
 const courses=management?.courses||state.courses||[],byId=new Map(courses.map(c=>[c.id,c]));
 const rows=inputs.map(input=>{const c=byId.get(input.value)||{id:input.value,name:input.value};return {input,label:input.closest('label'),category:c.category||c.name,year:String(c.year_level||''),text:(c.id+' '+c.name+' '+(c.category||'')).toLowerCase()};});
 const categories=[...new Set(rows.map(r=>r.category))];let category=rows.some(r=>r.input.checked)?'__selected':categories[0],query='',year='';
 const bar=document.createElement('div');bar.className='subject-picker-controls';
 bar.innerHTML='<div class="subject-search-row"><label>Find a subject<input type="search" placeholder="Name or code" aria-label="Find a subject"></label><label>Year<select aria-label="Filter subject year"><option value="">All years</option>'+[1,2,3,4].map(y=>'<option value="'+y+'">Year '+y+'</option>').join('')+'</select></label></div><div class="subject-category-tags" role="group" aria-label="Subject categories"></div><div class="subject-picker-summary" role="status"></div>';
 const grid=document.createElement('div');grid.className='subject-picker-results';
 rows.forEach(r=>{r.label.classList.add('subject-choice-row');r.label.replaceChildren(r.input);const text=document.createElement('span');text.textContent=r.input.value;const sub=document.createElement('small');sub.textContent=r.year?'Year '+r.year+' · '+r.category:r.category;text.append(sub);r.label.append(text);grid.append(r.label);});
 container.replaceChildren(bar,grid);const tags=bar.querySelector('.subject-category-tags'),summary=bar.querySelector('[role=status]');
 const render=()=>{let shown=0;for(const r of rows){const matches=(!query||r.text.includes(query))&&(!year||r.year===year)&&(query||category==='__all'||category==='__selected'&&r.input.checked||r.category===category);r.label.hidden=!matches;if(matches)shown++;}for(const b of tags.children)b.setAttribute('aria-pressed',String(b.dataset.category===category));summary.textContent=rows.filter(r=>r.input.checked).length+' selected · '+shown+' shown'+(shown?'':' · No matching subjects');};
 for(const [value,label] of [['__selected','Selected'],['__all','All'],...categories.map(c=>[c,c])]){const b=document.createElement('button');b.type='button';b.className='category-tag';b.dataset.category=value;b.textContent=label;b.onclick=()=>{category=value;bar.querySelector('input').value='';query='';render();};tags.append(b);}
 bar.querySelector('input').oninput=e=>{query=e.target.value.trim().toLowerCase();render();};bar.querySelector('select').onchange=e=>{year=e.target.value;render();};container.addEventListener('change',render);container.updateSubjectPicker=render;render();
}
function enhancePeoplePicker(fieldset){
 const labels=[...fieldset.querySelectorAll('label.check-row')];if(!labels.length)return;
 const controls=document.createElement('div');controls.className='people-picker-controls';controls.innerHTML='<label>Find a person<input type="search" placeholder="Search people" aria-label="Search class members"></label><label>Role<select aria-label="Filter class member role"><option value="">Everyone</option><option value="teacher">Teachers</option><option value="student">Students</option><option value="selected">Selected</option></select></label>';
 fieldset.insertBefore(controls,labels[0]);const filter=()=>{const q=controls.querySelector('input').value.toLowerCase(),role=controls.querySelector('select').value;for(const label of labels){const input=label.querySelector('input'),person=management.users.find(u=>u.id===Number(input.value));label.hidden=!label.textContent.toLowerCase().includes(q)||(role==='selected'?!input.checked:!!role&&person?.role!==role);}};controls.oninput=filter;controls.onchange=filter;
}
function enhanceAdminDialog(form){
 if(form.dataset.editorEnhanced)return;form.dataset.editorEnhanced='1';const dialog=form.closest('dialog');dialog.classList.add('admin-editor-dialog');
 const isClass=form.id==='class-form',children=[...form.children],fields=children.filter(c=>c.tagName==='FIELDSET');
 const sections=isClass?[['Details',children.filter(c=>c.tagName==='LABEL')],['Subjects',[fields[0]]],['People',[fields[1]]],['Policies',[fields[2]]]]:[['Details',children.filter(c=>c.classList.contains('form-grid')||c.tagName==='LABEL')],['Subjects',[fields[0]]],['Tools',fields.slice(1)]];
 const tabs=document.createElement('div');tabs.className='editor-section-tabs';tabs.setAttribute('role','tablist');tabs.setAttribute('aria-label',isClass?'Class settings':'Account settings');
 const body=document.createElement('div');body.className='editor-section-body';const footer=document.createElement('div');footer.className='editor-save-bar';
 const panels=[];const select=index=>{panels.forEach((p,i)=>{p.hidden=i!==index;tabs.children[i].setAttribute('aria-selected',String(i===index));tabs.children[i].tabIndex=i===index?0:-1;});body.scrollTop=0;};
 sections.forEach(([title,nodes],i)=>{const section=document.createElement('section');section.id=form.id+'-section-'+i;section.setAttribute('role','tabpanel');section.setAttribute('aria-labelledby',form.id+'-tab-'+i);nodes.filter(Boolean).forEach(n=>section.append(n));body.append(section);panels.push(section);const button=document.createElement('button');button.type='button';button.id=form.id+'-tab-'+i;button.textContent=title;button.setAttribute('role','tab');button.setAttribute('aria-controls',section.id);button.onclick=()=>select(i);button.onkeydown=e=>{if(!['ArrowLeft','ArrowRight','Home','End'].includes(e.key))return;e.preventDefault();const next=e.key==='Home'?0:e.key==='End'?sections.length-1:(i+(e.key==='ArrowRight'?1:-1)+sections.length)%sections.length;select(next);tabs.children[next].focus();};tabs.append(button);});
 for(const child of children)if(child.parentElement===form)footer.append(child);
 form.replaceChildren(tabs,body,footer);form.addEventListener('invalid',e=>{const index=panels.findIndex(p=>p.contains(e.target));if(index>=0)select(index);},true);select(0);
 if(isClass)enhancePeoplePicker(fields[1]);
}
function refreshAdminEditors(){
 for(const container of document.querySelectorAll('.course-checks,.subject-picker'))enhanceSubjectPicker(container);
 for(const form of document.querySelectorAll('#class-form,#account-form'))enhanceAdminDialog(form);
 if(!document.querySelector('#class-form,#account-form'))document.querySelector('#modal')?.classList.remove('admin-editor-dialog');
}
new MutationObserver(records=>{if(records.some(r=>[...r.addedNodes].some(n=>n.nodeType===1)))refreshAdminEditors();}).observe(document.body,{childList:true,subtree:true});
document.querySelector('#modal').addEventListener('close',()=>document.querySelector('#modal').classList.remove('admin-editor-dialog'));
refreshAdminEditors();
document.addEventListener('change',()=>document.querySelectorAll('.grouped-subject-picker').forEach(p=>p.updateSubjectPicker?.()));
