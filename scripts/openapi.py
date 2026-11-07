import json

from apps.api.config import ROOT
from apps.api.main import app


def main():
    path = ROOT / "apps/web/openapi.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(app.openapi(), indent=2) + "\n", encoding="utf-8")
    print(f"Exported {path}")


if __name__ == "__main__":
    main()
