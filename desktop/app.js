const $ = id => document.getElementById(id);
let state = {}, token = '', busy = false, completedShown = '', frameBusy = false;
const clock = seconds => `${Math.floor(seconds/60).toString().padStart(2,'0')}:${Math.floor(seconds%60).toString().padStart(2,'0')}`;
$('today').textContent = new Intl.DateTimeFormat(undefined,{weekday:'long',month:'short',day:'numeric'}).format(new Date());
function toast(message){$('toast').textContent=message;$('toast').style.display='block';setTimeout(()=>$('toast').style.display='none',3500);}
async function command(payload){
  if(busy || !token)return;
  busy=true;
  try{const response=await fetch('/command',{method:'POST',headers:{'Content-Type':'application/json','X-Form-Token':token},body:JSON.stringify(payload)});if(!response.ok)throw Error();}
  catch{toast('Could not update your session. Please try again.');}
  finally{busy=false;}
}
function goal(value){const target=Number(value);if(Number.isInteger(target)&&target>=1&&target<=999)command({target});else{$('target').value=state.target||10;toast('Choose a whole number between 1 and 999.');}}
document.querySelectorAll('[data-exercise]').forEach(button=>button.onclick=()=>command({key:49+Number(button.dataset.exercise)}));
document.querySelectorAll('[data-goal]').forEach(button=>button.onclick=()=>goal(button.dataset.goal));
$('minus').onclick=()=>goal((state.target||10)-1);$('plus').onclick=()=>goal((state.target||10)+1);$('target').onchange=event=>goal(event.target.value);
$('start').onclick=()=>command({key:32});$('log').onclick=()=>command({key:99});
function reset(){if((state.count||state.elapsed)&&!state.completed&&!confirm('Reset this session and clear its progress?'))return;command({key:114});$('complete').close();}
$('reset').onclick=reset;$('again').onclick=reset;$('close').onclick=()=>$('complete').close();
$('camera').onload=()=>{frameBusy=false;$('camera').hidden=false;$('loading').hidden=true;};
$('camera').onerror=()=>{frameBusy=false;};
async function poll(){
  try{
    const response=await fetch('/state');state=await response.json();token=state.token;
    if(!state.ready){$('loading-text').textContent=state.status;$('camera-label').textContent=state.error?'Camera unavailable':'Preparing studio';return;}
    const locked=state.active||state.count>0||state.elapsed>0||!!state.completed;
    document.querySelectorAll('[data-exercise]').forEach(button=>{button.classList.toggle('selected',Number(button.dataset.exercise)===state.selected);button.disabled=locked;button.setAttribute('aria-pressed',Number(button.dataset.exercise)===state.selected);});
    document.querySelectorAll('[data-goal],#minus,#plus,#target').forEach(control=>control.disabled=locked);
    document.querySelectorAll('[data-goal]').forEach(button=>button.classList.toggle('selected',Number(button.dataset.goal)===state.target));
    if(document.activeElement!==$('target'))$('target').value=state.target;
    $('count').innerHTML=`${state.count} <span>/ ${state.target}</span>`;$('timer').textContent=clock(state.elapsed);
    const percentage=Math.round(state.count/state.target*100);$('percent').textContent=percentage+'%';$('progress').style.width=percentage+'%';
    $('feedback').textContent=state.status;$('movement').textContent=state.movement;
    $('camera-label').textContent='Camera connected';$('state-tag').textContent=state.completed?'COMPLETE':state.active?'IN SESSION':locked?'PAUSED':'READY';
    $('start').disabled=!!state.completed;$('start').innerHTML=(state.active?'Pause session':locked?'Resume session':'Start session')+' <span>'+(state.active?'Ⅱ':'↗')+'</span>';
    $('reset').disabled=!locked;$('log').hidden=state.selected===1;$('log').disabled=!state.active;
    $('count-note').textContent=state.selected===1?'Reps count automatically, one per arm.':'Log each finished rep with the button below.';
    if(!frameBusy){frameBusy=true;$('camera').src='/frame?t='+Date.now();}
    if(state.completed&&completedShown!==state.completed){completedShown=state.completed;$('final-count').textContent=state.count;$('final-time').textContent=clock(state.elapsed);$('completed-date').textContent=new Date(state.completed).toLocaleString(undefined,{dateStyle:'long',timeStyle:'short'});$('complete').showModal();}
    if(!state.completed)completedShown='';
  }catch{$('camera-label').textContent='Connection interrupted';}
  finally{setTimeout(poll,180);}
}
poll();
