import unittest

from database import Database
from src.infrastructure.repositories import (
    CharacterRepository,
    EnemyRepository,
    SkillRepository,
)


class RepositoryContractTests(unittest.TestCase):
    def test_sqlite_database_satisfies_initial_repository_contracts(self):
        database = Database(":memory:")
        try:
            self.assertIsInstance(database, CharacterRepository)
            self.assertIsInstance(database, SkillRepository)
            self.assertIsInstance(database, EnemyRepository)
        finally:
            database.close()


if __name__ == "__main__":
    unittest.main()
