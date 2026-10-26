'use strict';
var tr=value=>globalThis.DashboardI18n?globalThis.DashboardI18n.text(value):value;

const $=s=>document.querySelector(s), token=location.pathname.startsWith('/j/')?location.pathname.slice(3):'';
let device,profileRequest=null,preparedImport=null;
globalThis.DeviceDownloads?.mount(document,navigator);
fetch('/api/downloads').then(async r=>{if(!r.ok)return;const release=await r.json();$('#release-version').textContent=tr('Последняя стабильная версия: ')+release.version+' · GitHub';for(const [platform,asset] of Object.entries(release.platforms)){const hint=document.querySelector('[data-download-hint="'+platform+'"]');if(hint)hint.textContent=tr(asset.hint)}}).catch(()=>{});
function error(s){$('#join-error').textContent=s}
function ready(){$('#request-view').classList.add('hidden');$('#ready-view').classList.remove('hidden');$('#issued-expiry').textContent=device&&Object.hasOwn(device,'expires_at')?(device.expires_at==null?tr('При выдаче: без ограничения срока.'):tr('При выдаче доступ до ')+ClientAccess.format(device.expires_at)):'';error('');prepareImport()}
async function request(url,body){let r=await fetch(url,body?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{});let d=await r.json();if(!r.ok)throw Error(d.error||tr('Не удалось выполнить запрос'));return d}
function profile(){
  if(profileRequest)return profileRequest;
  profileRequest=(async()=>{const r=await fetch('/api/receive/'+device.id,{headers:{Authorization:'Bearer '+device.download_token}});if(!r.ok){const d=await r.json();throw Error(d.error)}return ProfileImport.key(await r.text())})().catch(e=>{profileRequest=null;throw e});
  return profileRequest;
}
function saveProfile(text){
  const href=URL.createObjectURL(new Blob([text+'\n'],{type:'text/plain'})),a=document.createElement('a');
  a.href=href;a.download='AmneziaVPN.vpn';a.click();setTimeout(()=>URL.revokeObjectURL(href),1000);
}
async function prepareImport(){
  const b=$('#import-app');b.disabled=true;b.textContent=tr('Готовим импорт…');$('#import-hint').textContent=tr('Подготавливаем ваш уже выданный конфиг. Новый клиент не создаётся.');
  try{const text=await profile();preparedImport=ProfileImport.prepare(text,navigator);b.textContent=tr('Добавить в AmneziaVPN ↗');$('#import-hint').textContent=preparedImport.hint;}
  catch(e){preparedImport=null;b.textContent=tr('Повторить подготовку импорта');$('#import-hint').textContent=tr('Не удалось подготовить импорт. Попробуйте ещё раз или скачайте файл.');error(e.message);}
  finally{b.disabled=false;}
}
$('#join-form').onsubmit=async e=>{e.preventDefault();let b=$('#get-profile');b.disabled=true;b.textContent=tr('Готовим ваше подключение…');error('');try{if(!device)device={id:crypto.randomUUID(),download_token:Array.from(crypto.getRandomValues(new Uint8Array(32)),b=>b.toString(16).padStart(2,'0')).join(''),name:new FormData(e.target).get('name')};sessionStorage.setItem('join:'+token,JSON.stringify(device));const issued=await request('/api/join/'+encodeURIComponent(token),device);device.expires_at=issued.expires_at??null;device.ready=true;device.at=Date.now();sessionStorage.setItem('join:'+token,JSON.stringify(device));ready()}catch(err){error(err.message)}finally{b.disabled=false;b.textContent=tr('Получить подключение →')}};
$('#import-app').onclick=()=>{
  if(!preparedImport){prepareImport();return;}
  error('');
  try{
    const result=ProfileImport.launch(preparedImport,navigator,uri=>{location.href=uri;},()=>{profile().then(saveProfile).catch(e=>error(e.message));});
    Promise.resolve(result).then(mode=>{if(mode==='shared')$('#import-hint').textContent=tr('Файл передан выбранному приложению. Подтвердите импорт в AmneziaVPN.');else if(mode==='downloaded')$('#import-hint').textContent=preparedImport.hint;})
      .catch(e=>{if(e.name!=='AbortError')error(tr('Не удалось передать конфиг приложению. Скачайте .vpn или скопируйте ключ.'));});
  }catch{error(tr('Не удалось открыть приложение. Скачайте .vpn или скопируйте ключ.'));}
};
$('#download').onclick=async()=>{try{saveProfile(await profile())}catch(e){error(e.message)}};
$('#copy').onclick=async()=>{try{await navigator.clipboard.writeText(await profile());$('#toast').textContent=tr('Ключ скопирован. Вставьте его в AmneziaVPN через «+».');$('#toast').classList.remove('hidden');setTimeout(()=>$('#toast').classList.add('hidden'),6000)}catch(e){error(tr('Не удалось скопировать ключ. Попробуйте скачать файл .vpn.'))}};
(async()=>{if(!token){$('#join-description').textContent=tr('Попросите администратора прислать приглашение вашей группы. В нём будет кнопка получения персонального конфига.');return}try{let d=await request('/api/join/'+encodeURIComponent(token));$('#join-title').textContent=d.name;$('#join-description').textContent=tr('Вы получили приглашение в эту группу. Введите название устройства и нажмите кнопку ниже. ')+ClientAccess.groupText(d.default_access_days);$('#join-form').classList.remove('hidden');try{device=JSON.parse(sessionStorage.getItem('join:'+token)||'null')}catch{}if(device?.ready&&Date.now()-device.at<86400000)ready();else if(device?.ready){device=null;sessionStorage.removeItem('join:'+token)}}catch(e){$('#join-description').textContent=e.message}})();
