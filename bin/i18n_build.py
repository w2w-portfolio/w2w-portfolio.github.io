#!/usr/bin/env python3
# Собирает сайт из шаблонов tpl/ и словарей i18n/<lang>.json.
# Русская версия ложится в корень, остальные — в /<lang>/.
#
# Помимо перевода строк подставляет четыре служебных маркера:
#   {{LANG}}       — код языка в <html lang=...>
#   {{FEED}}       — лента недель из site/tables/weekly.html (строит weekly_report.py)
#   {{BASE}}       — путь к assets/ ('' из корня, '../' из подпапки)
#   {{HREFLANG}}   — ссылки на языковые версии для поисковиков
#   {{LANGSWITCH}} — переключатель в шапке; ссылки готовые, работает без JS
import json, re, sys
from pathlib import Path

# Путь к сайту: рядом со скриптом (в облачной сборке скрипт лежит в
# site/bin/) или на уровень выше (на маке — personal/bin/).
_here = Path(__file__).resolve().parent
SITE  = _here.parent if (_here.parent/'tpl').is_dir() else _here.parent/'site'
PAGES = ['index.html','tickmill.html','results.html','monitor.html','about.html']
LANGS = ['ru','en','es']
NAMES = {'ru':'RU','en':'EN','es':'ES'}
HOST  = 'https://w2w-portfolio.github.io'
KEY   = re.compile(r'\{\{([a-z][a-z0-9_.]*)\}\}')
NUM   = re.compile(r'\{\{#(\d+)\}\}')
# Разделитель тысяч: у русского — неразрывный пробел, у английского запятая,
# у испанского точка. Маркер {{#3801}} в шаблоне разворачивается по языку.
THOUSANDS = {'ru': '\u202f', 'en': ',', 'es': '.'}

def fmt_num(v, lang):
    return f'{int(v):,}'.replace(',', THOUSANDS[lang])

def path_to(lang, page, cur_lang):
    """Относительный путь со страницы cur_lang на ту же страницу языка lang."""
    up = '' if cur_lang == 'ru' else '../'
    return up + ('' if lang == 'ru' else lang + '/') + page

def langswitch(page, cur):
    parts = []
    for L in LANGS:
        cls = ' class="on"' if L == cur else ''
        parts.append(
            f'<a href="{path_to(L, page, cur)}" hreflang="{L}"{cls} '
            f'onclick="try{{localStorage.setItem(\'w2w-lang\',\'{L}\')}}catch(e){{}}">'
            f'{NAMES[L]}</a>')
    return '<div class="langsw" role="group" aria-label="Language">' + ''.join(parts) + '</div>'

def feed_html():
    """Лента недель: готовый кусок от bin/weekly_report.py, ключи в нём
    переводятся дальше общим механизмом."""
    p = SITE / 'tables' / 'weekly.html'
    return p.read_text(encoding='utf-8') if p.exists() else ''


def hreflang(page):
    out = []
    for L in LANGS:
        href = f'{HOST}/' + ('' if L == 'ru' else L + '/') + page
        out.append(f'<link rel="alternate" hreflang="{L}" href="{href}">')
    out.append(f'<link rel="alternate" hreflang="x-default" href="{HOST}/{page}">')
    return '\n'.join(out)

BLOB = re.compile(r'<(svg|script|style)\b.*?</\1>', re.S)
DEC  = re.compile(r'(?<=\d)\.(?=\d{1,2}\b)')

def localize_decimals(html, lang):
    """Десятичный разделитель в числах, зашитых прямо в разметку.

    В испанском дробь пишется через запятую. Трогаем только текст между тегами
    (не атрибуты) и только 1–2 знака после точки: 21.2 -> 21,2, но дата 08.2021
    и разделитель тысяч 1.204 остаются нетронутыми. Применяется к шаблону ДО
    подстановки словаря — переводы уже приходят с правильными разделителями."""
    if lang != 'es': return html
    keep = []
    def stash(m):
        keep.append(m.group(0)); return f'\x00{len(keep)-1}\x00'
    html = BLOB.sub(stash, html)
    html = re.sub(r'>([^<]*)<', lambda m: '>' + DEC.sub(',', m.group(1)) + '<', html)
    return re.sub(r'\x00(\d+)\x00', lambda m: keep[int(m.group(1))], html)

AXIS = re.compile(r'(<text[^>]*>)(.*?)(</text>)', re.S)
def localize_axis(html, lang):
    """Разделитель тысяч в подписях осей: 1000% -> 1,000% / 1.000%.

    Только числа со знаком процента — иначе пострадали бы годы (2021 -> 2.021)."""
    sep = THOUSANDS[lang]
    if lang == 'ru': return html          # русская ось уже читается верно
    def one(m):
        body = re.sub(r'\b(\d)(\d{3})(?=%)', lambda n: n.group(1) + sep + n.group(2), m.group(2))
        return m.group(1) + body + m.group(3)
    return AXIS.sub(one, html)

def build(lang, outdir):
    d  = json.loads((SITE/'i18n'/f'{lang}.json').read_text(encoding='utf-8'))
    ru = json.loads((SITE/'i18n'/'ru.json').read_text(encoding='utf-8'))
    outdir.mkdir(parents=True, exist_ok=True)
    missing = []
    for f in PAGES:
        tpl = (SITE/'tpl'/f).read_text(encoding='utf-8')
        tpl = (tpl.replace('{{LANG}}', lang)
                  .replace('{{BASE}}', '' if lang == 'ru' else '../')
                  .replace('{{HREFLANG}}', hreflang(f))
                  .replace('{{LANGSWITCH}}', langswitch(f, lang))
                  .replace('{{FEED}}', feed_html()))
        # Эпиграф Франклина уже приведён в оригинале, по-английски. На английской
        # странице перевод под ним был бы повтором той же строки — убираем.
        tpl = tpl.replace('{{EPI_TRANS}}',
                          '' if lang == 'en' else
                          '  <p class="epi-ru">{{index.t007}}</p>\n')
        tpl = localize_decimals(tpl, lang)
        tpl = localize_axis(tpl, lang)
        tpl = NUM.sub(lambda m: fmt_num(m.group(1), lang), tpl)
        def rep(m):
            k = m.group(1)
            if k in d: return d[k]
            missing.append(k); return ru.get(k, m.group(0))
        (outdir/f).write_text(KEY.sub(rep, tpl), encoding='utf-8')
    return missing

if __name__ == '__main__':
    langs = sys.argv[1:] or LANGS
    for lang in langs:
        out = SITE if lang == 'ru' else SITE/lang
        miss = build(lang, out)
        note = f'  ⚠ без перевода: {len(miss)}' if miss else ''
        print(f'  {lang} -> {out.relative_to(SITE.parent)}/{note}')
