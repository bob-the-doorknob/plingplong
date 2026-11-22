import unittest

from tools.generalization import SHA256, complete_label, digest, git_diff


class GeneralizationLabels(unittest.TestCase):
    def setUp(self):
        self.catalog = {'tests': [{'id': 'numbered'}], 'skipped': ['organizer-skip']}
        self.patch = b'patch'
        self.label = {'catalog_sha256': 'catalog', 'archive_sha256': SHA256,
                      'sha256': digest(self.patch), 'collected': ['numbered', 'organizer-skip'],
                      'finished': ['numbered'], 'failed': ['numbered'], 'skipped': ['organizer-skip'],
                      'errors': [], 'exit': 1}

    def test_complete_numbered_failure(self):
        self.assertTrue(complete_label(self.label, self.patch, self.catalog, 'catalog'))

    def test_incomplete_result_is_not_ground_truth(self):
        for update in ({'skipped': ['numbered']}, {'finished': []}, {'exit': 2}, {'failed': []},
                       {'errors': ['collection failure']}, {'sha256': 'stale'}, {'catalog_sha256': 'other'}):
            with self.subTest(update=update):
                self.assertFalse(complete_label(self.label | update, self.patch, self.catalog, 'catalog'))

    def test_patch_generation_keeps_git_newline_marker(self):
        self.assertTrue(git_diff('x', 'a\n', 'b').endswith('-a\n+b\n\\ No newline at end of file\n'))


if __name__ == '__main__':
    unittest.main()
