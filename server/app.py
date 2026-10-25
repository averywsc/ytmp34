import io
import logging
import shutil
import tempfile
import textwrap
from pathlib import Path
from urllib.parse import urlparse

from flask import Flask, after_this_request, jsonify, render_template, request, send_file
from flask_cors import CORS
from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError


PROJECT_ROOT = Path(__file__).resolve().parent.parent
app = Flask(__name__, template_folder=str(PROJECT_ROOT / "templates"))
CORS(app, resources={r"/api/*": {"origins": "*"}})
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SCREENPLAYS = [
    {
        "slug": "halcyon",
        "title": "Halcyon",
        "description": "A city archivist discovers that a perfect society is built on carefully edited memories.",
        "story": "When Mara finds her own childhood missing from the civic archive, she traces the edits through the city's quiet systems. Each recovered memory brings one neighbor back into focus—and puts the carefully maintained peace at risk.",
    },
    {
        "slug": "residual",
        "title": "Residual",
        "description": "An isolated radio operator begins receiving messages from a settlement that vanished years ago.",
        "story": "Across a salt-flat outpost, Eli keeps a lonely watch over a dead frequency. A familiar voice returns in fragments, describing events that have not happened yet. To answer, Eli must decide whether the signal is a warning, an echo, or a voice asking not to be forgotten.",
    },
    {
        "slug": "incept-date",
        "title": "Incept Date",
        "description": "A restoration artist reconstructs the last day of a stranger's life from damaged recordings.",
        "story": "A commission arrives with no name, only a box of corrupted tapes. As Jo restores each recording, a tender portrait takes shape—along with evidence that the client knows much more about the missing voice than they admit.",
    },
    {
        "slug": "permafrost",
        "title": "Permafrost",
        "description": "A border-station medic must choose who gets shelter when the thaw comes early.",
        "story": "The winter outpost has room for one more family. When the ice road opens weeks ahead of schedule, the arrival of a second group turns a practical decision into a test of the community's idea of fairness.",
    },
    {
        "slug": "the-array",
        "title": "The Array",
        "description": "A maintenance crew on a remote listening station discovers a signal that responds to silence.",
        "story": "Nia and her small crew are paid to keep a field of old antennas running. A strange pattern appears only when they stop transmitting. Their attempt to hear it brings them closer together, and makes every interruption feel deliberate.",
    },
    {
        "slug": "leos-date",
        "title": "Leo's Date / Not With a Bang",
        "description": "Two strangers try to have an ordinary first date during a citywide blackout.",
        "story": "Leo planned every detail except the power cut. With the restaurant closed and their phones dead, he and Sam wander through a dark neighborhood, trading stories and discovering that an unplanned evening can be its own kind of beginning.",
    },
]

OUTPUT_FORMATS = {
    "mp3": {
        "extension": ".mp3",
        "postprocessor": {
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        },
    },
    "mp4": {
        "extension": ".mp4",
        "postprocessor": {
            "key": "FFmpegVideoConvertor",
            "preferedformat": "mp4",
        },
    },
}

SUPPORTED_VIDEO_HOSTS = {
    "youtu.be",
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "youtube-nocookie.com",
    "www.youtube-nocookie.com",
}


@app.get("/")
def index():
    return render_template("index.html", screenplays=SCREENPLAYS)


def build_script_pdf(screenplay):
    lines = [
        "AVERY BEUTH  /  SCREENPLAY NOTES",
        "",
        screenplay["title"],
        "",
        "LOGLINE",
        *textwrap.wrap(screenplay["description"], width=76),
        "",
        "STORY",
        *textwrap.wrap(screenplay["story"], width=76),
        "",
        "END",
    ]
    lines = lines[:38]

    def escape_pdf_text(value):
        return value.encode("ascii", "replace").decode("ascii").replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    text_commands = ["BT", "/F1 12 Tf", "52 744 Td", "17 TL"]
    for index, line in enumerate(lines):
        if index:
            text_commands.append("T*")
        text_commands.append(f"({escape_pdf_text(line)}) Tj")
    text_commands.append("ET")
    stream = "\n".join(text_commands).encode("ascii")

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier >>",
        b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"\nendstream",
    ]
    document = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for object_number, content in enumerate(objects, start=1):
        offsets.append(len(document))
        document.extend(f"{object_number} 0 obj\n".encode("ascii"))
        document.extend(content)
        document.extend(b"\nendobj\n")
    xref_offset = len(document)
    document.extend(f"xref\n0 {len(offsets)}\n".encode("ascii"))
    document.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        document.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    document.extend(
        f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode("ascii")
    )
    return bytes(document)


