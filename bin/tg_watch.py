#!/usr/bin/env python3
"""Сторож живого счёта: пишет Сергею в Телеграм, когда что-то случилось.

    python3 bin/tg_watch.py            отправить, если есть о чём
    python3 bin/tg_watch.py --dry      показать сообщения, ничего не слать
    python3 bin/tg_watch.py --test     проверить связь с ботом

На сайте предупреждений нет намеренно (решение Сергея 04.09.2026): витрина
остаётся спокойной, а тревоги летят в личку. Сообщение уходит только когда
состояние изменилось — сравнение с site/data/alerts.json, — поэтому при
ежечасном запуске бот не спамит.

О чём сообщает:
  * наблюдатель замолчал дольше STALE_HOURS и когда данные снова пошли;
  * сменился уровень риска по просадке (норма / внимание / разбор / стоп);
  * закрылись новые сделки — короткой сводкой.

Токен бота и адрес чата берутся из переменных окружения TG_TOKEN и TG_CHAT
(в облаке — секреты репозитория). Без них скрипт работает как --dry.
"""
import json, os, sys, urllib.parse, urllib.request
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from weekly_report import (MT5, SITE, load_status, load_trades, curve,
                           DD_OK, DD_WATCH, DD_RARE, STALE_HOURS)

STATE = SITE / 'data' / 'alerts.json'
API   = 'https://api.telegram.org/bot{token}/sendMessage'


def send(text, dry=False):
    token, chat = os.environ.get('TG_TOKEN'), os.environ.get('TG_CHAT')
    if dry or not token or not chat:
        print(('[dry] ' if dry else '[без токена] ') + text.replace('\n', ' | '))
        return False
    data = urllib.parse.urlencode({
        'chat_id': chat, 'text': text,
        'parse_mode': 'HTML', 'disable_web_page_preview': 'true'}).encode()
    with urllib.request.urlopen(API.format(token=token), data, timeout=20) as r:
        ok = json.load(r).get('ok', False)
    print(('отправлено: ' if ok else 'НЕ отправлено: ') + text.replace('\n', ' | '))
    return ok


def plural(n, one, few, many):
    """Склонение при числе: 1 сделка, 2 сделки, 5 сделок."""
    n = abs(n) % 100
    if 11 <= n <= 14: return many
    n %= 10
    return one if n == 1 else few if 2 <= n <= 4 else many


def money_ru(v):
    """Деньги по-русски: разделитель тысяч — пробел, а не запятая."""
    return f'{v:+,.0f}'.replace(',', '\u202f')


def read_state():
    try:
        return json.loads(STATE.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}


def main():
    dry = '--dry' in sys.argv

    if '--test' in sys.argv:
        send('Проверка связи: сторож w2w на месте.', dry)
        return

    st = load_status()
    if not st:
        print(f'нет w2w_status.json в {MT5} — сказать нечего')
        return
    trades = load_trades()
    base = float(st.get('start_balance') or st.get('balance') or 0) or 1.0

    snap = st.get('time', '')
    try:
        t = datetime.strptime(snap, '%Y.%m.%d %H:%M:%S')
        hours = (datetime.now() - t).total_seconds() / 3600
        when = t.strftime('%d.%m %H:%M')
    except ValueError:
        hours, when = 0.0, snap or '—'

    pts = curve(trades, base)
    dd = pts[-1]['dd'] if pts else 0.0
    grow = pts[-1]['grow'] if pts else 0.0

    level = 'норма'
    if dd > DD_RARE:     level = 'стоп'
    elif dd > DD_WATCH:  level = 'разбор'
    elif dd > DD_OK:     level = 'внимание'

    silent = hours > STALE_HOURS
    old = read_state()
    msgs = []

    # 1. Молчание наблюдателя. Считаем по времени торгового сервера, поэтому
    #    порог с запасом — см. STALE_HOURS в weekly_report.py.
    if silent and not old.get('silent'):
        msgs.append(f'🔕 <b>Наблюдатель молчит.</b>\nПоследний снимок {when}, '
                    f'это {hours:.0f} ч назад.\nПроверь терминал на VDS '
                    f'и синхронизацию Яндекс.Диска.')
    elif old.get('silent') and not silent:
        msgs.append(f'✅ <b>Данные снова идут.</b> Снимок {when}.')

    # 2. Уровень риска. Действия при каждом описаны в МОНИТОРИНГ.md.
    what = {'внимание': 'Проверить, все ли алгоритмы работают.',
            'разбор':   'Разобрать по инструментам. Настройки не менять.',
            'стоп':     'Остановить торговлю и разбираться.',
            'норма':    'Вернулись в норму, действий не нужно.'}
    if old.get('level') and old['level'] != level:
        mark = '🟢' if level == 'норма' else ('🟡' if level == 'внимание' else '🔴')
        msgs.append(f'{mark} <b>Уровень: {level}.</b>\nПросадка {dd:.1f}% '
                    f'(пороги {DD_OK:.0f} / {DD_WATCH:.0f} / {DD_RARE:.0f}).\n'
                    f'{what[level]}')

    # 3. Новые закрытые сделки — сводкой, а не по одной.
    was = old.get('deals')
    now_deals = len(trades)
    if was is not None and now_deals > was and not silent:
        fresh = trades[was:]
        money = sum(t['money'] for t in fresh)
        plus = sum(1 for t in fresh if t['money'] > 0)
        syms = ' '.join(sorted({t['symbol'] for t in fresh}))
        word = plural(len(fresh), 'сделка', 'сделки', 'сделок')
        total_word = plural(now_deals, 'сделка', 'сделки', 'сделок')
        msgs.append(f'📊 <b>Закрыто: {len(fresh)} {word}</b> '
                    f'({plus} в плюс, {len(fresh) - plus} в минус)\n'
                    f'{syms}\nРезультат {money_ru(money)} · всего {now_deals} '
                    f'{total_word}, счёт {grow:+.1f}%, просадка {dd:.1f}%')

    for m in msgs:
        send(m, dry)
    if not msgs:
        print(f'без событий: снимок {when}, уровень {level}, сделок {now_deals}')

    if not dry:
        STATE.parent.mkdir(parents=True, exist_ok=True)
        STATE.write_text(json.dumps(
            {'silent': silent, 'level': level, 'deals': now_deals,
             'snap': snap, 'checked': datetime.now().strftime('%Y-%m-%d %H:%M')},
            ensure_ascii=False, indent=1) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
