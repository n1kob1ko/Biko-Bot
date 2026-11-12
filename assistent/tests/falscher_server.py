"""Startet den echten Server mit einer falschen KI, für die Browser-Tests (tests/e2e.test.js).
Aufruf: python falscher_server.py <port> <daten-ordner>"""
import json
import math
import os
import re
import struct
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.update(PORT=sys.argv[1], DATA_DIR=sys.argv[2], APP_PASSWORT="test")
import server  # noqa: E402
from http.server import ThreadingHTTPServer  # noqa: E402


def falsche_ki(system, messages, max_tokens=4000, websuche=False, werkzeuge=None, beim_text=None, modell=None):
    time.sleep(0.4)  # damit "Biko denkt nach" sichtbar ist
    inhalt = messages[-1]["content"]   # vorne der Hinweis der App, dann die Frage
    frage = inhalt if isinstance(inhalt, str) else "".join(
        b["text"] for b in inhalt if b.get("type") == "text" and not b["text"].startswith("<app>"))
    if not frage and "Morgenrunde" in json.dumps(inhalt, ensure_ascii=False):   # Biko meldet sich von selbst
        return "Guten Morgen! In Wien wird es heute sonnig. Was hast du heute vor?"
    if frage.startswith("Was steht da?") and isinstance(inhalt, list) and any(b.get("type") == "image" for b in inhalt):
        return "Der Brief ist von den Wiener Netzen. Sie lesen am Dienstag den Zähler ab. Du musst nichts tun."
    antwort = antwort_fuer(frage, werkzeuge)
    if beim_text:   # wie die echte KI: die Antwort kommt in Stücken
        for stueck in re.findall(r"\S+\s*", antwort):
            beim_text(stueck)
            time.sleep(0.02)
    return antwort


def antwort_fuer(frage, werkzeuge):
    # So wie die echte KI: Biko schreibt sich Erinnerungen über seine Werkzeuge selbst auf
    if frage.startswith("Erinnere mich"):
        werkzeuge["erinnerung_merken"]["tun"]({"text": "Herztablette", "zeit": "08:00"})
        return "Mach ich. Ich erinnere dich jeden Tag um 8 Uhr an die Herztablette."
    if frage.startswith("Mein Blutdruck ist 135 zu 85"):
        werkzeuge["gesundheit_notieren"]["tun"]({"art": "blutdruck", "wert": "135/85", "notiz": "morgens"})
        werkzeuge["tagebuch_zeigen"]["tun"]({})
        return "Hab ich ins Tagebuch geschrieben: 135 zu 85. Das liegt etwas über dem üblichen Bereich."
    if frage.startswith("Frag mich jeden Tag um 10"):
        server.checkin_einstellen({"zeit": "10:00", "kontakte": [{"name": "Peter", "nummer": "0664 1234567"}]})
        return "Mach ich. Ich frag dich jeden Tag um 10. Meldest du dich bis 12 nicht, bekommt Peter eine SMS."
    if frage.startswith("Dolmetsch für mich beim Arzt"):
        server.dolmetscher({"an": True, "sprache_a": "Chinesisch", "sprache_b": "Deutsch"})
        return "Gern, ich übersetze jetzt. 好的，我现在帮你翻译。"
    if frage.startswith("我头疼三天了"):
        return "Ich habe seit drei Tagen Kopfschmerzen."
    if frage.startswith("Danke, fertig mit dem Dolmetschen"):
        server.dolmetscher({"an": False})
        return "Gern geschehen. Ich übersetze jetzt nicht mehr."
    if frage.startswith("Peter hat am 6. Jänner Geburtstag"):
        server.geburtstag_merken({"name": "Peter", "tag": 6, "monat": 1, "jahr": 1986})
        return "Das merk ich mir. Am 6. Jänner wird Peter 40, ich sag dir rechtzeitig Bescheid."
    if frage.startswith("Schreib Milch und Brot"):
        server.liste_aendern({"liste": "Einkaufen", "dazu": ["Milch", "Brot"]})
        werkzeuge["liste_zeigen"]["tun"]({"liste": "Einkaufen"})
        return "Hab ich aufgeschrieben. Auf der Einkaufsliste stehen jetzt Milch und Brot."
    if frage.startswith("Ich hab eine SMS von der Post"):
        werkzeuge["warnung_zeigen"]["tun"]({
            "stufe": "betrug", "titel": "Diese SMS ist nicht von der Post.",
            "anzeichen": ["Die Post verlangt keine Gebühr per SMS.", "Der Link führt nicht zu post.at."],
            "tun": ["Nicht auf den Link tippen.", "Die SMS löschen."]})
        werkzeuge["anruf_zeigen"]["tun"]({"name": "Peter", "nummer": "0664 123 4567"})
        return "Das ist sehr wahrscheinlich Betrug. Tipp nichts an. Magst du Peter anrufen?"
    if frage.startswith("Ruf Peter an"):
        werkzeuge["anruf_zeigen"]["tun"]({"name": "Peter", "nummer": "0664 123 4567"})
        return "Gern. Tipp auf den Knopf, dann geht das Telefon mit Peters Nummer auf."
    if frage.startswith("Schreib Peter auf WhatsApp"):
        werkzeuge["nachricht_zeigen"]["tun"]({"an": "Peter", "text": "Ich komme um 5!", "ueber": "whatsapp",
                                              "nummer": "0664 123 4567"})
        return "Hier ist die Nachricht für Peter."
    if frage.startswith("Meld dich"):
        werkzeuge["morgenrunde_einstellen"]["tun"]({"zeit": "08:00"})
        return "Gern. Ab jetzt melde ich mich jeden Morgen um 8 mit Wetter und Nachrichten."
    if frage.startswith("Ich hab Diabetes"):
        werkzeuge["wissen_merken"]["tun"]({"text": "Hat Diabetes"})
        return "Das merk ich mir. Dann schauen wir beim Essen auf den Zucker."
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


# Zwei Sekunden leiser Ton, roh wie vom echten Dienst (16 Bit, 24 kHz): so lange "spricht" Biko pro Satz
PCM = b"".join(struct.pack("<h", int(800 * math.sin(i / 24000 * 2 * math.pi * 220))) for i in range(48000))


def falscher_strom(pfad, daten, kopf=None):
    assert pfad.endswith("/stream?output_format=pcm_24000") and json.loads(daten)["text"], "falsche Anfrage zum Sprechen"
    return iter([PCM[i:i + 4800] for i in range(0, len(PCM), 4800)])


# Falscher Sprachdienst: liefert zum Vorlesen einen kurzen Ton und "versteht" aus jeder Aufnahme denselben Satz
def falscher_sprachdienst(pfad, daten=None, kopf=None):
    if pfad.startswith("/v2/voices"):
        return json.dumps({"voices": [{"voice_id": "test-stimme", "name": "Test"}]}).encode()
    if pfad == "/v1/single-use-token/realtime_scribe":
        return json.dumps({"token": "einmal-zugang"}).encode()
    if pfad.startswith("/v1/text-to-speech/"):
        with open(os.path.join(os.path.dirname(__file__), "ton.mp3"), "rb") as f:
            return f.read()
    assert b'name="file"' in daten and len(daten) > 500, "die Aufnahme fehlt"
    return json.dumps({"language_code": "de", "text": "Hallo Biko"}).encode()


server.frage_claude = falsche_ki
server.SPRACH_KEY = "test"
server.sprach_anfrage = falscher_sprachdienst
server.sprach_strom = falscher_strom
ThreadingHTTPServer(("127.0.0.1", int(sys.argv[1])), server.Handler).serve_forever()
