# Convert

The GitHub Pages site includes the local setup instructions. Video conversion runs on your own computer.

## Run locally

1. Install Python 3.10 or newer.
2. Install [FFmpeg](https://ffmpeg.org/download.html) and make sure `ffmpeg` is available on your PATH.
3. Download this repository with **Code → Download ZIP** and extract it.
4. Open a terminal in the extracted folder and run `py run.py` on Windows or `python3 run.py` on macOS/Linux.
5. Open `http://127.0.0.1:5000`. Keep the terminal open while converting.

The first launch installs the Python dependencies. Only download videos you have permission to use.

## Publish the instructions with GitHub Pages

In the GitHub repository, open **Settings → Pages**, select **GitHub Actions** as the source, then push to `main` or `master`. The **Deploy GitHub Pages** workflow publishes the local setup guide. The hosted page does not convert videos; use the local app for that.

## Test

```sh
python -m pip install -r server/requirements.txt
python -m unittest server.test_app -v
```
