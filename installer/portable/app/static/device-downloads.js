var tr=value=>globalThis.DashboardI18n?globalThis.DashboardI18n.text(value):value;
(function(root,factory){'use strict';const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;else root.DeviceDownloads=api;})(globalThis,function(){
  'use strict';
  const names={android:'Android',ios:'iPhone / iPad',windows:'Windows',macos:'macOS',linux:'Linux'};
  function detect(nav={}){
    const ua=String(nav.userAgent||''),platform=String(nav.platform||'');let hint='';
    // Low-entropy information only; no high-entropy hints or external detector.
    try{hint=String(nav.userAgentData?.platform||'');}catch{}
    if(/Windows Phone|IEMobile|CrOS/i.test(ua)||/Chrome OS|Chromium OS/i.test(hint))return null;
    if(/Android/i.test(ua)||/^Android$/i.test(hint))return 'android';
    if(/iPhone|iPad|iPod/i.test(ua+' '+platform)||(/^iOS$/i.test(hint))||
       ((/Macintosh/i.test(ua)||/^MacIntel$/i.test(platform))&&Number(nav.maxTouchPoints)>1))return 'ios';
    if(/Windows NT/i.test(ua)||/^Windows$/i.test(hint)||/^Win/i.test(platform))return 'windows';
    if(/Macintosh|Mac OS X/i.test(ua)||/^macOS$/i.test(hint)||/^Mac/i.test(platform))return 'macos';
    if(/Linux/i.test(ua)||/^Linux$/i.test(hint)||/^Linux/i.test(platform))return 'linux';
    return null;
  }
  function mount(doc,nav={}){
    const main=doc.querySelector('#device-downloads'),other=doc.querySelector('#other-device-downloads'),
      options=doc.querySelector('#other-device-options'),notes=doc.querySelector('#other-device-notes'),caption=doc.querySelector('#device-download-caption');
    if(!main||!other||!options||!notes||!caption)return null;
    const os=detect(nav);caption.textContent=os?tr('Для вашего устройства: ')+names[os]:tr('Выберите приложение для вашего устройства.');
    // Move the original links, never rebuild URLs or affect issued profiles.
    // Repeated mounting also restores cards/extras to the appropriate location.
    for(const link of doc.querySelectorAll('[data-device-os]'))(os&&link.dataset.deviceOs!==os?options:main).append(link);
    const extras=doc.querySelector('#device-download-notes');
    if(extras)for(const extra of doc.querySelectorAll('[data-device-extra]'))(os&&extra.dataset.deviceExtra!==os?notes:extras).append(extra);
    main.classList.toggle('device-matched',Boolean(os));other.hidden=!os;other.open=false;
    return os;
  }
  return {detect,mount};
});
