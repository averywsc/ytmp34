from pathlib import Path


ROOT = Path(__file__).resolve().parent
TEMPLATE = ROOT / "templates" / "index.html"
LOCAL_APP_MARKER = 'data-local-app="{{ local_app }}"'


def build_site(output_directory=ROOT / "_site"):
    page = TEMPLATE.read_text(encoding="utf-8")
    if page.count(LOCAL_APP_MARKER) != 1:
        raise ValueError("The page must contain exactly one local app marker.")

    output_directory.mkdir(parents=True, exist_ok=True)
    (output_directory / "index.html").write_text(
        page.replace(LOCAL_APP_MARKER, 'data-local-app="false"'),
        encoding="utf-8",
    )


if __name__ == "__main__":
    build_site()
