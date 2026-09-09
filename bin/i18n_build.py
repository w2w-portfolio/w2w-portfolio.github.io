#!/usr/bin/env python3
"""Собирает сайт из шаблонов tpl/ и словарей i18n/<lang>.json.

    python3 i18n_build.py            все три языка
    python3 i18n_build.py es         только испанский

Русская версия ложится в корень, остальные — в /<lang>/.

Помимо перевода строк подставляет служебные маркеры:
  {{LANG}}       — код языка в <html lang=...>
  {{FEED}}       — лента недель из site/tables/weekly.html (строит weekly_report.py)
  {{LIVE}}       — таблица живых цифр рядом с расчётными (он же)
  {{BASE}}       — путь к assets/ ('' из корня, '../' из подпапки)
  {{HREFLANG}}   — ссылки на языковые версии для поисковиков
  {{LANGSWITCH}} — переключатель в шапке; ссылки готовые, работает без JS
  {{MASTHEAD}}   — логотип из tpl/_masthead.html (общий для всех страниц)
  {{NAV}}        — меню; текущий пункт сборщик подсвечивает сам
  {{TOC}}        — оглавление страницы по секциям с якорем
  {{n.<ключ>}}   — число из расчёта, site/data/numbers.json

Голова страницы тоже общая — tpl/_head.html, {{TITLE}} в ней разворачивается
в ключ заголовка текущей страницы (title.index, title.results и так далее).
"""
import json, re, sys
from pathlib import Path

# Путь к сайту: рядом со скриптом (в облачной сборке скрипт лежит в
# site/bin/) или на уровень выше (на маке — personal/bin/).
_here = Path(__file__).resolve().parent
SITE  = _here.parent if (_here.parent/'tpl').is_dir() else _here.parent/'site'
PAGES = ['index.html','results.html','backtest.html','tickmill.html','about.html',
         'important.html', 'copy-trading-market.html', 'terms.html']
# Меню: главной в нём нет намеренно — на неё ведёт логотип, как принято.
MENU  = [('results.html', 'nav.results'), ('backtest.html', 'nav.backtest'),
         ('tickmill.html', 'nav.connect'), ('terms.html', 'nav.terms'), ('about.html', 'nav.author'),
         # Пункт ведёт на страницу раздела со вступлением и списком
         # материалов; сами материалы лежат отдельными страницами
         # с говорящими адресами.
         ('important.html', 'nav.research')]
LANGS = ['ru','en','es']
NAMES = {'ru':'RU','en':'EN','es':'ES'}
HOST  = 'https://w2w-portfolio.github.io'
# Ключи словаря. Маркеры чисел {{n.<ключ>}} исключены: они не переводятся,
# их подставляет put_numbers уже после словаря — иначе счётчик «без перевода»
# считал бы их пропущенными.
# Дефис в классе обязателен: имена страниц бывают составными
# (title.copy-trading-market), и без него заголовок оставался маркером.
KEY   = re.compile(r'\{\{(?!n\.)([a-z][a-z0-9_.-]*)\}\}')
# Упоминание страницы в тексте: [[backtest]] разворачивается в ссылку с её
# названием на нужном языке. На самоё себя страница не ссылается — остаётся
# просто название. Так читателю не нужно искать, где про это сказано подробно.
LINK  = re.compile(r'\[\[(index|results|backtest|tickmill|about|important|copy-trading-market)\]\]')
NAVKEY = {'index': 'nav.home', 'results': 'nav.results', 'backtest': 'nav.backtest',
          'tickmill': 'nav.connect', 'about': 'nav.author',
          'important': 'nav.research', 'copy-trading-market': 'nav.research'}
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

def nav(page):
    """Меню страницы: текущий пункт получает class="on" и остаётся ссылкой."""
    items = ''.join(
        f'<a href="{href}"{" class=\"on\"" if href == page else ""}>{{{{{key}}}}}</a>'
        for href, key in MENU)
    return f'<nav>{items}</nav>'


OGLOCALE = {'ru': 'ru_RU', 'en': 'en_US', 'es': 'es_ES'}


def shell(page, lang):
    """Голова и шапка страницы — общие куски tpl/_head.html и _masthead.html.

    Заголовок и описание берутся по имени страницы (title.index, desc.index),
    канонический адрес и локаль — по языку. Описание нужно и поисковику,
    и превью ссылки в мессенджерах: без него вместо карточки уходит
    голая строка."""
    slug = page.replace('.html', '')
    head = (SITE/'tpl'/'_head.html').read_text(encoding='utf-8')
    canon = f'{HOST}/' + ('' if lang == 'ru' else lang + '/') + page
    head = (head.replace('{{TITLE}}', '{{title.' + slug + '}}')
                .replace('{{DESC}}', '{{desc.' + slug + '}}')
                .replace('{{CANONICAL}}', canon)
                .replace('{{OGLOCALE}}', OGLOCALE[lang]))
    return head, (SITE/'tpl'/'_masthead.html').read_text(encoding='utf-8')


