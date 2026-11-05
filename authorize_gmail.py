"""Create a fresh local Gmail OAuth token without processing any mail.

Run this after downloading a new Google Cloud OAuth Desktop client JSON. The
script only writes token.json; it never lists, reads, or marks Gmail messages.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow


SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Authorize Gmail for Scholar Alert collection")
    parser.add_argument("--credentials-file", default="credentials.json")
    parser.add_argument("--token-file", default="token.json")
    args = parser.parse_args()

    credentials_file = Path(args.credentials_file)
    token_file = Path(args.token_file)
    if not credentials_file.exists():
        raise SystemExit(f"Missing OAuth client file: {credentials_file}")

    flow = InstalledAppFlow.from_client_secrets_file(str(credentials_file), SCOPES)
    credentials = flow.run_local_server(port=0)
    token_file.write_text(credentials.to_json(), encoding="utf-8")
    print(f"Wrote fresh Gmail token to {token_file}")


if __name__ == "__main__":
    main()
