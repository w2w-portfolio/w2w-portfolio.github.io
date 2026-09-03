#!/usr/bin/env python3
"""Еженедельный отчёт по живому счёту: свой аналог страницы сигнала MQL5.

    python3 bin/weekly_report.py             собрать отчёт на сегодня
    python3 bin/weekly_report.py --dry       посчитать и показать, ничего не писать
    python3 bin/weekly_report.py --pulse      только пульс: состояние счёта на сейчас
    python3 bin/weekly_report.py --drop-demo убрать из архива все записи демо-счёта

Демо-период нужен, чтобы проверить расчёт живой торговлей, но в витрину
для инвестора он не идёт: на сайт выводятся только записи реального счёта.
Пока реального нет, лента честно помечена как демонстрационная.

Читает то, что наблюдатель TC_Watch выложил из терминала:
    MQL5/Files/w2w_status.json   сводка счёта на момент снимка
    MQL5/Files/w2w_trades.csv    все закрытые сделки

Считает неделю (пн-вс той даты, что задана или текущей), дописывает запись
в архив PLATFORMS/../data/weekly.json и строит две кривые в site/charts:
доходность и просадку от максимума. Архив накапливается — из него потом
и берётся лента на странице «Контроль».

Пороги просадки берутся ОТСЮДА и больше ниоткуда, чтобы страница,
наблюдатель и МОНИТОРИНГ.md не разъезжались.
"""
import csv, json, os, sys
from datetime import datetime, timedelta
from pathlib import Path

# Отчёты наблюдателя приезжают с VDS через Яндекс.Диск (задание w2w_sync.bat
# копирует их из папки терминала в синхронизируемую папку). Если там пусто —
# берём из локального терминала: так работает, когда торгуем с мака.
# Папка терминала на VDS подключена к Яндекс.Диску напрямую
# (Настройки → Автоматическое сохранение папок), поэтому файлы
# приезжают сами, без копировальщиков и заданий.
YD  = Path.home() / 'Yandex.Disk.localized' / 'Компьютер WIN-G1OC1NJFU3O' / 'Files'
LOC = (Path.home() / 'Library' / 'Application Support'
       / 'net.metaquotes.wine.metatrader5' / 'drive_c'
       / 'Program Files' / 'MetaTrader 5' / 'MQL5' / 'Files')
# В облачной сборке путь задаётся переменной W2W_DATA — там файлы,
# скачанные с публичной ссылки Яндекс.Диска.
ENV = os.environ.get('W2W_DATA')
if ENV:
    MT5 = Path(ENV)
else:
    MT5 = YD if (YD / 'w2w_status.json').exists() else LOC
# Куда писать: в облаке скрипт лежит в site/bin/ и всё складывается
# в сам репозиторий; на маке — в personal/site/.
_here = Path(__file__).resolve().parent
SITE = _here.parent if (_here.parent/'tpl').is_dir() else _here.parent/'site'
ARCHIVE = SITE / 'data' / 'weekly.json'
CHARTS = SITE / 'charts'
TABLES = SITE / 'tables'

DD_OK, DD_WATCH, DD_RARE = 25.0, 36.0, 44.0     # см. МОНИТОРИНГ.md, пересчёт 03.09.2026
EXPECTED_PER_MONTH = 63                          # ожидаемый поток портфеля


def load_status():
    p = MT5 / 'w2w_status.json'
    if not p.exists():
        raise SystemExit(f'нет сводки наблюдателя: {p}\nтерминал запущен?')
    return json.loads(p.read_text(encoding='utf-8'))


def load_trades():
    p = MT5 / 'w2w_trades.csv'
    if not p.exists():
        return []
    rows = []
    for r in csv.DictReader(p.read_text(encoding='utf-8').splitlines(), delimiter=';'):
        try:
            rows.append(dict(
                t=datetime.strptime(r['close_time'], '%Y.%m.%d %H:%M:%S'),
                symbol=r['symbol'], magic=int(r['magic']),
                volume=float(r['volume']), money=float(r['money'])))
        except (ValueError, KeyError):
            continue
    return sorted(rows, key=lambda x: x['t'])


