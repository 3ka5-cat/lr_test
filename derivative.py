# -*- coding: utf-8 -*-
from copy import copy
import re
import requests
import sys
import traceback
import xml.etree.ElementTree as ET


def _check_is_digit(a):
    return a['value'].lstrip('-').replace('.', '', 1).isdigit()


def single_derivative(a):
    if _check_is_digit(a):
        value = '0'
    else:
        re_txt = re.search(r'(ln|sin|cos|tg|ctg)\((.*)\)', a['value'])
        value = '{}({})\''.format(re_txt.group(1), re_txt.group(2)) if re_txt else '1'
    return dict(calculated=True, value=value)


def raise_to_power(a, b):
    a_is_digit = _check_is_digit(a)
    b_is_digit = _check_is_digit(b)
    if a_is_digit and b_is_digit:
        # derivative of constant
        res = '0'
    elif a_is_digit and not b_is_digit:
        if float(a['value']) in [0.0, 1.0]:
            res = '0'
        else:
            # derivative of constant raised to power of expression
            res = '{} ^ {} * ln({})'.format(a['value'], b['value'], a['value'])
    elif not a_is_digit and b_is_digit:
        if float(b['value']) in [0.0, 1.0]:
            res = b['value']
        else:
            # derivative of expression raised to power of constant
            res = '{} * {} ^ {}'.format(b['value'], a['value'], float(b['value']) - 1)
    else:
        raise NotImplementedError('Raising expression to the power of another expression')
    return dict(calculated=True, value=res)


def multiply(a, b):
    a_is_digit = _check_is_digit(a)
    b_is_digit = _check_is_digit(b)
    if a_is_digit and b_is_digit:
        # here and below: we should calculate derivative only once and
        # don't calculate derivatives of expressions till trivial tokens
        if a['calculated'] or b['calculated']:
            res = '{} * {}'.format(a['value'], b['value'])
        else:
            # derivative of constant
            res = '0'
    elif a_is_digit and not b_is_digit:
        if not b['calculated']:
            b = calc_first_derivative(b['value'])
        res = '{} * {}'.format(a['value'], b['value'])
    elif not a_is_digit and b_is_digit:
        if not a['calculated']:
            a = calc_first_derivative(a['value'])
        res = '{} * {}'.format(a['value'], b['value'])
    else:
        # both factors are expressions
        if not a['calculated']:
            a = calc_first_derivative(a['value'])
        if not b['calculated']:
            b = calc_first_derivative(b['value'])
        res = '{} * {} + {} * {}'.format(a['value'], b['value'],
                                         a['value'], b['value'])
    return dict(calculated=True, value=res)


def divide(a, b):
    a_is_digit = _check_is_digit(a)
    b_is_digit = _check_is_digit(b)
    if b_is_digit and b == 0.0:
        raise ZeroDivisionError

    if a_is_digit and b_is_digit:
        if a['calculated'] or b['calculated']:
            res = '{} / {}'.format(a['value'], b['value'])
        else:
            # derivative of constant
            res = '0'
    elif a_is_digit and not b_is_digit:
        if not b['calculated']:
            calculated_b = calc_first_derivative(b['value'])
            res = '- ( {} * {} ) / {} ^ 2'.format(a['value'], calculated_b['value'], b['value'])
        else:
            res = '{} / {}'.format(a, b)
    elif not a_is_digit and b_is_digit:
        if not a['calculated']:
            b['value'] = '{}'.format(1.0 / float(b['value']))
            return multiply(a, b)
        else:
            res = '{} / {}'.format(a['value'], b['value'])
    else:
        # we have a problem here if derivative of a or b is already calculated,
        # this case could be triggered after addition of parenthesis support
        calculated_a = calc_first_derivative(a['value'])
        calculated_b = calc_first_derivative(b['value'])
        res = '( {} * {} - {} * {} ) / {} ^ 2'.format(calculated_a['value'], b['value'],
                                                      a['value'], calculated_b['value'], b['value'])
    return dict(calculated=True, value=res)