@app.get("/scripts/<slug>.pdf")
def download_script(slug):
    screenplay = next((item for item in SCREENPLAYS if item["slug"] == slug), None)
    if screenplay is None:
        return jsonify(error="That screenplay could not be found."), 404
    return send_file(
        io.BytesIO(build_script_pdf(screenplay)),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"{screenplay['slug']}.pdf",
    )


@app.post("/api/convert")
def convert():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify(error="Send a JSON object containing a URL and format."), 400

    url = payload.get("url", "")
    output_format = payload.get("format", "mp4")
    if not isinstance(url, str) or not url.strip():
        return jsonify(error="A video URL is required."), 400
    try:
        parsed_url = urlparse(url.strip())
        hostname = (parsed_url.hostname or "").lower().rstrip(".")
        port = parsed_url.port
    except ValueError:
        return jsonify(error="Enter a valid YouTube video URL."), 400
    if (
        parsed_url.scheme not in {"http", "https"}
        or hostname not in SUPPORTED_VIDEO_HOSTS
        or parsed_url.username is not None
        or parsed_url.password is not None
        or port not in {None, 80, 443}
    ):
        return jsonify(error="Enter a valid link from YouTube or youtu.be."), 400
    if not isinstance(output_format, str) or output_format not in OUTPUT_FORMATS:
        return jsonify(error="Choose either mp3 or mp4 as the output format."), 400
    if shutil.which("ffmpeg") is None:
        return jsonify(error="FFmpeg is required. Install FFmpeg and make it available on PATH."), 503

    temporary_directory = Path(tempfile.mkdtemp(prefix="ytmp34-"))
    configuration = OUTPUT_FORMATS[output_format]
    options = {
        "format": "bestvideo+bestaudio/best" if output_format == "mp4" else "bestaudio/best",
        "outtmpl": str(temporary_directory / "converted.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "postprocessors": [configuration["postprocessor"]],
    }
    if output_format == "mp4":
        options["merge_output_format"] = "mp4"

    try:
        with YoutubeDL(options) as downloader:
            downloader.download([url.strip()])

        converted_files = [
            path
            for path in temporary_directory.iterdir()
            if path.is_file() and path.suffix.lower() == configuration["extension"]
        ]
        if not converted_files:
            raise RuntimeError("The converter did not produce the requested output file.")

        converted_file = converted_files[0]

        @after_this_request
        def schedule_temporary_file_cleanup(response):
            response.direct_passthrough = False
            response.call_on_close(lambda: shutil.rmtree(temporary_directory))
            return response

        return send_file(
            converted_file,
            mimetype="audio/mpeg" if output_format == "mp3" else "video/mp4",
            as_attachment=True,
            download_name=converted_file.name,
        )
    except DownloadError as error:
        shutil.rmtree(temporary_directory, ignore_errors=True)
        logger.warning("Video conversion failed: %s", error)
        detail = str(error).strip() or "yt-dlp did not provide further details."
        return jsonify(error=f"yt-dlp could not download or convert this video: {detail}"), 422
    except Exception as error:
        shutil.rmtree(temporary_directory, ignore_errors=True)
        logger.exception("Unexpected video conversion error")
        detail = str(error).strip() or type(error).__name__
        return jsonify(error=f"Unexpected conversion error: {detail}"), 500


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
