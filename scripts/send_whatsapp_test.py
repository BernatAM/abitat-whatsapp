import json
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

TO_PHONE = "34657705038"
MESSAGE = "Mensaje de prueba"
TOKEN = "EAANR0fh7QtMBRd2NGyIvPNPlZCyX2x1lC11Q6VsPtjeWmVFR4ZB7MVxOauKUCn9TZBy6feBNcnygIZBB2ZBJpZCEvuhkQiV3CeuQASk0i2usvRiZBc6CXeL31GMBmqnUVNmqZCUN8sbayZC9igKY04XQbpZArZA4fPf1JoqFj9rmCjZBzzh8g62rMBpWX9nfRwMOfhoPKAZDZD"
PHONE_NUMBER_ID = "1119122344609258"
GRAPH_VERSION = "v23.0"


def main() -> int:
    if TOKEN == "PEGA_AQUI_TU_ACCESS_TOKEN" or PHONE_NUMBER_ID == "PEGA_AQUI_TU_PHONE_NUMBER_ID":
        print("Configura TOKEN y PHONE_NUMBER_ID directamente en este script antes de ejecutarlo.")
        return 1

    url = f"https://graph.facebook.com/{GRAPH_VERSION}/{PHONE_NUMBER_ID}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "to": TO_PHONE,
        "type": "text",
        "text": {"body": MESSAGE},
    }

    request = Request(
        url=url,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": "application/json",
        },
    )

    try:
        with urlopen(request, timeout=20) as response:
            body = response.read().decode("utf-8")
            print(body)
            return 0
    except HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        print(f"HTTP {exc.code}")
        print(error_body)
        return 2
    except URLError as exc:
        print(f"Network error: {exc.reason}")
        return 3


if __name__ == "__main__":
    sys.exit(main())
