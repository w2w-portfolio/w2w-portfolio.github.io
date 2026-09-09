#!/usr/bin/env python3
"""Пересчёт чисел w2w из опубликованной выгрузки сделок.

    python3 verify.py [файл.csv]

Скрипт ничего не берёт с сайта и никуда не ходит: он читает тот же файл
w2w-backtest-trades.csv, который вы скачали, и считает из него всё, что
показано на страницах «Бэктесты» и «Условия». Если числа сойдутся —
значит на сайте посчитано из этих же сделок, а не написано от руки.

Нужен только Python 3, без библиотек. Файл ожидается рядом со скриптом.
"""
import csv, io, os, statistics as st, sys
from collections import defaultdict

# Что стоит на сайте — сюда же смотрите глазами при сверке.
SITE = {'сделок': 3291, 'итог, R': 982.9, 'просадка, R': 18.1,
        'профит-фактор': 1.49, 'прибыльных, %': 38.4, 'средний RR': 2.39}


def drawdown(seq):
    """Максимальная просадка кривой, сложенной из результатов сделок."""
    eq = peak = dd = 0.0
    for x in seq:
        eq += x
        peak = max(peak, eq)
        dd = max(dd, peak - eq)
    return dd


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(os.path.abspath(__file__)), 'w2w-backtest-trades.csv')
    if not os.path.exists(path):
        sys.exit(f'не найден файл: {path}\nскачайте w2w-backtest-trades.csv и положите рядом')

    rows = list(csv.DictReader(io.open(path, encoding='utf-8')))
    r = [float(x['result_r']) for x in rows]
    wins = [x for x in r if x > 0]
    loss = [x for x in r if x <= 0]

    got = {
        'сделок':        len(rows),
        'итог, R':       sum(r),
        'просадка, R':   drawdown(r),
        'профит-фактор': sum(wins) / abs(sum(loss)),
        'прибыльных, %': 100 * len(wins) / len(r),
        'средний RR':    st.fmean(wins) / abs(st.fmean(loss)),
    }

    print(f'файл: {os.path.basename(path)}, строк {len(rows)}\n')
    print(f'{"величина":16}{"из файла":>12}{"на сайте":>12}   ')
    ok = True
    for k, site in SITE.items():
        v = got[k]
        near = abs(v - site) <= (0.05 if isinstance(site, float) else 0)
        ok &= near
        print(f'{k:16}{v:>12.2f}{site:>12}   {"✓" if near else "✗ расходится"}')

    print('\nпо годам, R:')
    by_year = defaultdict(float)
    for x in rows:
        by_year[x['close_time'][:4]] += float(x['result_r'])
    for y in sorted(by_year):
        print(f'  {y}  {by_year[y]:+8.1f}')

    print('\nпо алгоритмам, R:')
    by_algo = defaultdict(float)
    for x in rows:
        by_algo[x['algo']] += float(x['result_r'])
    for a in sorted(by_algo):
        print(f'  {a}  {by_algo[a]:+8.1f}')

    print('\nсходится' if ok else '\nчисла разошлись — напишите автору, это повод разобраться')


if __name__ == '__main__':
    main()
