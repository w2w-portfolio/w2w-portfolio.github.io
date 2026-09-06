#!/usr/bin/env python3
"""Пересчёт всех чисел страницы «Бэктесты» из опубликованной выгрузки сделок.

    python3 check_numbers.py [путь к w2w-backtest-trades.csv]

Скрипт ничего не знает о внутренней кухне: он читает тот же файл, что
лежит на сайте, и печатает числа, которые стоят на страницах. Если они
сходятся — расчёт воспроизводим, и проверить его может любой, а не только
автор.

Стандартная библиотека, никаких зависимостей. Результат каждой сделки —
в долях риска (колонка result_r), поэтому суммы складываются напрямую:
при риске 1% депозита на сделку сумма R и есть проценты депозита.
"""
import csv, statistics as st, sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT = HERE.parent / 'data' / 'w2w-backtest-trades.csv'
path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT

rows = sorted(csv.DictReader(path.open(encoding='utf-8')), key=lambda r: r['close_time'])
r = [float(x['result_r']) for x in rows]
day = lambda x: x['close_time'][:10].replace('.', '-')


def maxdd(seq):
    """Просадка по каждой сделке: баланс меняется в момент закрытия.

    Считать по дням или часам нельзя — провал внутри интервала пропадёт,
    и просадка выйдет мягче, чем была."""
    peak = cum = dd = 0.0
    for v in seq:
        cum += v
        peak = max(peak, cum)
        dd = max(dd, peak - cum)
    return dd


win = [v for v in r if v > 0]
loss = [v for v in r if v < 0]
years = (int(day(rows[-1])[:4]) - int(day(rows[0])[:4]))

print(f'файл: {path}')
print(f'период: {day(rows[0])} — {day(rows[-1])}\n')
P = lambda k, v: print(f'  {k:38} {v}')
P('сделок', len(r))
P('прибыльных', f'{100*len(win)/len(r):.1f}%')
P('итог при риске 1% на сделку', f'{sum(r):+.0f}%')
P('профит-фактор', f'{sum(win)/abs(sum(loss)):.2f}')
P('средний выигрыш / убыток', f'{st.fmean(win):.2f}% / {abs(st.fmean(loss)):.2f}%')
P('средний RR', f'{st.fmean(win)/abs(st.fmean(loss)):.2f}')
P('просадка по закрытым сделкам', f'{maxdd(r):.1f}%')

print('\nпо алгоритмам')
for a, name in (('A2', 'Алгоритм 2'), ('A1', 'Алгоритм 1')):
    sel = [float(x['result_r']) for x in rows if x['algo'] == a]
    srcs = {x['symbol'] for x in rows if x['algo'] == a}
    P(f'{name}: инструментов / итог / просадка',
      f'{len(srcs)} / {sum(sel):+.0f}% / {maxdd(sel):.1f}%')

print('\nпо годам')
by_year = defaultdict(float)
for x, v in zip(rows, r):
    by_year[day(x)[:4]] += v
for y in sorted(by_year):
    P(y, f'{by_year[y]:+.0f}%')

print('\nсерии убытков подряд')
runs, cur = [], 0
for v in r:
    if v < 0:
        cur += 1
    else:
        if cur: runs.append(cur)
        cur = 0
if cur: runs.append(cur)
# группы те же, что в таблице на странице: ровно 5, ровно 7, десять и длиннее
P('всего серий', len(runs))
P('ровно 5 убытков подряд', sum(1 for x in runs if x == 5))
P('ровно 7', sum(1 for x in runs if x == 7))
P('10 и длиннее', sum(1 for x in runs if x >= 10))
P('самая длинная', max(runs))

print('\nразрывы: сделки хуже −1.5R (только Алгоритм 2)')
gaps = [(x['close_time'][:10], x['symbol'], float(x['result_r']))
        for x in rows if float(x['result_r']) <= -1.5]
P('случаев за пять лет', len(gaps))
P('средняя потеря по ним', f'{st.fmean([g[2] for g in gaps]):.2f}R')
P('худший', f'{min(g[2] for g in gaps):.2f}R  {min(gaps, key=lambda g: g[2])[0]}'
            f' {min(gaps, key=lambda g: g[2])[1]}')
