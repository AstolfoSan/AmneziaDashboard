var tr=value=>globalThis.DashboardI18n?globalThis.DashboardI18n.text(value):value;
(function(root,factory){'use strict';const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;else root.ProfileImport=api;})(typeof window==='undefined'?globalThis:window,function(){
  'use strict';
  function platform(nav={}){
    const ua=String(nav.userAgent||'');
    if(/Android/i.test(ua))return 'android';
    if(/iPhone|iPad|iPod/i.test(ua)||(/Macintosh/i.test(ua)&&Number(nav.maxTouchPoints)>1))return 'ios';
    return 'desktop';
  }
  function key(text){
    const value=String(text||'').trim();
    if(value.length>65536||!/^vpn:\/\/[A-Za-z0-9_-]+$/.test(value))throw Error(tr('Некорректный формат профиля AmneziaVPN'));
    return value;
  }
  function prepare(text,nav={},FileType=globalThis.File){
    const value=key(text),os=platform(nav);
    const file=typeof FileType==='function'?new FileType([value+'\n'],'AmneziaVPN.vpn',{type:'text/plain'}):null;
    if(os==='android'){
      const chromium=/Chrome\/|Chromium\/|SamsungBrowser\/|EdgA\//i.test(nav.userAgent||'');
      return {os,file,mode:'android',uri:chromium?'intent://'+value.slice(6)+'#Intent;scheme=vpn;package=org.amnezia.vpn;end':value,
        hint:tr('Откроется AmneziaVPN. Подтвердите добавление конфигурации в приложении. Если приложение не открылось, скачайте .vpn или скопируйте ключ.')};
    }
    let share=false;
    try{share=Boolean(file&&typeof nav.share==='function'&&typeof nav.canShare==='function'&&nav.canShare({files:[file]}));}catch{}
    if(share)return {os,file,mode:'share',hint:os==='ios'?
      tr('Откроется меню iPhone/iPad: выберите AmneziaVPN (при необходимости — «Ещё») и подтвердите импорт. Если её нет в списке, скачайте .vpn и откройте его через «Поделиться».') :
      tr('Выберите AmneziaVPN в системном меню. Если её нет в списке, скачайте файл .vpn и откройте его в приложении.')};
    return {os,file,mode:'download',hint:os==='ios'?
      tr('Браузер не поддерживает передачу файла приложению. Скачаем .vpn: откройте его в «Файлах» → «Поделиться» → AmneziaVPN. Можно открыть эту страницу в Safari.') :
      tr('Скачается файл .vpn. Откройте его в AmneziaVPN; если приложение не выбрано автоматически, используйте «+» → «Файл».')};
  }
  function launch(plan,nav,navigate,download){
    // Must run directly from a click, with the profile already fetched.
    if(plan.mode==='android'){navigate(plan.uri);return Promise.resolve('opened');}
    if(plan.mode==='share')return nav.share({files:[plan.file]}).then(()=>'shared');
    download();return Promise.resolve('downloaded');
  }
  function conf(text){
    const value=String(text||'').trim();
    if(value.length>65536||!value.startsWith('[Interface]\n')||!value.includes('\n[Peer]\n')||/[\u0000-\u0008\u000b\u000c\u000e-\u001f]/.test(value))throw Error('Некорректный формат конфига AmneziaWG');
    return value+'\n';
  }
  function fileName(name){
    let value=String(name||'').normalize('NFC').replace(/[<>:"/\\|?*\x00-\x1F\x7F\u202A-\u202E\u2066-\u2069]/g,'_').replace(/^[.\s]+|[.\s]+$/g,'');
    value=Array.from(value).slice(0,64).join('').replace(/[.\s]+$/g,'');
    if(!value)value='AmneziaWG';
    if(/^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)/i.test(value))value='AmneziaWG-'+value;
    return value+'.conf';
  }
  function prepareConf(text,nav={},FileType=globalThis.File,name){
    const value=conf(text),os=platform(nav),file=typeof FileType==='function'?new FileType([value],fileName(name),{type:'application/octet-stream'}):null;
    let share=false;
    try{share=Boolean(file&&typeof nav.share==='function'&&typeof nav.canShare==='function'&&nav.canShare({files:[file]}));}catch{}
    return {os,file,mode:share?'share':'download',hint:share?
      'Выберите AmneziaWG в системном меню и подтвердите импорт .conf. Затем включите туннель в приложении.':
      'Скачайте .conf, откройте AmneziaWG и импортируйте этот файл. На iPhone можно открыть его через «Файлы» → «Поделиться» → AmneziaWG.'};
  }
  return {platform,key,prepare,launch,conf,prepareConf,fileName};
});
