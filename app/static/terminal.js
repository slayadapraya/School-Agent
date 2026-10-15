'use strict';
let hostTerminal=null;
const renderAdminBeforeTerminal=renderAdminPanel;
renderAdminPanel=async function(){
 await disconnectTerminal();
 if(adminTab!=='terminal')return renderAdminBeforeTerminal();
 if(state.user?.role!=='admin'||studentView)return;
 $('#admin-panel').innerHTML=`<div class="admin-heading"><h1>SSH / Terminal</h1><span class="badge">Administrator only</span></div><p class="muted">Interactive terminal on the computer hosting School Agent. Commands run as the server’s operating-system account.</p><form id="terminal-unlock" class="account-form terminal-unlock"><label>Current account password<input type="password" name="password" autocomplete="current-password" required maxlength="256"></label><button class="primary">Connect to host</button><p class="error" id="terminal-error" role="status"></p></form><section id="host-console" hidden><div class="terminal-toolbar"><span id="terminal-host"></span><button data-terminal-disconnect="1">Disconnect</button></div><div id="terminal-screen" aria-label="Host terminal"></div><p class="muted" id="terminal-status">Connected · disconnects after 5 minutes without input, or 30 minutes total.</p><div class="terminal-keys"><button data-terminal-key="ctrl-c">Ctrl+C</button><button data-terminal-key="tab">Tab</button><button data-terminal-key="up">↑</button><button data-terminal-key="down">↓</button><button data-terminal-key="escape">Esc</button></div></section>`;
 $('#terminal-unlock').onsubmit=async e=>{e.preventDefault();const f=e.target,button=f.querySelector('button');button.disabled=true;try{
 const result=await api('/api/admin/terminal',{action:'open',password:f.elements.password.value});f.elements.password.value='';
 if(!$('#terminal-screen')||adminTab!=='terminal'||screen!=='admin'){await api('/api/admin/terminal',{action:'close',id:result.id});return;}
 f.hidden=true;$('#host-console').hidden=false;$('#terminal-host').textContent=result.user+'@'+result.host;
 const terminal=new Terminal({cursorBlink:false,cursorStyle:'block',cursorInactiveStyle:'outline',fontSize:16,fontFamily:'ui-monospace, SFMono-Regular, Consolas, monospace',scrollback:3000,theme:{background:'#101e19',foreground:'#e3eedb',cursor:'#c4f8a4',cursorAccent:'#101e19',selectionBackground:'#4d705b',black:'#101e19',red:'#ed9292',green:'#9edcaa',yellow:'#e9ce8c',blue:'#9abde9',magenta:'#d6a5df',cyan:'#90d8cf',white:'#d5e2d0',brightBlack:'#6d8f7c',brightRed:'#ffaaaa',brightGreen:'#b3f0ac',brightYellow:'#ffe2a6',brightBlue:'#bdd5ff',brightMagenta:'#ecc0f1',brightCyan:'#adf1e9',brightWhite:'#f4faed'}});
 const fit=new FitAddon.FitAddon();terminal.loadAddon(fit);terminal.open($('#terminal-screen'));fit.fit();
 const connection={id:result.id,terminal,fit,closed:false};hostTerminal=connection;
 const socket=new WebSocket((location.protocol==='https:'?'wss:':'ws:')+'//'+location.host+'/api/admin/terminal-stream?id='+encodeURIComponent(result.id));socket.binaryType='arraybuffer';connection.socket=socket;
 const resize=()=>{if(!connection.closed){fit.fit();if(socket.readyState===WebSocket.OPEN)socket.send(JSON.stringify({cols:terminal.cols,rows:terminal.rows}));}};
 terminal.onData(text=>sendTerminalInput(connection,text));
 socket.onopen=()=>{resize();terminal.focus();$('#terminal-status').textContent='Live connection · 5-minute idle timeout · 30-minute session limit.';};
 socket.onmessage=event=>{if(!connection.closed&&event.data instanceof ArrayBuffer)terminal.write(new Uint8Array(event.data));};
 socket.onerror=()=>finishTerminal(connection,'Could not establish the live terminal connection. Please reconnect.',true);
 socket.onclose=()=>finishTerminal(connection,'Terminal disconnected. Connect again to start a shell.',false);
 connection.resize=new ResizeObserver(resize);connection.resize.observe($('#terminal-screen'));
 terminal.focus();
 }catch(err){if($('#terminal-error'))$('#terminal-error').textContent=err.message;}finally{button.disabled=false;}};
};
function sendTerminalInput(c,text){if(!c.closed&&c.socket?.readyState===WebSocket.OPEN&&text.length<=8192)c.socket.send(JSON.stringify({input:text}));}
async function finishTerminal(c,message,notify){if(c.closed)return;await disconnectTerminal(notify);if($('#terminal-status'))$('#terminal-status').textContent=message;if($('#terminal-unlock'))$('#terminal-unlock').hidden=false;}
async function disconnectTerminal(notify=true){const c=hostTerminal;if(!c)return;hostTerminal=null;c.closed=true;c.resize?.disconnect();c.socket?.close();c.terminal.dispose();if(notify){try{await api('/api/admin/terminal',{action:'close',id:c.id});}catch(e){}}}
document.addEventListener('click',async e=>{const b=e.target.closest('button');if(!b)return;if(b.dataset.terminalDisconnect){await disconnectTerminal();if($('#terminal-unlock'))$('#terminal-unlock').hidden=false;if($('#host-console'))$('#host-console').hidden=true;}if(b.dataset.terminalKey&&hostTerminal){const keys={'ctrl-c':'\x03',tab:'\t',up:'\x1b[A',down:'\x1b[B',escape:'\x1b'};sendTerminalInput(hostTerminal,keys[b.dataset.terminalKey]||'');hostTerminal.terminal.focus();}});
// Closing/navigation also closes the host process; server timeout covers abrupt network loss.
new MutationObserver(()=>{if(hostTerminal&&!document.getElementById('terminal-screen'))disconnectTerminal();}).observe(document.getElementById('app'),{childList:true,subtree:true});
window.addEventListener('pagehide',()=>{if(hostTerminal)fetch('/api/admin/terminal',{method:'POST',headers:{'Content-Type':'application/json','X-School-Agent':'1'},body:JSON.stringify({action:'close',id:hostTerminal.id}),keepalive:true});});