def curve(trades, start_balance):
    """Кривая баланса и просадки от максимума, в процентах депозита."""
    pts, cum, peak = [], 0.0, 0.0
    for tr in trades:
        cum += tr['money']
        peak = max(peak, cum)
        pts.append(dict(t=tr['t'],
                        grow=100.0 * cum / start_balance,
                        dd=100.0 * (peak - cum) / start_balance))
    return pts


def svg_line(pts, key, color, title, fname, invert=False):
    """Простая кривая без библиотек: у нас всего один график на показатель."""
    W, H, PAD = 720, 240, 34
    CHARTS.mkdir(parents=True, exist_ok=True)
    if len(pts) < 2:
        body = (f'<text x="{W/2}" y="{H/2}" text-anchor="middle" fill="#8b959f" '
                f'font-family="system-ui" font-size="13">данных пока нет</text>')
        (CHARTS / fname).write_text(
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" '
            f'role="img" aria-label="{title}">{body}</svg>', encoding='utf-8')
        return
    ys = [p[key] for p in pts]
    lo, hi = min(ys + [0.0]), max(ys + [0.0])
    if hi - lo < 1e-9:
        hi = lo + 1
    def X(i): return PAD + (W - 2 * PAD) * i / (len(pts) - 1)
    def Y(v):
        f = (v - lo) / (hi - lo)
        return H - PAD - (H - 2 * PAD) * (1 - f if invert else f)
    d = ' '.join(f'{"M" if i == 0 else "L"}{X(i):.1f},{Y(v):.1f}'
                 for i, v in enumerate(ys))
    zero = Y(0.0)
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" '
           f'role="img" aria-label="{title}">'
           f'<line x1="{PAD}" y1="{zero:.1f}" x2="{W-PAD}" y2="{zero:.1f}" '
           f'stroke="#39424c" stroke-width="1"/>'
           f'<path d="{d}" fill="none" stroke="{color}" stroke-width="2" '
           f'stroke-linejoin="round"/>'
           f'<text x="{PAD}" y="{PAD-12}" fill="#8b959f" font-family="system-ui" '
           f'font-size="12">{title}</text>'
           f'<text x="{W-PAD}" y="{PAD-12}" text-anchor="end" fill="#8b959f" '
           f'font-family="system-ui" font-size="12">{ys[-1]:+.1f}%</text>'
           f'</svg>')
    (CHARTS / fname).write_text(svg, encoding='utf-8')


def render_feed(arch):
    """Лента недель для страницы «Контроль» — готовый кусок разметки."""
    TABLES.mkdir(parents=True, exist_ok=True)
    real = [a for a in arch if a.get('account_type') == 'real']
    demo_only = bool(arch) and not real
    if real:
        arch = real                      # реал появился — демо в витрину не идёт
    if not arch or all(a['trades_total'] == 0 for a in arch):
        html = ('<p class="muted">{{monitor.t020}}</p>')
        (TABLES / 'weekly.html').write_text(html, encoding='utf-8')
        return
    rows = []
    for a in reversed(arch):                       # свежие сверху
        cls = {'норма': 'ok', 'внимание': 'warn',
               'разбор': 'warn', 'стоп': 'bad'}.get(a['level'], 'ok')
        # уровень выводим ключом: на англ. и исп. страницах он переводится
        key = {'норма': 'monitor.t028', 'внимание': 'monitor.t029',
               'разбор': 'monitor.t030', 'стоп': 'monitor.t031'}.get(a['level'], 'monitor.t028')
        money = a['money_week']
        r = ' style="text-align:right"'
        rows.append(
            f"<tr><th>{a['week_from']} — {a['week_to']}</th>"
            f"<td{r}>{a['trades_week']}</td>"
            f"<td{r}>{money:+,.0f}</td>"
            f"<td{r}>{a['grow_total_pct']:+.1f}%</td>"
            f"<td{r}>{a['dd_now_pct']:.1f}%</td>"
            f'<td{r}><span class="lvl {cls}">{{{{{key}}}}}</span></td></tr>')
    head = '<p class="note">{{monitor.t027}}</p>' if demo_only else ''
    R = ' style="text-align:right"'
    html = (head + '<div class="scroll"><table class="feed">'
            '<thead><tr>'
            '<th>{{monitor.t021}}</th>'
            f'<th{R}>{{{{monitor.t022}}}}</th><th{R}>{{{{monitor.t023}}}}</th>'
            f'<th{R}>{{{{monitor.t024}}}}</th><th{R}>{{{{monitor.t025}}}}</th>'
            f'<th{R}>{{{{monitor.t026}}}}</th>'
            '</tr></thead><tbody>' + ''.join(rows) + '</tbody></table></div>')
    (TABLES / 'weekly.html').write_text(html, encoding='utf-8')