def links(html, page, d, ru):
    def one(m):
        slug = m.group(1)
        key  = NAVKEY[slug]
        name = d.get(key) or ru.get(key, slug)
        href = slug + '.html'
        return name if href == page else f'<a href="{href}">{name}</a>'
    return LINK.sub(one, html)


def part_html(name):
    """Готовый кусок от bin/weekly_report.py (лента, пульс). Ключи внутри
    переводятся дальше общим механизмом."""
    p = SITE / 'tables' / name
    return p.read_text(encoding='utf-8') if p.exists() else ''


def hreflang(page):
    out = []
    for L in LANGS:
        href = f'{HOST}/' + ('' if L == 'ru' else L + '/') + page
        out.append(f'<link rel="alternate" hreflang="{L}" href="{href}">')
    out.append(f'<link rel="alternate" hreflang="x-default" href="{HOST}/{page}">')
    return '\n'.join(out)

BLOB = re.compile(r'<(svg|script|style)\b.*?</\1>', re.S)
# После дроби не должно идти ни цифры, ни точки: первое отсекает разделитель
# тысяч (1.204), второе — даты (06.10.2025), у которых иначе поехала бы первая
# точка. Граница слова тут не годится: в «1.02R» её между цифрой и буквой нет,
# и числа с R не локализовались вовсе.
DEC  = re.compile(r'(?<=\d)\.(?=\d{1,2}(?![\d.]))')

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

# Числа портфеля берутся из расчёта, а не вбиваются в тексты руками:
# site/data/numbers.json пишет bin/page_numbers.py --json. Формат у каждого
# свой и задан здесь же — «сколько знаков» это свойство числа, а не языка.
NUMFMT = {
    'trades': (0, True), 'total': (0, False), 'per_year': (0, False),
    'pf': (1, False), 'rr': (2, False), 'win_rate': (1, False),
    'avg_win': (2, False), 'avg_loss': (2, False),
    'dd_bal': (1, False), 'dd_eq': (1, False),
    'dd_eq_1000': (0, True), 'dry_days': (0, False),
    'years': (0, False), 'sources': (0, False), 'symbols': (0, False),
    'months': (0, False), 'months_up': (0, False),
    # по алгоритмам
    'total_a1': (0, False), 'total_a2': (0, False),
    'dd_a1': (1, False), 'dd_a2': (1, False), 'dd_a12': (1, False),
    'rdd_a2': (0, False), 'rdd_port': (0, False),
    'both_days': (0, False), 'both_down': (0, False), 'both_exp': (0, False),
    # месяцы и годы
    'month_best': (1, False), 'month_avg': (1, False),
    'y1': (0, False), 'y2': (0, False), 'y3': (0, False),
    'y4': (0, False), 'y5': (0, False), 'years_up': (0, False),
    # золото и просадки источников
    'gold_a1': (0, False), 'gold_a2': (0, False), 'gold_share': (0, False),
    'dd_all': (0, False),
    # после вознаграждения площадки
    'fee_windows': (0, False),
    'fee30': (0, False), 'fee30_lo': (0, False),
    'fee30_mid': (0, False), 'fee30_hi': (0, False),
    'fee20': (0, False), 'fee20_lo': (0, False),
    'fee20_mid': (0, False), 'fee20_hi': (0, False),
}
NUMKEY = re.compile(r'\{\{n\.([a-z][a-z0-9_]*)\}\}')


def numbers():
    """Числа расчёта; пусто, если файл ещё не собран."""
    p = SITE / 'data' / 'numbers.json'
    return json.loads(p.read_text(encoding='utf-8')) if p.exists() else {}


def put_numbers(html, nums, lang, missing):
    """Подстановка {{n.<ключ>}} — после словаря, чтобы числа внутри
    переводов тоже разворачивались."""
    def one(m):
        k = m.group(1)
        if k not in nums or k not in NUMFMT:
            missing.append(f'n.{k}')
            return m.group(0)
        digits, thousands = NUMFMT[k]
        v = f'{nums[k]:.{digits}f}'
        if thousands:
            whole, _, frac = v.partition('.')
            whole = f'{int(whole):,}'.replace(',', THOUSANDS[lang])
            v = whole + (('.' + frac) if frac else '')
        if lang == 'es':
            v = v.replace('.', ',') if not thousands else v
        return v
    return NUMKEY.sub(one, html)


