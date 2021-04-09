"""
Statistiques simples des paris effectués sur Betclic.

Créé et maintenu par Mickaël 'Tiger-222' Schoentgen.
"""

__version__ = "1.0.0"

import datetime
import json
import pickle
import sys
from io import StringIO
from operator import attrgetter
from pathlib import Path
from typing import Any, Callable, Dict, List, NamedTuple, Optional
from uuid import uuid4

import requests
from dateutil.parser import parse
from termgraph.termgraph import chart, read_data

# User details
BIRTHDAY = "YYYY-MM-DD"
LOGIN = "EMAIL_OR_USERID"
PASSWORD = "MY_PASSWORD"

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


class Transaction(NamedTuple):
    id: str
    date: str
    loss: float
    win: float


Transactions = List[Transaction]
Group = Dict[str, Dict[str, float]]


def request_auth() -> str:
    data = {
        "birthdate": f"{BIRTHDAY}T00:00:00.000Z",
        "client_info": {
            "application": "BETCLIC.FR",
            "channel": "WEB_BETCLIC.FR",
            "universe": "sport",
        },
        "fingerprint": str(uuid4()),
        "login": LOGIN,
        "password": PASSWORD,
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


def get_transactions(page: int, until: Optional[datetime.datetime]) -> Transactions:
    params = {
        "filter": "All",
        "page": str(page),
        "pageSize": "20",
    }
    with requests.get(URL_TRANSACTIONS, headers=HEADERS, params=params) as req:
        req.raise_for_status()
        new_transactions = req.json()

    transactions = []
    for transaction in new_transactions:
        if until and parse(transaction["date"]) <= until:
            break
        # betReference is None when it is a credit, so we assign an UUID to keep the transaction
        transactions.append(
            Transaction(
                transaction["betReference"] or str(uuid4()),
                transaction["date"],
                transaction["debitAmount"] or 0.0,
                transaction["totalAmount"] or transaction["creditAmount"] or 0.0,
            )
        )
    return transactions


def get_all_transactions(until: Optional[datetime.datetime]) -> Transactions:
    page = 1
    transactions = []
    while "there are transactions":
        new_transactions = get_transactions(page, until)
        if not new_transactions:
            break
        transactions.extend(new_transactions)
        page += 1
    return transactions


def sort_by_date(transactions: Transactions) -> Transactions:
    return sorted(set(transactions), key=attrgetter("date"))


def last_item(transactions: Transactions) -> Transaction:
    return sort_by_date(transactions)[-1]


def load_history(file: Path) -> Transactions:
    try:
        with file.open(mode="rb") as fh:
            data: Transactions = pickle.load(fh)
            return data
    except FileNotFoundError:
        return []


def save_history(file: Path, transactions: Transactions) -> None:
    with file.open(mode="wb") as fh:
        pickle.dump(transactions, fh)


def label_month(bet: Transaction) -> str:
    # date format: 09/04/2021 08:35
    _, month, year = bet.date.split(" ")[0].split("/")
    return f"{month}/{year}"


def label_year(bet: Transaction) -> str:
    # date format: 09/04/2021 08:35
    return bet.date[6:10]


def label_uid(bet: Transaction) -> str:
    return f"{bet.id}"


def group_by(transactions: Transactions, label_cb: Callable) -> Group:
    group: Group = {}
    for bet in transactions:
        label = label_cb(bet)
        try:
            group[label]["loss"] += bet.loss
            group[label]["win"] += bet.win
        except KeyError:
            group[label] = {"loss": bet.loss, "win": bet.win}
    return group


def plot_new_bets(transactions: Transactions) -> None:
    if not transactions:
        return
    plot("Nouveaux paris", transactions, label_uid, ["black", "green"])


def plot_all_bets(transactions: Transactions, yearly: bool = False) -> None:
    if not transactions:
        return
    plot(
        "Statistiques globales",
        transactions,
        label_year if yearly else label_month,
        ["red", "blue"],
        max_items=4 if yearly else 12,
    )


def plot(
    title: str,
    transactions: Transactions,
    label_cb: Callable,
    colors: List[str],
    max_items: int = 256,
) -> None:
    win = sum(bet.win for bet in transactions)
    loss = sum(bet.loss for bet in transactions)
    total = win - loss
    balance = fmt_number(total, suffix="€")
    suffix = "+" if total > 0 else ""

    lines = "@ Mises,Gains"
    it = sorted(group_by(transactions, label_cb).items())
    for idx, (label, values) in enumerate(it, start=1):
        if idx > max_items:
            break
        lines += f"\n{label},{values['loss']:.02f},{values['win']:.02f}"
    sys.stdin = StringIO(lines)

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
        "title": f"{title} ({suffix}{balance})",
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


def main(*args: Any) -> int:
    if "--help" in args:
        print("--no-update to disable metrics update")
        print("--yearly to display a yearly chart (instead of monthly)")
        return 0

    # Load saved metrics
    file = Path(__file__).parent / "data" / f"{LOGIN}.pickle"
    transactions = load_history(file)
    new_transactions = []

    # Update if not explicitely disallowed
    if "--no-update" not in args:
        HEADERS["X-CLIENT"] = request_auth()
        until = parse(last_item(transactions).date) if transactions else None
        new_transactions = [
            transaction
            for transaction in get_all_transactions(until=until)
            if transaction not in transactions
        ]

    if new_transactions:
        transactions.extend(new_transactions)
        transactions = sort_by_date(transactions)
        save_history(file, transactions)

    # Display nice charts
    plot_new_bets(new_transactions)
    plot_all_bets(transactions, yearly="--yearly" in args)

    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
