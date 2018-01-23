import json
from datetime import datetime
from time import mktime, sleep
from urllib.parse import urlencode

import requests

import utils

base_url = 'https://api.binance.com'

statistics_list = []


def get_buy_watermark(symbol, buy_price, timestamp):
    history_high = 0
    history_low = 1000000000
    kline_data = {'symbol': symbol, 'interval': '1d', 'limit': 500}
    for kline in requests.get('{}/api/v1/klines?{}'.format(base_url, urlencode(kline_data))).json():
        kline_timestamp = float(kline[0])

        if kline_timestamp >= timestamp:
            break

        price_close = float(kline[4])

        if price_close >= history_high:
            history_high = price_close

        if price_close <= history_low:
            history_low = price_close

    if history_high - history_low > 0:
        return (buy_price - history_low) / (history_high - history_low)
    return 1


def analyze_bull(base_symbol):
    symbols = [symbol['symbol'] for symbol in requests.get('{}/api/v3/ticker/price'.format(base_url)).json()
               if symbol['symbol'].endswith(base_symbol)]
    for symbol in symbols:
        highest_price = 0
        starting_timestamp = 0
        highest_price_timestamp = 0
        buy_price = 0
        possess = False
        time_take = 0
        cooldown_time = 0
        profit = 0
        starting_increase = 0
        buy_watermark = 0
        buy_date = None
        base_time = '1h'
        kline_starting_timestamp = mktime(datetime.strptime(
            '2018/01/01-00:00:00', "%Y/%m/%d-%H:%M:%S").timetuple()) * 1000
        kline_data = {'symbol': symbol, 'interval': base_time, 'limit': 500}
        klines = requests.get('{}/api/v1/klines?{}'.format(base_url, urlencode(kline_data))).json()
        klines.pop(0)
        for kline in klines:
            price_open = float(kline[1])
            price_close = float(kline[4])
            price_low = float(kline[3])
            price_high = float(kline[2])
            timestamp = float(kline[0])

            if price_close >= highest_price:
                highest_price = price_high
                highest_price_timestamp = timestamp

            if not possess and price_high / price_open - 1 > 0.09:
                buy_price = price_open * 1.09
                starting_timestamp = timestamp
                buy_date = datetime.fromtimestamp(
                    int(starting_timestamp / 1000)).strftime('%Y-%m-%d %H:%M:%S')
                starting_increase = price_high / price_open - 1
                cooldown_time = timestamp - highest_price_timestamp
                highest_price = price_high
                highest_price_timestamp = timestamp
                buy_watermark = get_buy_watermark(symbol, buy_price, starting_timestamp)
                possess = True
        sleep(1)

        if possess:
            time_take = highest_price_timestamp - starting_timestamp
            profit = highest_price / buy_price - 1

        symbol_statistics_json = {'symbol': symbol, 'cooldown': cooldown_time/3600000,
                                  'buy_price': buy_price, 'time_take': time_take/3600000,
                                  'profit': profit, 'starting_increase': starting_increase,
                                  'buy_watermark': buy_watermark,
                                  'highest_price_since_buy': highest_price,
                                  'buy_date': buy_date}

        statistics_list.append(symbol_statistics_json)

    with open('statistics-{}.log'.format(base_time), 'a+') as statistics_file:
        json.dump(statistics_list, statistics_file, indent=4)
        statistics_file.write('\n')


def analyze_bear(base_symbol):
    symbols = [symbol['symbol'] for symbol in requests.get('{}/api/v3/ticker/price'.format(base_url)).json()
               if symbol['symbol'].endswith(base_symbol)]
    for symbol in symbols:
        starting_timestamp = 0
        buy_price = 0
        possess = False
        highest_profit = 0
        lowest_profit = 100000
        kline_starting_timestamp = mktime(datetime.strptime(
            '2018/01/01-00:00:00', "%Y/%m/%d-%H:%M:%S").timetuple()) * 1000
        kline_data = {'symbol': symbol, 'interval': '6h', 'limit': 500, 'startTime': int(kline_starting_timestamp)}
        klines = requests.get('{}/api/v1/klines?{}'.format(base_url, urlencode(kline_data))).json()

        for kline in klines:
            price_open = float(kline[1])
            price_low = float(kline[3])
            timestamp = float(kline[0])

            if possess and timestamp != starting_timestamp:
                sell_price = price_open
                profit = sell_price / buy_price - 1
                if highest_profit < profit:
                    highest_profit = profit
                if lowest_profit > profit:
                    lowest_profit = profit
                possess = False

            if not possess and price_open / price_low >= 1.2:
                buy_price = price_open / 1.2
                starting_timestamp = timestamp
                possess = True

        symbol_statistics_json = {'symbol': symbol,
                                  'highest_profit': highest_profit,
                                  'lowest_profit': lowest_profit}

        statistics_list.append(symbol_statistics_json)

    with open('statistics.log', 'a+') as statistics_file:
        json.dump(statistics_list, statistics_file, indent=4)
        statistics_file.write('\n')


def max_profit():
    with open('statistics.log', 'r') as statistics_file:
        data = json.load(statistics_file)

    profit_percent_low = None
    profit_percent_high = 0.3

    total = len(data)
    if profit_percent_low:
        below_low_total = len([d for d in data if d['profit'] < profit_percent_low])
        in_low_high_total = len([d for d in data if profit_percent_low <= d['profit'] < profit_percent_high])
    else:
        below_low_total = len([d for d in data if d['profit'] < profit_percent_high])
    above_high_total = len([d for d in data if d['profit'] >= profit_percent_high])

    if profit_percent_low:
        gain_low = in_low_high_total / total * profit_percent_low * 0.5 - (total - in_low_high_total) / total * 0.5 * 0.1
    else:
        gain_low = 0
    gain_high = above_high_total / total * profit_percent_high
    loss = below_low_total / total * 0.1

    return gain_high + gain_low - loss


def get_trading_pairs_rule():
    exchange_info = requests.get('{}/api/v1/exchangeInfo'.format(base_url)).json()['symbols']
    pass


get_trading_pairs_rule()
# analyze_bear('USDT')
analyze_bull('ETH')
profit = max_profit()
pass
