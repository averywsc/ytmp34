import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from build_pages import build_site
from yt_dlp.utils import DownloadError

from server.app import app


class ConverterAppTests(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True)
        self.client = app.test_client()

    def test_home_page_renders_converter(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"<h1>Convert</h1>", response.data)
        self.assertIn(b'placeholder="Paste a YouTube link"', response.data)
        self.assertIn(b'id="quality-select"', response.data)
        self.assertIn(b'data-local-app="true"', response.data)
        self.assertIn(b"Run on your computer", response.data)
        self.assertIn(b'aria-live="polite"', response.data)
        self.assertIn(b"/api/convert", response.data)

    def test_github_pages_build_disables_conversion_and_shows_local_guide(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            build_site(Path(temporary_directory))
            page = (Path(temporary_directory) / "index.html").read_text(
                encoding="utf-8"
            )

        self.assertIn('data-local-app="false"', page)
        self.assertNotIn("{{ local_app }}", page)
        self.assertIn("Start the app locally to convert files.", page)
        self.assertIn("py run.py", page)
        self.assertIn("python3 run.py", page)

    def test_health_endpoint(self):
        response = self.client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"status": "ok"})

    def test_rejects_invalid_payloads_and_non_youtube_urls(self):
        requests = [
            (None, 400),
            ({"url": "", "format": "mp3"}, 400),
            ({"url": "https://example.com/watch?v=1", "format": "mp3"}, 400),
            ({"url": "https://youtube.com.evil.test/watch?v=1", "format": "mp3"}, 400),
            ({"url": "https://youtube.com:8080/watch?v=1", "format": "mp3"}, 400),
            ({"url": "https://user@youtube.com/watch?v=1", "format": "mp3"}, 400),
            ({"url": "ftp://youtube.com/watch?v=1", "format": "mp3"}, 400),
            ({"url": "https://youtube.com:invalid/watch?v=1", "format": "mp3"}, 400),
            ({"url": "https://youtu.be/example", "format": "wav"}, 400),
            ({"url": "https://youtu.be/example", "format": "mp3", "quality": "1080"}, 400),
            ({"url": "https://youtu.be/example", "format": "mp4", "quality": "320"}, 400),
            ({"url": "https://youtu.be/example", "format": "mp3", "quality": 192}, 400),
        ]

        with patch("server.app.shutil.which") as find_ffmpeg, patch(
            "server.app.YoutubeDL"
        ) as youtube_dl:
            for payload, expected_status in requests:
                with self.subTest(payload=payload):
                    response = self.client.post("/api/convert", json=payload)
                    self.assertEqual(response.status_code, expected_status)
                    self.assertIn("error", response.get_json())

        find_ffmpeg.assert_not_called()
        youtube_dl.assert_not_called()

    def test_reports_missing_ffmpeg(self):
        with patch("server.app.shutil.which", return_value=None), patch(
            "server.app.YoutubeDL"
        ) as youtube_dl:
            response = self.client.post(
                "/api/convert",
                json={"url": "https://youtube.com/watch?v=example", "format": "mp3"},
            )

        self.assertEqual(response.status_code, 503)
        self.assertIn("FFmpeg is required", response.get_json()["error"])
        youtube_dl.assert_not_called()

    def test_converts_mp3_and_mp4_and_cleans_up_downloads(self):
        downloader_options = []

        class FakeDownloader:
            def __init__(self, options):
                self.options = options
                downloader_options.append(options)

            def __enter__(self):
                return self

            def __exit__(self, exception_type, exception, traceback):
                return False

            def download(self, urls):
                self.urls = urls
                extension = "mp3" if "FFmpegExtractAudio" in str(
                    self.options["postprocessors"]
                ) else "mp4"
                output_path = self.options["outtmpl"].replace(
                    "%(ext)s", extension
                )
                Path(output_path).write_bytes(b"converted media")

        with tempfile.TemporaryDirectory() as root:
            created_directories = []

            def create_temporary_directory(prefix):
                directory = Path(root) / f"{prefix}{len(created_directories)}"
                directory.mkdir()
                created_directories.append(directory)
                return str(directory)

            with patch("server.app.shutil.which", return_value="ffmpeg"), patch(
                "server.app.tempfile.mkdtemp",
                side_effect=create_temporary_directory,
            ), patch("server.app.YoutubeDL", FakeDownloader):
                for output_format, mime_type in (
                    ("mp3", "audio/mpeg"),
                    ("mp4", "video/mp4"),
                ):
                    with self.subTest(output_format=output_format):
                        response = self.client.post(
                            "/api/convert",
                            json={
                                "url": " https://youtu.be/example ",
                                "format": output_format,
                                "quality": "320" if output_format == "mp3" else "720",
                            },
                        )
                        self.assertEqual(response.status_code, 200)
                        self.assertEqual(response.data, b"converted media")
                        self.assertEqual(response.mimetype, mime_type)
                        self.assertIn(
                            f"converted.{output_format}",
                            response.headers["Content-Disposition"],
                        )
                        temporary_directory = created_directories[-1]
                        self.assertTrue(temporary_directory.exists())
                        response.close()
                        self.assertFalse(temporary_directory.exists())

        self.assertEqual(
            downloader_options[0]["postprocessors"][0]["preferredquality"], "320"
        )
        self.assertEqual(
            downloader_options[1]["format"],
            "bestvideo[height<=720]+bestaudio/best[height<=720]",
        )

    def test_returns_download_errors_as_unprocessable(self):
        with patch("server.app.shutil.which", return_value="ffmpeg"), patch(
            "server.app.YoutubeDL", side_effect=DownloadError("video unavailable")
        ):
            response = self.client.post(
                "/api/convert",
                json={"url": "https://youtube.com/watch?v=example", "format": "mp3"},
            )

        self.assertEqual(response.status_code, 422)
        self.assertIn("video unavailable", response.get_json()["error"])

    def test_cleans_up_when_converter_produces_no_file(self):
        class EmptyDownloader:
            def __init__(self, options):
                self.options = options

            def __enter__(self):
                return self

            def __exit__(self, exception_type, exception, traceback):
                return False

            def download(self, urls):
                return None

        with tempfile.TemporaryDirectory() as root:
            temporary_directory = Path(root) / "conversion"

            def create_temporary_directory(prefix):
                temporary_directory.mkdir()
                return str(temporary_directory)

            with patch("server.app.shutil.which", return_value="ffmpeg"), patch(
                "server.app.tempfile.mkdtemp",
                side_effect=create_temporary_directory,
            ), patch("server.app.YoutubeDL", EmptyDownloader):
                response = self.client.post(
                    "/api/convert",
                    json={
                        "url": "https://youtube.com/watch?v=example",
                        "format": "mp4",
                    },
                )

        self.assertEqual(response.status_code, 500)
        self.assertIn("did not produce", response.get_json()["error"])
        self.assertFalse(temporary_directory.exists())


if __name__ == "__main__":
    unittest.main()
