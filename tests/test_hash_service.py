import hashlib
import os
import tempfile
import unittest

from services.hash_service import (
    HashAlgorithm,
    calculate_file_hash,
    calculate_hashes_concurrent,
    get_recommended_workers,
)


class TestHashService(unittest.TestCase):
    def setUp(self):
        self.test_content = b"Hello, WINTools!"
        self.tmp = tempfile.NamedTemporaryFile(delete=False)
        self.tmp.write(self.test_content)
        self.tmp.close()

    def tearDown(self):
        os.unlink(self.tmp.name)

    def _expected_hash(self, algo: str) -> str:
        return hashlib.new(algo, self.test_content).hexdigest()

    def test_md5(self):
        result = calculate_file_hash(self.tmp.name, HashAlgorithm.MD5)
        self.assertEqual(result, self._expected_hash("md5"))

    def test_sha1(self):
        result = calculate_file_hash(self.tmp.name, HashAlgorithm.SHA1)
        self.assertEqual(result, self._expected_hash("sha1"))

    def test_sha256(self):
        result = calculate_file_hash(self.tmp.name, HashAlgorithm.SHA256)
        self.assertEqual(result, self._expected_hash("sha256"))

    def test_progress_callback(self):
        progress_log = []

        def callback(read, total):
            progress_log.append((read, total))

        calculate_file_hash(self.tmp.name, HashAlgorithm.MD5, progress_callback=callback)
        self.assertTrue(len(progress_log) > 0)
        self.assertEqual(progress_log[-1][0], progress_log[-1][1])  # 最终读取等于总大小

    def test_concurrent(self):
        results = calculate_hashes_concurrent(
            [self.tmp.name],
            algorithms=[HashAlgorithm.SHA256],
        )
        hashes = results[self.tmp.name]
        assert hashes is not None
        self.assertEqual(hashes["sha256"], self._expected_hash("sha256"))

    def test_get_recommended_workers(self):
        workers = get_recommended_workers()
        self.assertIsInstance(workers, int)
        self.assertGreaterEqual(workers, 1)


if __name__ == "__main__":
    unittest.main()
