var tr=value=>globalThis.DashboardI18n?globalThis.DashboardI18n.text(value):value;
(function(root,factory){
  'use strict';
  if(typeof module==='object'&&module.exports)module.exports=factory();
  else root.ClientAccess=factory();
})(typeof globalThis!=='undefined'?globalThis:this,function(){
  'use strict';
  function format(seconds){
    return new Date(seconds*1000).toLocaleString((globalThis.DashboardI18n?.locale()||'ru-RU'),{
      timeZone:'Europe/Moscow',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'
    })+tr(' МСК');
  }
  function input(seconds){
    return seconds==null?'':new Date(seconds*1000+10800000).toISOString().slice(0,16);
  }
  function parse(value){
    if(!value)return null;
    if(!/^\d{4}-\d\d-\d\dT\d\d:\d\d$/.test(value))throw Error(tr('Укажите дату и время окончания'));
    const result=Date.parse(value+':00+03:00')/1000;
    if(!Number.isInteger(result)||result<946684800||result>4133969999||input(result)!==value)
      throw Error(tr('Проверьте дату окончания (2000–2100, время МСК)'));
    return result;
  }
  function deadline(device){
    if(device.legacy)return '';
    return '<small class="access-deadline">'+(device.expires_at==null?tr('Без срока'):tr('До ')+format(device.expires_at))+'</small>';
  }
  function badge(state){
    if(state==='paused')return tr('<span class="badge access-paused">Приостановлен</span>');
    if(state==='expired')return tr('<span class="badge warn">Срок истёк</span>');
    return '';
  }
  function expired(device,now=Date.now()/1000){
    return device.expires_at!=null&&Number(device.expires_at)<=now;
  }
  function quotaExceeded(device){return device.state==='limited'||device.traffic_limit_bytes!=null&&Number(device.rx||0)+Number(device.tx||0)>=device.traffic_limit_bytes;}
  function manageable(device){return !device.legacy&&['active','paused','expired','limited'].includes(device.state);}
  function accessCell(device,now=Date.now()/1000){
    if(device.state==='revoked')return tr('<span class="badge off">Отозван</span>');
    if(device.manual_paused||device.state==='paused')return tr('<span class="badge access-paused">Приостановлен</span><small>Ручная пауза</small>');
    if(expired(device,now)||device.state==='expired')return tr('<span class="badge warn">Приостановлен</span><small>Срок истёк</small>');
    if(quotaExceeded(device))return tr('<span class="badge warn">Приостановлен</span><small>Лимит трафика</small>');
    if(device.state!=='active')return tr('<span class="badge off">Не выдан</span>');
    return tr('<span class="badge access-allowed">Разрешён</span>');
  }
  function termCell(device,now=Date.now()/1000){
    if(device.legacy)return tr('<span class="muted">Не задан в панели</span>');
    if(device.expires_at==null)return tr('<span>Без срока</span>');
    return '<span class="access-term">'+format(device.expires_at)+'</span>'+(expired(device,now)?tr('<small class="access-expired">Срок истёк</small>'):'');
  }
  function actions(device){
    if(device.legacy||device.state==='revoked')return '';
    const disabled=manageable(device)?'':tr(' disabled title="Сначала завершите выдачу профиля"');
    const pauseLabel=device.manual_paused?(expired(device)||quotaExceeded(device)?tr('Снять паузу'):tr('Возобновить доступ')):tr('Приостановить доступ');
    return '<button class="small" data-pause="'+device.id+'"'+disabled+'>'+pauseLabel+'</button>'+
      '<button class="small" data-expiry="'+device.id+'"'+disabled+tr('>Срок</button>')+
      '<button class="small" data-traffic="'+device.id+'"'+disabled+tr('>Трафик</button>');
  }
  function pauseForm(device){
    const resuming=Boolean(device.manual_paused);
    return '<p>'+(resuming?tr('Снять ручную паузу для этого клиента?'):tr('VPN-доступ этого клиента будет приостановлен, но он останется в списке.'))+'</p>'+
      tr('<p class="help">Клиент, статистика и прежний .vpn сохранятся. Дата окончания доступа не изменится.</p>')+
      (resuming&&expired(device)?tr('<div class="notice warn">Срок доступа уже истёк. Снятие ручной паузы не продлит его: отдельно измените дату кнопкой «Срок».</div>'):'')+
      (resuming&&quotaExceeded(device)?tr('<div class="notice warn">Лимит трафика исчерпан. Для подключения увеличьте или снимите его кнопкой «Трафик».</div>'):'')+
      (resuming?tr('<p class="help">После возобновления переподключите VPN в приложении — прежний .vpn менять не нужно.</p>'):'');
  }
  function expiryForm(device){
    return tr('<label>Дата окончания доступа · МСК')+
      '<input name="expires_local" type="datetime-local" min="2000-01-01T03:00" max="2100-12-31T23:59" value="'+input(device.expires_at)+'"></label>'+
      '<div class="expiry-options"><button type="button" id="expiry-unlimited" class="small expiry-unlimited" aria-pressed="'+(device.expires_at==null)+tr('">∞ Бесконечно</button>')+
      '<span id="expiry-mode" class="help" role="status">'+(device.expires_at==null?tr('Без срока.'):tr('До указанной даты.'))+tr(' Нажмите «Сохранить срок», чтобы применить.</span></div>')+
      tr('<p class="help">«Бесконечно» очищает дату окончания. Если дата задана, по её наступлении VPN-сервер автоматически приостановит доступ (проверка каждые 15 секунд), даже если панель недоступна.</p>')+
      tr('<p class="help">Клиент, статистика и прежний .vpn сохранятся. Ручная пауза не снимается продлением даты.</p>')+
      (device.manual_paused?tr('<div class="notice warn">Сейчас включена ручная пауза. Чтобы разрешить подключение, отдельно нажмите «Возобновить доступ» после изменения срока.</div>'):'');
  }
  function parseDays(value){
    const text=String(value??'').trim();
    if(!text)return null;
    if(!/^\d+$/.test(text)||Number(text)<1||Number(text)>3650)throw Error(tr('Укажите 1–3650 дней или оставьте поле пустым'));
    return Number(text);
  }
  function groupForm(days){
    const value=Number.isInteger(days)&&days>=1&&days<=3650?String(days):'';
    return tr('<label>Срок новых клиентов · дней<input name="default_access_days" type="number" min="1" max="3650" step="1" placeholder="Без срока" value="')+value+'"></label>'+
      tr('<p class="help">Например, 30 — каждый новый клиент получит доступ на 30 дней с момента создания профиля. Пустое поле — без срока. Уже выданные клиенты и их даты не изменятся.</p>');
  }
  function groupText(days){
    return days==null?tr('Новые клиенты: без срока.'):tr('Новые клиенты: ')+days+tr(' дн. с момента выдачи.');
  }
  const TRAFFIC_UNITS={b:1,mb:1024**2,gb:1024**3,tb:1024**4};
  function trafficInputs(limit){
    if(limit==null)return {amount:'',unit:'gb'};
    for(const unit of ['tb','gb','mb']){const amount=Number((limit/TRAFFIC_UNITS[unit]).toFixed(3));if(amount>0&&Math.round(amount*TRAFFIC_UNITS[unit])===limit)return {amount:String(amount),unit};}
    return {amount:String(limit),unit:'b'};
  }
  function parseTraffic(value,unit){
    if(!Object.hasOwn(TRAFFIC_UNITS,unit))throw Error(tr('Выберите единицу трафика'));
    const text=String(value??'').trim().replace(',','.');if(!text)return null;
    if(!/^\d+(\.\d{1,3})?$/.test(text))throw Error(tr('Укажите положительный лимит, до трёх знаков после запятой'));
    const bytes=Math.round(Number(text)*TRAFFIC_UNITS[unit]);
    if(!Number.isSafeInteger(bytes)||bytes<1)throw Error(tr('Лимит трафика вне допустимого диапазона'));
    return bytes;
  }
  function trafficSummary(device,bytes){
    if(device.legacy)return '';
    const limit=device.traffic_limit_bytes,used=Number(device.rx||0)+Number(device.tx||0);
    if(limit==null)return tr('<small>Без лимита трафика</small>');
    return tr('<small class="quota-summary">Всего ')+bytes(used)+tr(' из ')+bytes(limit)+'</small><progress class="quota-progress" max="'+limit+'" value="'+Math.min(limit,used)+tr('" aria-label="Использованный трафик"></progress>');
  }
  function trafficForm(device,bytes){
    const initial=trafficInputs(device.traffic_limit_bytes),used=Number(device.rx||0)+Number(device.tx||0);
    return tr('<div class="traffic-limit-fields"><label>Общий лимит<input name="traffic_amount" type="text" inputmode="decimal" maxlength="24" value="')+initial.amount+tr('" placeholder="Без лимита" autocomplete="off"></label>')+
      tr('<label>Единица<select name="traffic_unit">')+Object.entries({mb:tr('МБ'),gb:tr('ГБ'),tb:tr('ТБ'),b:tr('Б')}).map(([unit,name])=>'<option value="'+unit+'" '+(unit===initial.unit?'selected':'')+'>'+name+'</option>').join('')+'</select></label></div>'+
      '<div class="expiry-options"><button type="button" id="traffic-unlimited" class="small expiry-unlimited" aria-pressed="'+(device.traffic_limit_bytes==null)+tr('">∞ Без лимита</button><span id="traffic-mode" class="help" role="status">Изменение применяется после сохранения.</span></div>')+
      tr('<p class="help">Уже использовано: ')+bytes(used)+tr('. Лимит — скачано + отправлено за всё время наблюдения. Расход не обнуляется при смене лимита, паузе или продлении срока. 1 ГБ = 1024 МБ.</p>')+
      tr('<p class="help">Лимит ниже уже использованного объёма сразу приостановит доступ. Проверка на VPN-сервере каждые 15 секунд; трафик между проверками может превысить порог.</p>')+
      tr('<p class="help">Клиент, статистика и прежний .vpn сохраняются. Увеличение или снятие лимита не снимает ручную паузу и не продлевает срок доступа.</p>');
  }
  return {format,input,parse,deadline,badge,expired,manageable,quotaExceeded,accessCell,termCell,actions,pauseForm,expiryForm,parseDays,groupForm,groupText,trafficInputs,parseTraffic,trafficSummary,trafficForm};
});
