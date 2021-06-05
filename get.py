"""
Statistiques simples des paris effectués sur Betclic.

Créé et maintenu par Mickaël 'Tiger-222' Schoentgen.
"""

__version__ = "3.0.0"

import json
import sys
from base64 import b64decode
from datetime import datetime
from io import StringIO
from pathlib import Path
from typing import Any, Callable, Dict, List, NamedTuple
from uuid import uuid4

import requests
from termgraph.termgraph import chart, read_data

# Betclic details
URL_LOGIN = "https://apif.begmedia.com/api/v1/account/auth/logins"
URL_TRANSACTIONS = "https://globalapi.begmedia.com/api/Transactions/mvts"
HEADERS = {
    "Content-Type": "application/json",
    "Host": "globalapi.begmedia.com",
    "Origin": "https://www.betclic.fr",
    "Referer": "https://www.betclic.fr/",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:87.0) Gecko/20100101 Firefox/87.0",  # noqa
}


class Account(NamedTuple):
    name: str
    enabled: bool
    birthday: str
    login: str
    password: str


class Args(NamedTuple):
    folder: Path
    auto_update: bool
    yearly: bool


class Transaction(NamedTuple):
    date: str
    deposit: float
    withdrawal: float
    bet: float
    cat: str


Accounts = List[Account]
TransactionRaw = Dict[str, Any]
TransactionsRaw = List[TransactionRaw]
Transactions = List[Transaction]
Group = Dict[str, Dict[str, float]]


def request_auth(account: Account) -> str:
    data = {
        "birthdate": f"{account.birthday}T00:00:00.000Z",
        "client_info": {
            "application": "BETCLIC.FR",
            "channel": "WEB_BETCLIC.FR",
            "universe": "sport",
        },
        "fingerprint": str(uuid4()),
        "login": account.login,
        "password": account.password,
    }
    headers = {
        **HEADERS,
        "Host": "apif.begmedia.com",
    }
    with requests.post(URL_LOGIN, headers=headers, json=data) as req:
        req.raise_for_status()
        res: Dict[str, Any] = req.json()

    assert res["status"] == "Validated"
    return json.dumps(res["token"])


def get_transactions(page: int) -> TransactionsRaw:
    params = {
        "filter": "All",
        "page": str(page),
        "pageSize": "20",
    }
    with requests.get(URL_TRANSACTIONS, headers=HEADERS, params=params) as req:
        req.raise_for_status()
        data: TransactionsRaw = req.json()
        return data


def get_all_transactions() -> TransactionsRaw:
    page = 1
    transactions = []
    while "there are transactions":
        new_transactions = get_transactions(page)
        if not new_transactions:
            break
        transactions.extend(new_transactions)
        page += 1
    return transactions


def sort_by_date(transactions: TransactionsRaw) -> TransactionsRaw:
    def sorter(transaction: TransactionRaw) -> datetime:
        return datetime.strptime(transaction["date"], "%d/%m/%Y %H:%M")

    return sorted(transactions, key=sorter)


def load_accounts(file: Path) -> Accounts:
    def decoder(data: Dict[str, Any]) -> Account:
        if data["name"] != "Skeleton":
            for key, val in data.items():
                if key in ("birthday", "login", "password") and type(val) is str:
                    data[key] = b64decode(val).decode("utf-8")
        return Account(
            data["name"],
            data["enabled"],
            data["birthday"],
            data["login"],
            data["password"],
        )

    try:
        with file.open() as fh:
            data: Accounts = json.load(fh, object_hook=decoder)
            return data
    except FileNotFoundError:
        return []


def load_history(file: Path) -> TransactionsRaw:
    try:
        with file.open() as fh:
            data: TransactionsRaw = json.load(fh)
            return data
    except FileNotFoundError:
        return []


def save_history(file: Path, transactions: TransactionsRaw) -> None:
    with file.open(mode="w") as fh:
        json.dump(transactions, fh)


def label_month(bet: Transaction) -> str:
    # date format: 09/04/2021 08:35
    _, month, year = bet.date.split(" ")[0].split("/")
    return f"{month}/{year}"


def label_year(bet: Transaction) -> str:
    # date format: 09/04/2021 08:35
    return bet.date[6:10]


