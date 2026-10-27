/* Read-only administrator QR view of an already issued, authorized profile. */
(function(root,factory){
  const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;else root.ClientQR=api;
})(typeof globalThis!=='undefined'?globalThis:this,function(){
  'use strict';
  let current=null;
  function allowed(d){return Boolean(d&&!d.legacy&&typeof d.id==='string'&&d.id.length<=128&&['active','paused','expired','limited'].includes(d.state));}
  function close(){
    if(!current)return;const s=current;current=null;s.epoch++;
    for(const pending of s.pending){clearTimeout(pending.timer);pending.controller.abort();}
    s.pending.clear();s.cache.clear();s.image.replaceChildren();s.status.textContent='';s.select.onchange=null;s.copy.onclick=null;s.name.textContent='';s.modal.classList.remove('qr-modal');
  }
  async function open({device,doc,dialog,render,fetcher=globalThis.fetch,nav=globalThis.navigator,tr=value=>value}){
    if(!allowed(device)||current?.id===device.id&&current.modal.open)return;
    close();
    dialog(tr('QR-код · ')+device.name,
      '<label>'+tr('Приложение для QR-кода')+'<select id="client-qr-format"><option value="vpn">AmneziaVPN (.vpn)</option><option value="conf">AmneziaWG (.conf)</option></select></label>'+
      '<div class="qr-layout"><div id="client-qr-image" class="qr-image"></div><div><p id="client-qr-status" class="help" role="status"></p>'+
      '<section id="client-qr-naming" hidden><p class="help">'+tr('Имя подключения')+': <strong id="client-qr-name"></strong></p><button type="button" id="client-qr-copy-name" class="small">'+tr('Скопировать имя')+'</button><p class="help">'+tr('AmneziaWG на iPhone попросит ввести имя после сканирования. Вставьте это имя. При импорте .conf имя берётся из названия файла.')+'</p></section>'+
      '<p class="help">'+tr('Откройте сканер QR-кода внутри выбранного приложения на другом устройстве и наведите камеру на этот код.')+'</p>'+
      '<p class="help">'+tr('Это уже выданный профиль. Срок, пауза, лимит трафика и ключи не изменяются.')+'</p>'+
      '<p class="help">'+tr('QR-код содержит ваш приватный ключ. Не публикуйте его и не пересылайте другим людям.')+'</p></div></div>',async()=>{},tr('Закрыть'));
    const s={id:device.id,modal:doc.querySelector('#modal'),image:doc.querySelector('#client-qr-image'),status:doc.querySelector('#client-qr-status'),select:doc.querySelector('#client-qr-format'),name:doc.querySelector('#client-qr-name'),naming:doc.querySelector('#client-qr-naming'),copy:doc.querySelector('#client-qr-copy-name'),pending:new Set(),cache:new Map(),epoch:0};
    current=s;s.modal.classList.add('qr-modal');doc.querySelector('#modal-cancel').hidden=true;s.select.value='vpn';
    s.name.textContent=String(device.name||'AmneziaWG');
    s.copy.onclick=async()=>{try{await nav.clipboard.writeText(s.name.textContent);if(current===s)s.copy.textContent=tr('Имя скопировано');}catch{if(current===s)s.copy.textContent=tr('Выделите и скопируйте имя');}};
    function profile(format){
      if(s.cache.has(format))return s.cache.get(format);
      const item={controller:new AbortController()};item.timer=setTimeout(()=>item.controller.abort(),15000);s.pending.add(item);
      const request=(async()=>{
        const response=await fetcher('/api/devices/'+encodeURIComponent(s.id)+'/download'+(format==='conf'?'?format=conf':''),{credentials:'same-origin',cache:'no-store',signal:item.controller.signal});
        if(!response.ok)throw Error('PROFILE_UNAVAILABLE');
        const value=await response.text();if(value.length>65536)throw Error('PROFILE_UNAVAILABLE');
        return format==='vpn'?value.trim():value;
      })().catch(e=>{s.cache.delete(format);throw e;}).finally(()=>{clearTimeout(item.timer);s.pending.delete(item);});
      s.cache.set(format,request);return request;
    }
    async function update(){
      const epoch=++s.epoch,format=s.select.value;s.image.replaceChildren();s.status.textContent=tr('Готовим QR-код…');s.naming.hidden=format!=='conf';s.copy.textContent=tr('Скопировать имя');
      try{
        if(!['vpn','conf'].includes(format))throw Error('INVALID_FORMAT');
        const value=await profile(format);if(current!==s||!s.modal.open||epoch!==s.epoch)return;
        render(s.image,value,format,tr('QR-код для ')+(format==='vpn'?'AmneziaVPN':'AmneziaWG'));s.status.textContent='';
      }catch(e){
        if(current!==s||!s.modal.open||epoch!==s.epoch)return;
        s.image.replaceChildren();s.status.textContent=tr(e.message==='QR_TOO_LARGE'?'Конфиг слишком большой для одного QR-кода. Скачайте .vpn или .conf в строке клиента.':'Не удалось получить QR-код. Проверьте доступ к клиенту и попробуйте ещё раз.');
      }
    }
    s.select.onchange=update;return update();
  }
  globalThis.addEventListener?.('pagehide',close);
  return {allowed,open,close};
});