def _additive_operation(a, b, op):
    if op not in ['+', '-']:
        raise ValueError('Wrong operator for additive operation')

    if a['calculated'] and b['calculated']:
        return dict(calculated=True, value='{} {} {}'.format(a['value'], op, b['value']))

    a_is_digit = _check_is_digit(a)
    b_is_digit = _check_is_digit(b)
    if a_is_digit and b_is_digit:
        # derivative of constant
        res = '0'
    else:
        if a_is_digit and not b_is_digit:
            # one summand is number, other is expression
            if not b['calculated']:
                b = calc_first_derivative(b['value'])
            if not a['calculated']:
                a['value'] = 0
        elif not a_is_digit and b_is_digit:
            # one summand is number, other is expression
            if not a['calculated']:
                a = calc_first_derivative(a['value'])
            if not b['calculated']:
                b['value'] = 0
        else:
            # both summands are expressions
            if not a['calculated']:
                a = calc_first_derivative(a['value'])
            if not b['calculated']:
                b = calc_first_derivative(b['value'])
        res = '{} {} {}'.format(a['value'], op, b['value'])
    return dict(calculated=True, value=res)


def add(a, b):
    return _additive_operation(a, b, '+')


def subtract(a, b):
    return _additive_operation(a, b, '-')


derivatives = {
    '+': add,
    '-': subtract,
    '*': multiply,
    '/': divide,
    '^': raise_to_power,
}

L, R = 'l', 'r'
NUMBER = 'n'
operators = {
    '+': dict(priority=1, associativity=L),
    '-': dict(priority=1, associativity=L),
    '*': dict(priority=2, associativity=L),
    '/': dict(priority=2, associativity=L),
    '^': dict(priority=3, associativity=R)
}


def parse_input(expression):
    tokens = []
    for token in expression.strip().split():
        if token in ['(', ')']:
            raise NotImplementedError('Parentheses aren\'t supported')
        elif token in operators:
            tokens.append((token, operators[token]))
        else:
            tokens.append((NUMBER, token))
    return tokens


def shunting_yard(tokens):
    out, stack = [], []
    for token, data in tokens:
        if token == NUMBER:
            out.append(data)
        elif token in operators:
            t1, p1, a1 = token, data['priority'], data['associativity']
            while stack:
                t2 = stack[-1][0]
                p2, a2 = stack[-1][1]['priority'], stack[-1][1]['associativity']
                if (a1 == L and p1 <= p2) or (a1 == R and p1 < p2):
                    stack.pop()
                    out.append(t2)
                else:
                    break
            stack.append((t1, data))

    while stack:
        out.append(stack[-1][0])
        stack.pop()

    return out


def first_derivative(elements):
    pile = []
    old_elements = copy(elements)   # useful for debugging
    while elements:
        e = elements.pop(0)
        if e in operators:
            b = pile.pop()
            a = pile.pop()
            pile.append(derivatives[e](a, b))
        else:
            if not isinstance(e, dict):
                e = dict(calculated=False, value=e)
            if not elements:
                e = single_derivative(e)
            pile.append(e)
    # print pile
    return pile[0]


def calc_first_derivative(expression):
    rpn = shunting_yard(parse_input(expression))
    # print '{} -> {}'.format(expression, rpn)
    return first_derivative(rpn)


