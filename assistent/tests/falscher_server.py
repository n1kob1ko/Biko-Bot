"""Startet den echten Server mit einer falschen KI, für die Browser-Tests (tests/e2e.test.js).
Aufruf: python falscher_server.py <port> <daten-ordner>"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.update(PORT=sys.argv[1], DATA_DIR=sys.argv[2], APP_PASSWORT="test")
import server  # noqa: E402
from http.server import ThreadingHTTPServer  # noqa: E402


def falsche_ki(system, messages, max_tokens=4000, websuche=False, werkzeuge=None):
    time.sleep(0.4)  # damit "Biko denkt nach" sichtbar ist
    frage = messages[-1]["content"]
    # So wie die echte KI: Biko schreibt sich Erinnerungen über seine Werkzeuge selbst auf
    if frage.startswith("Erinnere mich"):
        werkzeuge["erinnerung_merken"]["tun"]({"text": "Herztablette", "zeit": "08:00"})
        return "Mach ich. Ich erinnere dich jeden Tag um 8 Uhr an die Herztablette."
    if frage.startswith("Vergiss"):
        werkzeuge["erinnerung_loeschen"]["tun"]({"id": server.erinnerungen_lesen()[0]["id"]})
        return "Erledigt, daran erinnere ich dich nicht mehr."
    if frage.startswith("给安娜"):
        werkzeuge["nachricht_zeigen"]["tun"]({"an": "安娜", "text": "亲爱的安娜，谢谢你送的花！周日来家里喝咖啡好吗？"})
        return "这是给安娜的消息。"
    if "茶" in frage:
        werkzeuge["link_zeigen"]["tun"]({"titel": "Billa 本周传单", "url": "https://www.billa.at/flugblatt"})
        return "茶的具体优惠我没有找到。你可以自己看看传单。"
    if any("一" <= z <= "鿿" for z in frage):
        return "这周 Billa 的咖啡打七折。价格可能会变哦。"
    # Nachricht für jemanden: Biko stellt den fertigen Text unter seine Antwort
    if frage.startswith("Schreib Anna"):
        werkzeuge["nachricht_zeigen"]["tun"]({
            "an": "Anna", "text": "Liebe Anna, vielen Dank für die schönen Blumen! Magst du am Sonntag auf einen Kaffee kommen?"})
        return "Hier ist die Nachricht für Anna."
    # Nichts Genaues gefunden: Biko stellt den Prospekt als Knopf ins Gespräch
    if "Tee" in frage:
        werkzeuge["link_zeigen"]["tun"]({"titel": "Billa Flugblatt", "url": "https://www.billa.at/flugblatt"})
        return "Genaues zu Tee habe ich nicht gefunden. Schau am besten selbst ins Flugblatt."
    return "Diese Woche gibt es bei Billa Kaffee um 30 % günstiger. Preise können sich ändern."


# Falscher Sprachdienst: liefert zum Vorlesen einen kurzen Ton und "versteht" aus jeder Aufnahme denselben Satz
def falscher_sprachdienst(pfad, daten=None, kopf=None):
    if pfad.startswith("/v2/voices"):
        return json.dumps({"voices": [{"voice_id": "test-stimme", "name": "Test"}]}).encode()
    if pfad.startswith("/v1/text-to-speech/"):
        with open(os.path.join(os.path.dirname(__file__), "ton.mp3"), "rb") as f:
            return f.read()
    assert b'name="file"' in daten and len(daten) > 500, "die Aufnahme fehlt"
    return json.dumps({"language_code": "de", "text": "Hallo Biko"}).encode()


server.frage_claude = falsche_ki
server.SPRACH_KEY = "test"
server.sprach_anfrage = falscher_sprachdienst
ThreadingHTTPServer(("127.0.0.1", int(sys.argv[1])), server.Handler).serve_forever()
