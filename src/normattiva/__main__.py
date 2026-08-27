"""Rende eseguibile il pacchetto: `python -m normattiva` equivale al comando `normattiva`.

Utile quando lo script non è sul PATH, per esempio in un ambiente virtuale non
attivato o in un container dove si invoca sempre l'interprete.
"""

from normattiva.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