def group_by(transactions: Transactions, label_cb: Callable) -> Group:
    group: Group = {}
    for transaction in transactions:
        label = label_cb(transaction)
        try:
            group[label]["deposit"] += transaction.deposit
            group[label]["withdrawal"] += transaction.withdrawal
        except KeyError:
            group[label] = {
                "deposit": transaction.deposit,
                "withdrawal": transaction.withdrawal,
            }
    return group


def plot_all_bets(
    account: Account, transactions: Transactions, yearly: bool = False
) -> None:
    plot(
        account,
        transactions,
        label_year if yearly else label_month,
        ["red", "green"],
        max_items=4 if yearly else 12,
    )


def plot(
    account: Account,
    transactions: Transactions,
    label_cb: Callable,
    colors: List[str],
    max_items: int = 256,
) -> None:
    lines = "@ Pertes,Gains"
    it = sorted(group_by(transactions, label_cb).items())
    for idx, (label, values) in enumerate(it, start=1):
        if idx > max_items:
            break
        lines += f"\n{label},{values['deposit']:.02f},{values['withdrawal']:.02f}"
    sys.stdin = StringIO(lines)

    balance = fmt_number(sum(bet.bet for bet in transactions), suffix="€")
    args = {
        "color": colors,
        "different_scale": False,
        "filename": "-",
        "format": "{:<5.2f}",
        "histogram": False,
        "no_labels": False,
        "no_values": False,
        "stacked": False,
        "suffix": "",
        "title": f"[{account.name}] Balance des paris : {balance}",
        "verbose": False,
        "vertical": False,
        "width": 50,
    }
    _, labels, data, colors = read_data(args)
    chart(colors, data, args, labels)


def fmt_number(val: float, /, *, suffix: str = "iB") -> str:
    """
    Human readable version of file size.
    Supports:
        - all currently known binary prefixes (https://en.wikipedia.org/wiki/Binary_prefix)
        - negative and positive numbers
        - numbers larger than 1,000 Yobibytes
        - arbitrary units

    Examples:

        >>> fmt_number(168963795964)
        "157.36 GiB"
        >>> fmt_number(168963795964, suffix="io")
        "157.36 Gio"
        >>> fmt_number(4096, suffix="Ω")
        "4.10 kΩ"

    Source: https://stackoverflow.com/a/1094933/1117028
    """
    kilo, divider = ("K", 1024.0) if suffix[0] == "i" else ("k", 1000.0)
    for unit in ("", kilo, "M", "G", "T", "P", "E", "Z"):
        if abs(val) < divider:
            return f"{val:3.2f} {unit}{suffix}"
        val /= divider
    return f"{val:,.2f} Y{suffix}"