def test():
    tests_ok = True
    line = None
    try:
        assert calc_first_derivative('2 ^ 3')['value'] == '0'
        assert calc_first_derivative('2 + 3')['value'] == '0'
        assert calc_first_derivative('2 - 3')['value'] == '0'
        assert calc_first_derivative('2 * 3')['value'] == '0'
        #
        assert calc_first_derivative('X')['value'] == '1'
        assert calc_first_derivative('X ^ 0')['value'] == '0'
        assert calc_first_derivative('X ^ 1')['value'] == '1'
        assert calc_first_derivative('X ^ 2')['value'] == '2 * X ^ 1.0'
        #
        assert calc_first_derivative('0 ^ X')['value'] == '0'
        assert calc_first_derivative('1 ^ X')['value'] == '0'
        assert calc_first_derivative('2 ^ X')['value'] == '2 ^ X * ln(2)'
        assert calc_first_derivative('2 ^ X + 2')['value'] == '2 ^ X * ln(2) + 0'
        #
        assert calc_first_derivative('2 + X')['value'] == '0 + 1'
        assert calc_first_derivative('2 - X')['value'] == '0 - 1'
        assert calc_first_derivative('2 * X')['value'] == '2 * 1'
        #
        assert calc_first_derivative('2 + X ^ 0')['value'] == '0'
        assert calc_first_derivative('2 + X ^ 1')['value'] == '0'
        assert calc_first_derivative('2 + X ^ 2')['value'] == '0 + 2 * X ^ 1.0'
        #
        assert calc_first_derivative('2 - X ^ 0')['value'] == '0'
        assert calc_first_derivative('2 - X ^ 1')['value'] == '0'
        assert calc_first_derivative('2 - X ^ 2')['value'] == '0 - 2 * X ^ 1.0'
        #
        assert calc_first_derivative('2 * X ^ 0')['value'] == '2 * 0'
        assert calc_first_derivative('2 * X ^ 1')['value'] == '2 * 1'
        assert calc_first_derivative('2 * X ^ 2')['value'] == '2 * 2 * X ^ 1.0'
        #
        assert calc_first_derivative('X + X ^ 0')['value'] == '1 + 0'
        assert calc_first_derivative('X + X ^ 1')['value'] == '1 + 1'
        assert calc_first_derivative('X + X ^ 2')['value'] == '1 + 2 * X ^ 1.0'
        #
        assert calc_first_derivative('X - X ^ 0')['value'] == '1 - 0'
        assert calc_first_derivative('X - X ^ 1')['value'] == '1 - 1'
        assert calc_first_derivative('X - X ^ 2')['value'] == '1 - 2 * X ^ 1.0'
        #
        assert calc_first_derivative('X ^ 0 + X ^ 0')['value'] == '0 + 0'
        assert calc_first_derivative('X ^ 1 + X ^ 0')['value'] == '1 + 0'
        assert calc_first_derivative('X ^ 1 + X ^ 1')['value'] == '1 + 1'
        assert calc_first_derivative('X ^ 2 + X ^ 0')['value'] == '2 * X ^ 1.0 + 0'
        assert calc_first_derivative('X ^ 2 + X ^ 1')['value'] == '2 * X ^ 1.0 + 1'
        assert calc_first_derivative('X ^ 2 + X ^ 2')['value'] == '2 * X ^ 1.0 + 2 * X ^ 1.0'
        #
        assert calc_first_derivative('X ^ 0 - X ^ 0')['value'] == '0 - 0'
        assert calc_first_derivative('X ^ 1 - X ^ 0')['value'] == '1 - 0'
        assert calc_first_derivative('X ^ 1 - X ^ 1')['value'] == '1 - 1'
        assert calc_first_derivative('X ^ 2 - X ^ 0')['value'] == '2 * X ^ 1.0 - 0'
        assert calc_first_derivative('X ^ 2 - X ^ 1')['value'] == '2 * X ^ 1.0 - 1'
        assert calc_first_derivative('X ^ 2 - X ^ 2')['value'] == '2 * X ^ 1.0 - 2 * X ^ 1.0'
        #
        assert calc_first_derivative('X ^ 2 + 0 * X')['value'] == '2 * X ^ 1.0 + 0 * 1'
        assert calc_first_derivative('X ^ 2 + 1 * X')['value'] == '2 * X ^ 1.0 + 1 * 1'
        assert calc_first_derivative('X ^ 2 + 2 * X')['value'] == '2 * X ^ 1.0 + 2 * 1'
        #
        assert calc_first_derivative('X ^ 2 + 2 * X ^ 0')['value'] == '2 * X ^ 1.0 + 2 * 0'
        assert calc_first_derivative('X ^ 2 + 2 * X ^ 1')['value'] == '2 * X ^ 1.0 + 2 * 1'
        #
        assert calc_first_derivative('X ^ 2 + 2 * X ^ 2')['value'] == '2 * X ^ 1.0 + 2 * 2 * X ^ 1.0'
        #
        # Tests for parenthesis support
        # assert calc_first_derivative('2 ^ ( X + 5 ) * 7')['value'] == '7 * 2 ^ ( x + 5 ) * ln(2)'
        # assert (calc_first_derivative('( ( X ^ 2 ) + ( 2 * ( X ^ 2 ) ) )')['value'] ==
        #         '2 * X ^ 1.0 + 2 * 2 * X ^ 1.0')
        # assert calc_first_derivative('2 * ( X + 5 )')['value'] == '2 * 1 + 0'
        #

        assert calc_first_derivative('1 / 2')['value'] == '0'
        assert calc_first_derivative('1 / X')['value'] == '- ( 1 * 1 ) / X ^ 2'
        assert calc_first_derivative('0 * 2 / X')['value'] == '- ( 0 * 1 ) / X ^ 2'
        assert calc_first_derivative('X / 1')['value'] == '1 * 1.0'

        raised = False
        try:
            calc_first_derivative('X / 0')
        except ZeroDivisionError:
            raised = True
        assert raised == True

        assert calc_first_derivative('X + 2 / 1')['value'] == '1 + 0'
        assert calc_first_derivative('X - 2 / 1')['value'] == '1 - 0'
        assert calc_first_derivative('X * 0 / 1')['value'] == '1 * 0 / 1'
        assert calc_first_derivative('X * 2 / 1')['value'] == '1 * 2 / 1'
        assert calc_first_derivative('X / ln(X)')['value'] == '( 1 * ln(X) - X * ln(X)\' ) / ln(X) ^ 2'
    except AssertionError:
        _, _, tb = sys.exc_info()
        tb_info = traceback.extract_tb(tb)
        _, line, _, _ = tb_info[-1]
        tests_ok = False

    print '{} {} {} {}'.format('='*10, 'Tests', 'OK' if tests_ok else 'FAIL', '='*10)
    if not tests_ok:
        print 'Failed line: {}\n'.format(line)