def render_pulse(st, trades, base):
    """Пульс: состояние счёта на сейчас. Обновляется чаще ленты — раз в час,
    поэтому видно, что счёт живой, а не замер неделю назад."""
    TABLES.mkdir(parents=True, exist_ok=True)
    snap = st.get('time', '')
    stale = ''
    try:                                    # время снимка — по часам торгового сервера
        t = datetime.strptime(snap, '%Y.%m.%d %H:%M:%S')
        hours = (datetime.now() - t).total_seconds() / 3600
        if hours > 24:
            stale = '<p class="warnbox">{{monitor.t040}}</p>'
    except ValueError:
        hours = 0

    pts = curve(trades, base)
    dd = pts[-1]['dd'] if pts else 0.0
    grow = pts[-1]['grow'] if pts else 0.0
    cells = [
        ('{{monitor.t033}}', f"{st.get('balance', 0):,.0f}"),
        ('{{monitor.t034}}', f"{st.get('equity', 0):,.0f}"),
        ('{{monitor.t035}}', f"{st.get('open_positions', 0)}"),
        ('{{monitor.t036}}', f"{st.get('deals', 0)}"),
        ('{{monitor.t037}}', f"{grow:+.1f}%"),
        ('{{monitor.t038}}', f"{dd:.1f}%"),
    ]
    # плитки — тот же компонент, что на остальных страницах сайта
    cards = ''.join(f'<div class="tile"><span class="k">{k}</span>'
                    f'<span class="v">{v}</span></div>' for k, v in cells)
    html = (stale + f'<div class="tiles">{cards}</div>'
            f'<p class="note">{{{{monitor.t039}}}} {snap}</p>')
    (TABLES / 'pulse.html').write_text(html, encoding='utf-8')
    return snap, hours


def week_bounds(day):
    start = day - timedelta(days=day.weekday())          # понедельник
    return (datetime.combine(start, datetime.min.time()),
            datetime.combine(start + timedelta(days=7), datetime.min.time()))


def drop_demo():
    """Убрать демо-записи: делается один раз, при переходе на реальный счёт."""
    if not ARCHIVE.exists():
        print('архива нет, чистить нечего'); return
    arch = json.loads(ARCHIVE.read_text(encoding='utf-8'))
    keep = [a for a in arch if a.get('account_type') == 'real']
    ARCHIVE.write_text(json.dumps(keep, ensure_ascii=False, indent=1), encoding='utf-8')
    render_feed(keep)
    print(f'убрано записей демо: {len(arch) - len(keep)}, осталось {len(keep)}')
    print('графики пересоберутся при следующем запуске отчёта')