def filter_and_arrange(all_transactions: TransactionsRaw) -> Transactions:
    """Filter transactions and generate appropriate *Transaction* objects.

    Transaction details:
        {'date': '20/05/2021 13:41', 'code': 'Bet',        'libelle': 'Mise',               'libelleTransaction': 'Mise',               'stakeReference': '105Hxxxxxxxxxxxxx', 'betReference': '105Hxxxxxxxxxxxxx', 'totalAmount': None,  'creditAmount': None,  'debitAmount': 50.0, 'bonusPercent': None, 'bonusAmount': None, 'fees': 0.0, 'currency': None, 'super14Reference': None, 'message': None, 'supertotoProduct': None, 'supertotoBetId': None, 'refColossus': None}  # noqa
        {'date': '01/05/2021 22:51', 'code': 'Boost',      'libelle': 'Multiple bet bonus', 'libelleTransaction': 'Multiple bet bonus', 'stakeReference': '105Axxxxxxxxxxxxx', 'betReference': '105Axxxxxxxxxxxxx', 'totalAmount': 45.39, 'creditAmount': 1.69,  'debitAmount': None, 'bonusPercent': 5.0,  'bonusAmount': 1.69, 'fees': 0.0, 'currency': None, 'super14Reference': None, 'message': None, 'supertotoProduct': None, 'supertotoBetId': None, 'refColossus': None}  # noqa
        {'date': '19/05/2021 21:47', 'code': 'Deposit',    'libelle': 'Carte bancaire',     'libelleTransaction': 'Dépôt',              'stakeReference': None,                'betReference': None,                'totalAmount': None,  'creditAmount': 100.0, 'debitAmount': None, 'bonusPercent': None, 'bonusAmount': None, 'fees': 0.0, 'currency': None, 'super14Reference': None, 'message': None, 'supertotoProduct': None, 'supertotoBetId': None, 'refColossus': None}  # noqa
        {'date': '04/04/2021 20:15', 'code': 'FreebetWin', 'libelle': 'Gain Freebet',       'libelleTransaction': 'Gain Freebet',       'stakeReference': '103Axxxxxxxxxxxxx', 'betReference': '103Axxxxxxxxxxxxx', 'totalAmount': None,  'creditAmount': 0.78,  'debitAmount': None, 'bonusPercent': None, 'bonusAmount': None, 'fees': 0.0, 'currency': None, 'super14Reference': None, 'message': None, 'supertotoProduct': None, 'supertotoBetId': None, 'refColossus': None}  # noqa
        {'date': '19/05/2021 22:57', 'code': 'Win',        'libelle': 'Gain',               'libelleTransaction': 'Gain',               'stakeReference': '105Exxxxxxxxxxxxx', 'betReference': '105Exxxxxxxxxxxxx', 'totalAmount': 120.0, 'creditAmount': 120.0, 'debitAmount': None, 'bonusPercent': None, 'bonusAmount': None, 'fees': 0.0, 'currency': None, 'super14Reference': None, 'message': None, 'supertotoProduct': None, 'supertotoBetId': None, 'refColossus': None}  # noqa
        {'date': '20/05/2021 13:42', 'code': 'Withdrawal', 'libelle': 'Virement bancaire',  'libelleTransaction': 'Retrait',            'stakeReference': None,                'betReference': None,                'totalAmount': None,  'creditAmount': None,  'debitAmount': 22.0, 'bonusPercent': None, 'bonusAmount': None, 'fees': 0.0, 'currency': None, 'super14Reference': None, 'message': None, 'supertotoProduct': None, 'supertotoBetId': None, 'refColossus': None}  # noqa

    Where is the amount?
        Bet:        debitAmount
        Boost:      totalAmount
        Deposit:    creditAmount
        FreebetWin: creditAmount
        Withdrawal: debitAmount
        Win:        totalAmount || creditAmount
    """

    transactions = []
    for transaction in all_transactions:
        bet = debit = credit = 0.0
        code = transaction["code"]

        if code == "Bet":
            bet = transaction["debitAmount"] * -1
        elif code in ("FreebetWin", "Win"):
            bet = transaction["totalAmount"] or transaction["creditAmount"]
        elif code == "Deposit":
            debit = transaction["creditAmount"]
        elif code == "Withdrawal":
            credit = transaction["debitAmount"]
        elif code == "Boost":
            # It seems those transactions are duplicates of "Win": both transations appears when a "Boost" is present.
            continue
        else:
            print("!!", transaction)
            exit(2)

        transactions.append(
            Transaction(
                transaction["date"],
                debit,
                credit,
                bet,
                transaction["code"],
            )
        )
    return transactions


def process(args: Args, account: Account) -> None:
    # Load saved metrics
    file = args.folder / "data" / f"{account.login}.json"
    transactions = load_history(file)
    new_transactions = []

    # Update if not explicitely disallowed
    if args.auto_update:
        HEADERS["X-CLIENT"] = request_auth(account)
        new_transactions = [
            transaction
            for transaction in get_all_transactions()
            if transaction not in transactions
        ]

    if new_transactions:
        transactions.extend(new_transactions)
        transactions = sort_by_date(transactions)
        save_history(file, transactions)

    # Keep and format revelant transactions
    final_transactions = filter_and_arrange(transactions)
    if not final_transactions:
        return

    # Display nice charts
    plot_all_bets(account, final_transactions, yearly=args.yearly)


def main(*args: Any) -> int:
    if "--help" in args:
        print("--no-update to disable metrics update")
        print("--yearly to display a yearly chart (instead of monthly)")
        return 0

    arguments = Args(
        Path(__file__).parent, "--no-update" not in args, "--yearly" in args
    )

    for account in load_accounts(arguments.folder / "accounts.json"):
        if not account.enabled:
            continue
        process(arguments, account)

    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
