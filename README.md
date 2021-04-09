# Paris en Ligne

Statistiques simples des paris effectués sur [Betclic](https://www.betclic.fr/).

## Installation

```shell
$ python -m pip install -U pip
$ python -m pip install -r requirements.txt
```

## Utilisation

### Synchroniser l'Historique Local

```shell
$ python get.py
```

![Aperçu][apercu]

[apercu]: preview-update.png

### Affichage par Année

```shell
$ python get.py --yearly
```

![Aperçu par année][apercu-annees]

[apercu-annees]: preview-yearly.png

### Zéro Mise à Jour

Il est possible de seulement afficher les données locales :

```shell
$ python get.py --no-update
```