def main():
    if '--drop-demo' in sys.argv:
        drop_demo(); return
    if '--pulse' in sys.argv:
        st = load_status()
        trades = load_trades()
        base = float(st.get('start_balance') or st.get('balance') or 0) or 1.0
        snap, hours = render_pulse(st, trades, base)
        print(f'пульс: снимок {snap} ({hours:.1f} ч назад)')
        print(f"  баланс {st.get('balance'):,.2f}  эквити {st.get('equity'):,.2f}"
              f"  позиций {st.get('open_positions')}  закрытых {st.get('deals')}")
        return
    dry = '--dry' in sys.argv
    st = load_status()
    src = ('переменная W2W_DATA' if os.environ.get('W2W_DATA')
           else 'VDS через Яндекс.Диск' if MT5 == YD else 'локальный терминал')
    print(f'источник: {src}  ({MT5})')
    trades = load_trades()
    base = float(st.get('start_balance') or st.get('balance') or 0) or 1.0

    now = datetime.now()
    w_from, w_to = week_bounds(now.date())
    week = [t for t in trades if w_from <= t['t'] < w_to]

    wins = [t for t in week if t['money'] > 0]
    losses = [t for t in week if t['money'] <= 0]
    gp = sum(t['money'] for t in wins)
    gl = -sum(t['money'] for t in losses)

    pts = curve(trades, base)
    dd_now = pts[-1]['dd'] if pts else 0.0
    grow = pts[-1]['grow'] if pts else 0.0

    level = 'норма'
    if dd_now > DD_RARE:     level = 'стоп'
    elif dd_now > DD_WATCH:  level = 'разбор'
    elif dd_now > DD_OK:     level = 'внимание'

    entry = dict(
        date=now.strftime('%Y-%m-%d'),
        week_from=w_from.strftime('%Y-%m-%d'),
        week_to=(w_to - timedelta(days=1)).strftime('%Y-%m-%d'),
        account=st.get('account'), server=st.get('server'),
        account_type=st.get('account_type', 'demo'),
        balance=st.get('balance'), equity=st.get('equity'),
        start_balance=base,
        trades_week=len(week), wins_week=len(wins), losses_week=len(losses),
        money_week=round(sum(t['money'] for t in week), 2),
        pf_week=round(gp / gl, 2) if gl > 0 else None,
        trades_total=len(trades),
        grow_total_pct=round(grow, 2),
        dd_now_pct=round(dd_now, 2),
        dd_max_pct=round(max((p['dd'] for p in pts), default=0.0), 2),
        level=level,
        symbols_week=sorted({t['symbol'] for t in week}),
    )

    print(f"неделя {entry['week_from']} — {entry['week_to']}")
    print(f"  сделок за неделю {entry['trades_week']}"
          f" (плюс {entry['wins_week']}, минус {entry['losses_week']}),"
          f" результат {entry['money_week']:+.2f} {st.get('currency','USD')}")
    print(f"  всего сделок {entry['trades_total']}, рост {entry['grow_total_pct']:+.2f}%,"
          f" просадка сейчас {entry['dd_now_pct']:.2f}%, максимум {entry['dd_max_pct']:.2f}%")
    print(f"  уровень: {entry['level']}"
          f"   (пороги {DD_OK:.0f} / {DD_WATCH:.0f} / {DD_RARE:.0f})")
    if entry['symbols_week']:
        print(f"  инструменты недели: {' '.join(entry['symbols_week'])}")

    if dry:
        print('\n--dry: ничего не записано')
        return

    ARCHIVE.parent.mkdir(parents=True, exist_ok=True)
    arch = json.loads(ARCHIVE.read_text(encoding='utf-8')) if ARCHIVE.exists() else []
    arch = [a for a in arch if a.get('week_from') != entry['week_from']]
    arch.append(entry)
    arch.sort(key=lambda a: a['week_from'])
    ARCHIVE.write_text(json.dumps(arch, ensure_ascii=False, indent=1), encoding='utf-8')

    render_feed(arch)
    render_pulse(st, trades, base)
    svg_line(pts, 'grow', '#4db6a0', 'Доходность, % депозита', 'live_growth.svg')
    svg_line(pts, 'dd', '#c9705c', 'Просадка от максимума, %', 'live_drawdown.svg', invert=True)

    print(f'\nзаписано: {ARCHIVE} ({len(arch)} недель)')
    print(f'графики: {CHARTS}/live_growth.svg, live_drawdown.svg')


if __name__ == '__main__':
    main()