def ask_wolfram(expression):
    sys.stdout.write('Asking Wolfram Alpha...')
    params = {
        'appid': 'J6HA6V-YHRLHJ8A8Q',  # wolframalpha api key from google search
        'input': '({})\''.format(expression)
    }

    response = requests.get('http://api.wolframalpha.com/v2/query', params=params)
    wf_result = 'Error while requesting Wolfram Alpha :('
    # go in hell, XML...
    try:
        tree = ET.fromstring(response.text)
        if tree.attrib['success'].lower() == 'true':
            derivative_node = tree.find('pod[@title="Derivative"]')
            if derivative_node.attrib['error'].lower() == 'false':
                res = derivative_node.find('subpod').find('plaintext').text
                wf_result = 'Result from Wolfram Alpha (simplifications applied):\n{}'.format(res)
    except (KeyError, AttributeError):
        wf_result = 'Error while parsing result from Wolfram Alpha'

    print '\r{}'.format(wf_result)


if __name__ == '__main__':
    """
    Usage: place space separated expression into `expression` variable to calculate it's first derivative.
    Note:
        * parenthesises ARE NOT supported
        * simplification IS NOT implemented
        * raising constant to power of expression IS implemented
        * raising expression to power of another expression IS NOT implemented
        * first derivative of functions (like ln, sin, etc.) IS marked, but IS NOT calculated
    """
    # expression = '2 * 5 * X ^ 2'  # TODO: implement simplification
    # expression = 'X ^ 1 + X'      # TODO: implement simplification
    # expression = 'X ^ 2 * X ^ 3'  # TODO: implement simplification
    # expression = '1 / X * 2'      # TODO: implement simplification
    # expression = '1 / 5 * X'      # TODO: implement simplification
    # expression = '2 ^ ( X + 5 ) * 7'  # TODO: implement parenthesis support
    # expression = '(X ^ 2) ^ (Y ^ 3)'  # TODO: implement raising expression to power of another expression
    test()

    expression = 'X ^ 3 + X ^ 5'
    print 'Result:\nder({}) = {}'.format(expression.replace(' ', ''),
                                         calc_first_derivative(expression)['value'].replace(' ', ''))
    ask_wolfram(expression)
