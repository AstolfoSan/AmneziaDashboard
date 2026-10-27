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
    s.pending.clear();s.cache.clear();s.image.replaceChildren();s.status.textContent='';s.select.onchange=null;s.modal.classList.remove('qr-modal');
  }
  async function open({device,doc,dialog,render,fetcher=globalThis.fetch,tr=value=>value}){
    if(!allowed(device)||current?.id===device.id&&current.modal.open)return;
    close();
    dialog(tr('QR-код · ')+device.name,
      '<label>'+tr('Приложение для QR-кода')+'<select id="client-qr-format"><option value="vpn">AmneziaVPN (.vpn)</option><option value="conf">AmneziaWG (.conf)</option></select></label>'+
      '<div id="client-qr-image" class="qr-image"></div><p id="client-qr-status" class="help" role="status"></p>'+
      '<p class="help">'+tr('Откройте сканер QR-кода внутри выбранного приложения на другом устройстве и наведите камеру на этот код.')+'</p>'+
      '<p class="help">'+tr('Это уже выданный профиль. Срок, пауза, лимит трафика и ключи не изменяются.')+'</p>'+
      '<p class="help">'+tr('QR-код содержит ваш приватный ключ. Не публикуйте его и не пересылайте другим людям.')+'</p>',async()=>{},tr('Закрыть'));
    const s={id:device.id,modal:doc.querySelector('#modal'),image:doc.querySelector('#client-qr-image'),status:doc.querySelector('#client-qr-status'),select:doc.querySelector('#client-qr-format'),pending:new Set(),cache:new Map(),epoch:0};
    current=s;s.modal.classList.add('qr-modal');doc.querySelector('#modal-cancel').hidden=true;s.select.value='vpn';
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
      const epoch=++s.epoch,format=s.select.value;s.image.replaceChildren();s.status.textContent=tr('Готовим QR-код…');
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
