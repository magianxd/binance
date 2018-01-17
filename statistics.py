import json
from datetime import datetime
from time import mktime
from urllib.parse import urlencode

import requests

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


def analyze():
    symbols = [symbol['symbol'] for symbol in requests.get('{}/api/v3/ticker/price'.format(base_url)).json()
               if symbol['symbol'].endswith('ETH')]
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
        kline_starting_timestamp = mktime(datetime.strptime(
            '2018/01/01-00:00:00', "%Y/%m/%d-%H:%M:%S").timetuple()) * 1000
        kline_data = {'symbol': symbol, 'interval': '1h', 'limit': 500, 'startTime': int(kline_starting_timestamp)}
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

            if not possess and price_high / price_open - 1 > 0.1:
                buy_price = price_open * 1.1
                starting_timestamp = timestamp
                buy_date = datetime.fromtimestamp(
                    int(starting_timestamp / 1000)).strftime('%Y-%m-%d %H:%M:%S')
                starting_increase = price_high / price_open - 1
                cooldown_time = timestamp - highest_price_timestamp
                highest_price = price_high
                highest_price_timestamp = timestamp
                buy_watermark = get_buy_watermark(symbol, buy_price, starting_timestamp)
                possess = True

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

        # with open('statistics.log', 'a+') as statistics_file:
        #     if buy_price > 0 and profit > 0.5:
        #         json.dump(symbol_statistics_json, statistics_file)
        #         statistics_file.write('\n')

    statistics_list.sort(key=lambda i: i['profit'], reverse=True)

    with open('statistics.log', 'a+') as statistics_file:
        json.dump(statistics_list, statistics_file, indent=4)
        statistics_file.write('\n')


def max_profit(data):
    profit_percent_low = 0.3
    profit_percent_high = 1

    total = len(data)
    below_low_total = len([d for d in data if d['profit'] < profit_percent_low])
    in_low_high_total = len([d for d in data if d['profit'] >= profit_percent_low
                             and d['profit'] < profit_percent_high])
    above_high_total = len([d for d in data if d['profit'] >= profit_percent_high])

    gain_low = in_low_high_total / total * profit_percent_low * 0.5 - (total - in_low_high_total) / total * 0.5 * 0.1
    gain_high = above_high_total / total * profit_percent_high
    loss = below_low_total / total * 0.1

    gain = gain_high + gain_low - loss
    pass


def get_trading_pairs_rule():
    exchange_info = requests.get('{}/api/v1/exchangeInfo'.format(base_url)).json()['symbols']
    pass

with open('statistics.log', 'r') as statistics_file:
    json = json.load(statistics_file)

get_trading_pairs_rule()
max_profit(json)
j = {}
if not j:
    pass
analyze()
