"""Translate system messages only; never rewrite stored names or profile data."""
import re
from flask import has_request_context,request

MESSAGES={
 'GitHub временно недоступен. Попробуйте скачать приложение позже':'GitHub is temporarily unavailable. Try downloading the app later',
 'VPN-сервер не подтвердил изменение доступа. Обновите список и повторите при необходимости':'The VPN server did not confirm access changes. Refresh and retry if needed',
 'VPN-сервер не подтвердил лимит трафика. Настройка в панели не сохранена.':'The VPN server did not confirm the traffic quota. The dashboard setting was not saved.',
 'VPN-сервер не подтвердил накопленный расход':'The VPN server did not confirm accumulated usage',
 'VPN-сервер не подтвердил поддержку лимита трафика':'The VPN server did not confirm quota support',
 'VPN-сервер не подтвердил состояние клиента':'The VPN server did not confirm device state',
 'Администратор не найден':'Administrator not found','В группе ещё есть клиенты. Сначала перенесите их в другую группу или отзовите доступ':'The group still has devices. Move or revoke them first',
 'Внутренняя ошибка сервера':'Internal server error','Войдите в кабинет':'Sign in to continue','Выдача для этой группы закрыта':'Issuing is disabled for this group','Группа не найдена':'Group not found','Для выдачи создайте отдельную группу':'Create a separate group for issuing profiles',
 'Доступ приостановлен. Обратитесь к администратору':'Access is paused. Contact your administrator','Запрос уже принадлежит другому устройству':'This request already belongs to another device','Лимит 1–150':'The limit must be 1–150','Лимит должен быть положительным числом байтов или без ограничения':'The quota must be a positive byte count or unlimited','Лимит подключений исчерпан':'The connection limit is reached','Логин уже занят':'The username is already taken','Логин: 3–32 латинских символа':'Username: 3–32 Latin characters','Название должно содержать 1–64 символа':'The name must contain 1–64 characters',
 'Не удалось выдать профиль. Повторите запрос — второй профиль не создастся':'Could not issue the profile. Retry the request; a duplicate profile will not be created','Неверный логин или пароль':'Incorrect username or password','Неверный старый пароль или новый короче 12 символов':'The old password is incorrect or the new password is shorter than 12 characters','Недопустимый источник запроса':'Invalid request origin','Некорректная дата окончания':'Invalid expiry date','Некорректный запрос':'Invalid request','Некорректный режим доступа':'Invalid access mode','Нельзя отключить свою учётную запись':'You cannot disable your own account','Неподдерживаемый вариант установщика':'Unsupported installer variant','Нужен JSON':'JSON is required','Нужен объект JSON':'A JSON object is required','Обновите страницу':'Refresh the page','Основная учётная запись защищена':'The primary account is protected','Основную или свою учётную запись удалить нельзя':'The primary account and your own account cannot be deleted','Отзыв не подтверждён VPN-сервером':'Revocation was not confirmed by the VPN server','Приглашение недоступно':'Invitation unavailable','Проверьте заполненные поля':'Check the entered fields','Проверьте пароль, роль и лимит':'Check the password, role and limit','Профиль не найден':'Profile not found','Профиль уже удалён администратором':'The profile was already deleted by an administrator','Сервис выдачи временно недоступен':'Profile issuing is temporarily unavailable','Слишком много запросов. Повторите позже':'Too many requests. Try again later',
 'Служебная группа со старыми конфигами защищена':'The system group with existing profiles is protected','Сначала завершите выдачу профиля':'Finish issuing the profile first','Сначала закройте кабинет администратора':'Close the administrator account first','Срок выходит за допустимый диапазон дат':'Expiry is outside the supported date range','Срок группы: 1–3650 дней или пустое поле':'Group duration: 1–3650 days or blank','Ссылка недоступна или истекла':'The link is unavailable or expired','Старые конфиги защищены от отзыва панелью':'Existing profiles are protected from dashboard revocation','Старые конфиги защищены: лимит доступен только клиентам панели':'Existing profiles are protected; quotas apply only to dashboard-created devices','Старые конфиги защищены: пауза доступна для клиентов панели':'Existing profiles are protected; pause applies only to dashboard-created devices','Статистика VPN-сервера временно недоступна':'VPN server statistics are temporarily unavailable',
 'Только для главного администратора':'Super administrators only','У администратора ещё есть группы. Сначала перенесите клиентов в другие группы и удалите его пустые группы':'The administrator still has groups. Move devices and remove empty groups first','У администратора ещё есть клиенты. Сначала перенесите их в другие группы':'The administrator still has devices. Move them to other groups first','Укажите лимит трафика':'Enter a traffic quota','Укажите паузу или срок доступа':'Specify pause or expiry','Этот профиль нельзя скачать из панели':'This profile cannot be downloaded from the dashboard','Этот профиль отключён':'This profile is disabled','VPN-сервер временно недоступен':'The VPN server is temporarily unavailable','Ошибка VPN-сервера':'VPN server error'
}


def current_language():
    if not has_request_context():return 'ru'
    for value in (request.headers.get('X-Dashboard-Language'),request.cookies.get('dashboard_lang')):
        if value in {'ru','en'}:return value
    return request.accept_languages.best_match(['ru','en'],default='ru')


def error_text(value):
    if current_language()!='en':return value
    if value in MESSAGES:return MESSAGES[value]
    return 'The request could not be completed. Please review the settings and retry.' if re.search('[А-Яа-яЁё]',str(value)) else value
