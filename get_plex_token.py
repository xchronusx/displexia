"""Fetch a Plex account token via the official plex.tv/link flow and write it to .env.

Run:  python3 get_plex_token.py
It prints a 4-character code. Go to https://plex.tv/link (signed into your Plex
account), enter the code, and this script saves the token into .env for you.
"""

import re
import sys
from pathlib import Path

from plexapi.myplex import MyPlexPinLogin

ENV_FILE = Path(__file__).resolve().parent / ".env"


def write_token(token: str):
    text = ENV_FILE.read_text()
    if re.search(r"^PLEX_TOKEN=.*$", text, flags=re.M):
        text = re.sub(r"^PLEX_TOKEN=.*$", f"PLEX_TOKEN={token}", text, flags=re.M)
    else:
        text += f"\nPLEX_TOKEN={token}\n"
    ENV_FILE.write_text(text)


def main():
    headers = {"X-Plex-Product": "displexia"}
    pinlogin = MyPlexPinLogin(headers=headers, oauth=False)
    print("\n  1. Open  https://plex.tv/link  (sign in as the Plex server owner)")
    print(f"  2. Enter this code:  {pinlogin.pin}\n")
    print("Waiting for you to link (up to 5 minutes)...")
    pinlogin.run(timeout=300)
    pinlogin.waitForLogin()
    if pinlogin.token:
        write_token(pinlogin.token)
        print("Token received and saved to .env — done.")
        return 0
    print("Timed out or link failed. Run this script again.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
