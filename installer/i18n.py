"""Explicit operator-language preference; never translates credentials or plans."""
import json
import locale
from pathlib import Path
import re
import sys

ROOT=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parent))
_language='ru'
_catalog=json.loads((ROOT/'messages_en.json').read_text(encoding='utf-8'))
_cache={}


def set_language(value):
    global _language
    if value=='auto':
        value='en' if (locale.getlocale()[0] or '').lower().startswith('en') else 'ru'
    if value not in {'ru','en'}:raise ValueError('Unsupported language')
    _language=value


def language():return _language


def english(value):
    if value in _cache:return _cache[value]
    result=value
    for source,replacement in sorted(_catalog.items(),key=lambda item:len(item[0]),reverse=True):
        result=re.sub(r'(?<![А-Яа-яЁё])'+re.escape(source)+r'(?![А-Яа-яЁё])',lambda match:replacement,result)
    _cache[value]=result
    return result


def tr(value):return english(value) if _language=='en' else value
