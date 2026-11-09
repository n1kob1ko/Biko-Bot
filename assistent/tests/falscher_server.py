"""Startet den echten Server mit einer falschen KI, für die Browser-Tests (tests/e2e.test.js).
Aufruf: python falscher_server.py <port> <daten-ordner>"""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.update(PORT=sys.argv[1], DATA_DIR=sys.argv[2], APP_PASSWORT="test")
import server  # noqa: E402
from http.server import ThreadingHTTPServer  # noqa: E402


def falsche_ki(system, messages, max_tokens=4000, websuche=False):
    time.sleep(0.4)  # damit "Biko denkt nach" sichtbar ist
    frage = messages[-1]["content"]
    if any("一" <= z <= "鿿" for z in frage):
        return "这周 Billa 的咖啡打七折。价格可能会变哦。"
    if frage.startswith("An:"):
        return "Liebe Anna, vielen Dank für die schönen Blumen! Magst du am Sonntag auf einen Kaffee kommen?"
    return "Diese Woche gibt es bei Billa Kaffee um 30 % günstiger. Preise können sich ändern."


server.frage_claude = falsche_ki
ThreadingHTTPServer(("127.0.0.1", int(sys.argv[1])), server.Handler).serve_forever()
