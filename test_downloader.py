"""Offline regression tests: python -m unittest test_downloader -v."""

import os
import queue
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

with patch("dotenv.load_dotenv"), patch.dict(os.environ, {
    "CLIENT_ID": "test-client", "CLIENT_SECRET": "test-secret",
    "REDIRECT_URL": "http://127.0.0.1:8888/callback",
}):
    import dl


class DownloadWorkerTests(unittest.TestCase):
    def run_worker(self, tasks):
        updates = queue.Queue()
        worker = threading.Thread(
            target=dl.download_worker, args=(tasks, updates), daemon=True
        )
        worker.start()
        worker.join(timeout=3)
        self.assertFalse(worker.is_alive(), "Worker hung after finishing its queue")
        self.assertEqual(tasks.unfinished_tasks, 0)
        messages = []
        while not updates.empty():
            messages.append(updates.get_nowait())
        self.assertEqual(messages[-1], ("status", "Idle"))
        return messages

    def test_empty_queue_finishes(self):
        self.run_worker(queue.Queue())

    def test_stop_sentinel_is_acknowledged(self):
        tasks = queue.Queue()
        tasks.put(None)
        self.run_worker(tasks)

    def test_failed_download_finishes_and_reports_progress(self):
        tasks = queue.Queue()
        tasks.put(dl.DownloadTask(1, 1, {
            "title": "Test", "artists": "Artist", "album": "Album",
            "release_date": "", "cover_url": None, "genre": "Unknown",
        }))
        with tempfile.TemporaryDirectory() as folder, \
                patch.object(dl, "DOWNLOAD_DIR", folder), \
                patch.object(dl.time, "sleep"), \
                patch.object(dl.yt_dlp, "YoutubeDL", side_effect=RuntimeError("offline")):
            messages = self.run_worker(tasks)
        self.assertIn(("progress", 1.0), messages)
        self.assertTrue(any("offline" in str(value) for _, value in messages))

    def test_stop_prevents_restart_until_worker_finishes(self):
        app = Mock()
        app.downloading = True
        app.colors = {"warning": "orange", "success": "green"}
        app.task_queue = queue.Queue()
        app.task_queue.put("pending track")
        dl.App.stop_download(app)
        self.assertTrue(app.downloading)
        self.assertEqual(app.start_btn.configure.call_args.kwargs["state"], "disabled")
        self.assertIsNone(app.task_queue.get_nowait())
        app.task_queue.task_done()
        self.assertEqual(app.task_queue.unfinished_tasks, 0)

    def test_playlist_error_callback_keeps_exception_message(self):
        app = Mock()
        callbacks = []
        app.after.side_effect = lambda delay, callback: callbacks.append(callback)
        app.executor.submit.side_effect = lambda callback: callback()
        with patch.object(dl, "get_user_playlists", side_effect=RuntimeError("offline")):
            dl.App.refresh_playlists(app)
        callbacks[0]()
        app._update_playlist_ui.assert_called_once_with([], "offline")


if __name__ == "__main__":
    unittest.main()
