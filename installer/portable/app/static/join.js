'use strict';
var tr=value=>globalThis.DashboardI18n?globalThis.DashboardI18n.text(value):value;
const $=s=>document.querySelector(s), token=location.pathname.startsWith('/j/')?location.pathname.slice(3):'';
let device,profileRequest=null,confRequest=null,preparedImport=null,preparedAwg=null,selectedClient='vpn';
globalThis.DeviceDownloads?.mount(document,navigator);
globalThis.ClientChoice?.mount(document,navigator,value=>{selectedClient=value;if(device?.ready)prepareImport();});
fetch('/api/downloads').then(async r=>{if(!r.ok)return;const release=await r.json();$('#release-version').textContent=tr('Последняя стабильная версия AmneziaVPN: ')+release.version+' · GitHub';for(const [platform,asset] of Object.entries(release.platforms)){const hint=document.querySelector('[data-download-hint="'+platform+'"]');if(hint)hint.textContent=tr(asset.hint)}}).catch(()=>{});
function error(s){$('#join-error').textContent=s}
function ready(){$('#request-view').classList.add('hidden');$('#ready-view').classList.remove('hidden');$('#issued-expiry').textContent=device&&Object.hasOwn(device,'expires_at')?(device.expires_at==null?tr('При выдаче: без ограничения срока.'):tr('При выдаче доступ до ')+ClientAccess.format(device.expires_at)):'';error('');prepareImport()}
async function request(url,body){let r=await fetch(url,body?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{});let d=await r.json();if(!r.ok)throw Error(d.error||tr('Не удалось выполнить запрос'));return d}
function profile(format='vpn'){
  if(format!=='vpn'&&format!=='conf')return Promise.reject(Error('Unsupported profile format'));
  if(format==='conf'&&confRequest)return confRequest;
  if(format==='vpn'&&profileRequest)return profileRequest;
  const pending=(async()=>{const r=await fetch('/api/receive/'+encodeURIComponent(device.id)+(format==='conf'?'?format=conf':''),{headers:{Authorization:'Bearer '+device.download_token},cache:'no-store'});if(!r.ok){const d=await r.json();throw Error(d.error)}const text=await r.text();return format==='conf'?ProfileImport.conf(text):ProfileImport.key(text)})().catch(e=>{if(format==='conf')confRequest=null;else profileRequest=null;throw e;});
  if(format==='conf')confRequest=pending;else profileRequest=pending;return pending;
}
function saveProfile(text,format='vpn'){
  const href=URL.createObjectURL(new Blob([format==='conf'?text:text+'\n'],{type:'application/octet-stream'})),a=document.createElement('a');
  a.href=href;a.download=format==='conf'?'AmneziaWG.conf':'AmneziaVPN.vpn';a.click();setTimeout(()=>URL.revokeObjectURL(href),1000);
}
async function prepareImport(){
  const awg=selectedClient==='awg',b=$(awg?'#import-awg':'#import-app'),hint=$(awg?'#awg-import-hint':'#import-hint');
  b.disabled=true;b.textContent=tr('Готовим импорт…');hint.textContent=tr('Подготавливаем ваш уже выданный конфиг. Новый клиент не создаётся.');
  try{
    const text=await profile(awg?'conf':'vpn'),plan=awg?ProfileImport.prepareConf(text,navigator):ProfileImport.prepare(text,navigator);
    if(awg)preparedAwg=plan;else preparedImport=plan;
    b.textContent=tr(awg?'Добавить в AmneziaWG ↗':'Добавить в AmneziaVPN ↗');hint.textContent=tr(plan.hint);
  }catch(e){if(awg)preparedAwg=null;else preparedImport=null;b.textContent=tr('Повторить подготовку импорта');hint.textContent=tr('Не удалось подготовить импорт. Попробуйте ещё раз или скачайте файл.');error(e.message);}
  finally{b.disabled=false;}
}
$('#join-form').onsubmit=async e=>{e.preventDefault();let b=$('#get-profile');b.disabled=true;b.textContent=tr('Готовим ваше подключение…');error('');try{if(!device)device={id:crypto.randomUUID(),download_token:Array.from(crypto.getRandomValues(new Uint8Array(32)),b=>b.toString(16).padStart(2,'0')).join(''),name:new FormData(e.target).get('name')};sessionStorage.setItem('join:'+token,JSON.stringify(device));const issued=await request('/api/join/'+encodeURIComponent(token),device);device.expires_at=issued.expires_at??null;device.ready=true;device.at=Date.now();sessionStorage.setItem('join:'+token,JSON.stringify(device));ready()}catch(err){error(err.message)}finally{b.disabled=false;b.textContent=tr('Получить подключение →')}};
function launchImport(awg){
  const plan=awg?preparedAwg:preparedImport,hint=$(awg?'#awg-import-hint':'#import-hint');
  if(!plan){prepareImport();return;}error('');
  try{
    const result=ProfileImport.launch(plan,navigator,uri=>{location.href=uri;},()=>{profile(awg?'conf':'vpn').then(text=>saveProfile(text,awg?'conf':'vpn')).catch(e=>error(e.message));});
    Promise.resolve(result).then(mode=>{if(mode==='shared')hint.textContent=tr(awg?'Файл передан выбранному приложению. Подтвердите импорт в AmneziaWG.':'Файл передан выбранному приложению. Подтвердите импорт в AmneziaVPN.');else if(mode==='downloaded')hint.textContent=tr(plan.hint);})
      .catch(e=>{if(e.name!=='AbortError')error(tr(awg?'Не удалось передать конфиг. Скачайте .conf и импортируйте его в AmneziaWG.':'Не удалось передать конфиг приложению. Скачайте .vpn или скопируйте ключ.'));});
  }catch{error(tr(awg?'Не удалось передать конфиг. Скачайте .conf и импортируйте его в AmneziaWG.':'Не удалось открыть приложение. Скачайте .vpn или скопируйте ключ.'));}
}
$('#import-app').onclick=()=>launchImport(false);
$('#import-awg').onclick=()=>launchImport(true);
$('#download').onclick=async()=>{try{saveProfile(await profile())}catch(e){error(e.message)}};
$('#download-conf').onclick=async()=>{try{saveProfile(await profile('conf'),'conf')}catch(e){error(e.message)}};
$('#copy').onclick=async()=>{try{await navigator.clipboard.writeText(await profile());$('#toast').textContent=tr('Ключ скопирован. Вставьте его в AmneziaVPN через «+».');$('#toast').classList.remove('hidden');setTimeout(()=>$('#toast').classList.add('hidden'),6000)}catch(e){error(tr('Не удалось скопировать ключ. Попробуйте скачать файл .vpn.'))}};
(async()=>{if(!token){$('#join-description').textContent=tr('Попросите администратора прислать приглашение вашей группы. В нём будет кнопка получения персонального конфига.');return}try{let d=await request('/api/join/'+encodeURIComponent(token));$('#join-title').textContent=d.name;$('#join-description').textContent=tr('Вы получили приглашение в эту группу. Введите название устройства и нажмите кнопку ниже. ')+ClientAccess.groupText(d.default_access_days);$('#join-form').classList.remove('hidden');try{device=JSON.parse(sessionStorage.getItem('join:'+token)||'null')}catch{}if(device?.ready&&Date.now()-device.at<86400000)ready();else if(device?.ready){device=null;sessionStorage.removeItem('join:'+token)}}catch(e){$('#join-description').textContent=e.message}})();