SECT = re.compile(r'<section id="([a-z0-9-]+)">(.*?)</section>', re.S)
H2 = re.compile(r'<h2[^>]*>(.*?)</h2>', re.S)


def toc(html, label):
    """Оглавление страницы из секций, у которых есть якорь.

    Собирается после подстановки словаря — иначе в списке оказались бы
    маркеры вместо заголовков. Секция без h2 в оглавление не идёт:
    ссылаться там не на что."""
    items = []
    for anchor, body in SECT.findall(html):
        m = H2.search(body)
        if not m:
            continue
        title = re.sub(r'<[^>]+>', '', m.group(1)).strip()
        items.append(f'<li><a href="#{anchor}">{title}</a></li>')
    if not items:
        return ''
    return (f'<nav class="toc" aria-label="{label}"><ol>'
            + ''.join(items) + '</ol></nav>')


def build(lang, outdir):
    d  = json.loads((SITE/'i18n'/f'{lang}.json').read_text(encoding='utf-8'))
    ru = json.loads((SITE/'i18n'/'ru.json').read_text(encoding='utf-8'))
    outdir.mkdir(parents=True, exist_ok=True)
    missing = []
    nums = numbers()
    for f in PAGES:
        tpl = (SITE/'tpl'/f).read_text(encoding='utf-8')
        head, mast = shell(f, lang)
        tpl = (tpl.replace('{{HEAD}}', head)
                  .replace('{{MASTHEAD}}', mast)
                  .replace('{{NAV}}', nav(f))
                  .replace('{{LANG}}', lang)
                  .replace('{{BASE}}', '' if lang == 'ru' else '../')
                  .replace('{{HREFLANG}}', hreflang(f))
                  .replace('{{LANGSWITCH}}', langswitch(f, lang))
                  .replace('{{FEED}}', part_html('weekly.html'))
                  .replace('{{LIVE}}', part_html('live.html'))
                  .replace('{{PULSE}}', part_html('pulse.html')))
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
        page = links(KEY.sub(rep, tpl), f, d, ru)
        page = put_numbers(page, nums, lang, missing)
        page = page.replace('{{TOC}}', toc(page, d.get('toc.label', 'Содержание')))
        (outdir/f).write_text(page, encoding='utf-8')
    return missing

def sitemap():
    """Карта сайта: все страницы всех языков, каждая со ссылками на переводы.

    Файл собирается вместе со страницами, поэтому не может от них отстать.
    Даты не ставим: врать «обновлено сегодня» о неизменившейся странице
    хуже, чем не сказать ничего."""
    rows = ['<?xml version="1.0" encoding="UTF-8"?>',
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"',
            '        xmlns:xhtml="http://www.w3.org/1999/xhtml">']
    for lang in LANGS:
        for page in PAGES:
            loc = f'{HOST}/' + ('' if lang == 'ru' else lang + '/') + page
            rows.append(f'  <url>\n    <loc>{loc}</loc>')
            for alt in LANGS:
                href = f'{HOST}/' + ('' if alt == 'ru' else alt + '/') + page
                rows.append(f'    <xhtml:link rel="alternate" hreflang="{alt}" href="{href}"/>')
            rows.append(f'    <xhtml:link rel="alternate" hreflang="x-default" '
                        f'href="{HOST}/{page}"/>')
            rows.append('  </url>')
    rows.append('</urlset>')
    (SITE/'sitemap.xml').write_text('\n'.join(rows) + '\n', encoding='utf-8')

    (SITE/'robots.txt').write_text(
        'User-agent: *\n'
        'Allow: /\n\n'
        f'Sitemap: {HOST}/sitemap.xml\n', encoding='utf-8')
    return len(LANGS) * len(PAGES)


if __name__ == '__main__':
    langs = sys.argv[1:] or LANGS
    for lang in langs:
        out = SITE if lang == 'ru' else SITE/lang
        miss = build(lang, out)
        uniq = sorted(set(miss))
        note = (f'  ⚠ без перевода: {len(miss)} ({", ".join(uniq[:5])}'
                f'{"…" if len(uniq) > 5 else ""})') if miss else ''
        print(f'  {lang} -> {out.relative_to(SITE.parent)}/{note}')
    print(f'  карта сайта: {sitemap()} адресов + robots.txt')
