(function (root, factory) {
  'use strict';
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.DeviceGroups = factory();
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';
  const collapsed = new Set();
  const escape = value => String(value ?? '').replace(/[&<>"']/g, c =>
    ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
  const counter = (value, fallback = 0) => value != null && Number.isFinite(Number(value)) &&
    Number(value) >= 0 ? Number(value) : fallback;

  function model(devices = [], groups = [], query = '') {
    const needle = String(query).trim().toLocaleLowerCase('ru');
    const byId = new Map();
    const fallback = new Map();
    // API group totals include retained revoked clients. Never re-sum the
    // filtered rows over them; old/missing metadata can fall back to all rows.
    for (const device of devices) {
      const key = String(device.group_id);
      if (!fallback.has(key)) fallback.set(key, {rx:0, tx:0});
      const usage = fallback.get(key);
      usage.rx += counter(device.rx); usage.tx += counter(device.tx);
    }
    for (const group of groups) {
      if (group.deleted_at != null) continue;
      const usage = fallback.get(String(group.id)) || {rx:0, tx:0};
      byId.set(String(group.id), {
        id: group.id, name: group.name, owner_id: group.owner_id,
        owner_name: group.owner_name || 'Администратор', devices: [], total: 0,
        rx:counter(group.rx, usage.rx), tx:counter(group.tx, usage.tx)
      });
    }
    for (const device of devices) {
      if (device.state === 'revoked') continue;
      const key = String(device.group_id);
      // Never silently lose a visible client if metadata is temporarily missing.
      if (!byId.has(key)) byId.set(key, {
        id: device.group_id, name: device.group_name || 'Без названия',
        owner_id: device.owner_id, owner_name: device.owner_name || 'Администратор',
        devices: [], total: 0, ...fallback.get(key)
      });
      const group = byId.get(key);
      group.total++;
      const haystack = [device.name, group.name, group.owner_name].join(' ').toLocaleLowerCase('ru');
      if (!needle || haystack.includes(needle)) group.devices.push(device);
    }
    return [...byId.values()].filter(group => !needle || group.devices.length ||
      [group.name, group.owner_name].join(' ').toLocaleLowerCase('ru').includes(needle));
  }

  function administrators(groups) {
    const byId = new Map();
    for (const group of groups) {
      const key = group.owner_id == null ? 'unknown-group:' + group.id : String(group.owner_id);
      if (!byId.has(key)) byId.set(key, {id:key, name:group.owner_name, groups:[], count:0, rx:0, tx:0});
      const admin = byId.get(key);
      admin.groups.push(group);
      admin.count += group.devices.length;
      admin.rx += counter(group.rx); admin.tx += counter(group.tx);
    }
    return [...byId.values()];
  }

  function remember(details) {
    const key = details.dataset.deviceDisclosure;
    // Search temporarily expands results, without overwriting the normal view.
    if (!key || details.dataset.deviceSearch === 'true') return;
    if (details.open) collapsed.delete(key);
    else collapsed.add(key);
  }

  function html(devices, groups, options = {}) {
    const searching = Boolean(String(options.query || '').trim());
    const all = administrators(model(devices, groups));
    const tree = searching ? administrators(model(devices, groups, options.query)) : all;
    const adminTotals = new Map(all.map(admin => [admin.id, admin]));
    const formatBytes = options.bytes || (value => counter(value).toLocaleString('ru') + ' Б');
    const traffic = (usage, scope) => '<div class="device-traffic" title="' +
      escape(scope + ' · с начала наблюдения панелью, включая сохранённый расход отозванных клиентов. Поиск не изменяет суммы.') + '">' +
      '<span class="device-traffic-total">За всё время: <strong>' + escape(formatBytes(usage.rx + usage.tx)) +
      '</strong></span><span class="device-traffic-directions">' +
      '<span class="traffic-down" title="Скачано клиентами">↓ ' + escape(formatBytes(usage.tx)) + '</span>' +
      '<span class="traffic-up" title="Отправлено клиентами">↑ ' + escape(formatBytes(usage.rx)) + '</span></span></div>';
    const attrs = key => ' data-device-disclosure="' + escape(key) + '"' +
      (searching ? ' data-device-search="true"' : '') + (searching || !collapsed.has(key) ? ' open' : '');
    const arrow = '<span class="device-chevron" aria-hidden="true">›</span>';
    if (!tree.length) return '<div class="empty">' +
      (searching ? 'Ничего не найдено. Попробуйте имя клиента, администратора или название группы.' :
        'Пока нет групп. Создайте группу и выдайте первое приглашение.') + '</div>';
    return '<div class="device-groups">' + tree.map(admin =>
      '<details class="device-admin"' + attrs('admin:' + admin.id) + '>' +
      '<summary class="device-admin-head">' + arrow + '<div class="device-heading">' +
      '<div class="eyebrow">Администратор</div><h2>' + escape(admin.name) + '</h2></div>' +
      '<div class="device-head-stats"><span class="badge off">Групп: ' + admin.groups.length + ' · Клиентов: ' + admin.count +
      '</span>' + traffic(adminTotals.get(admin.id), 'Трафик всех групп администратора') +
      '</div></summary><div class="device-admin-body">' + admin.groups.map(group =>
        '<details class="device-group"' + attrs('group:' + group.id) + '>' +
        '<summary class="device-group-head">' + arrow + '<div class="device-heading">' +
        '<div class="eyebrow">Группа</div><h3>' + escape(group.name) + '</h3></div>' +
        '<div class="device-head-stats"><span class="badge off">' + (searching ? 'Найдено: ' + group.devices.length + ' из ' +
          group.total : 'Клиентов: ' + group.total) + '</span>' + traffic(group, 'Трафик клиентов этой группы') +
        '</div></summary>' +
        (group.devices.length ? options.table(group.devices, true) :
          '<div class="empty">В этой группе пока нет клиентов.</div>') + '</details>'
      ).join('') + '</div></details>'
    ).join('') + '</div>';
  }

  return {model, administrators, html, remember};
});
