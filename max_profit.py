# -*- coding: utf-8 -*-


def maximize_profit(prices):
    max_profit = 0
    min_price = prices[0]
    for price in prices:
        if price - min_price > max_profit:
            max_profit = price - min_price
        if price < min_price:
            min_price = price
    return max_profit

print maximize_profit([2, 3, 10, 6, 4, 8, 1])