"""Compatibilidade com imports do protótipo.

Código novo deve importar de ``src.domain.combat``. Este módulo será mantido por
algumas versões para não quebrar integrações e instalações existentes.
"""

from src.domain.combat import *  # noqa: F401,F403
from src.domain.combat import __all__
