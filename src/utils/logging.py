"""Formato común de los mensajes de log de los comandos del proyecto."""

import logging


def configure_logging(level: int | str = logging.INFO) -> None:
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
