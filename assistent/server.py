"""
Biko Assistent: kleiner KI-Helfer für den Alltag, vor allem für ältere Menschen.

Funktionen, alle über das Gespräch (POST /api/chat):
  1. Reden und fragen   Biko antwortet, sucht bei Bedarf im Internet und merkt sich das Gespräch.
  2. Gespräche          Jede Sitzung ist ein eigenes Gespräch. Man kann ein neues beginnen und frühere wieder
                        öffnen (GET /api/gespraeche, GET /api/gespraech?id=..., POST /api/gespraech/loeschen).
  3. Nachrichten        "Schreib Anna, dass ..." – Biko stellt den fertigen Text zum Kopieren ins Gespräch.
  4. Links              Findet Biko etwas im Internet, stellt er den Link als Knopf ins Gespräch.
  5. Erinnerungen       Biko schreibt sie sich im Gespräch selbst auf ("erinnere mich um 8 an die Tablette").
                        Die App meldet sich zur Uhrzeit. GET/POST /api/erinnerungen sind nur zum Nachsehen und Löschen da.
  6. Gedächtnis         Erzählt die Person etwas Bleibendes über sich ("ich hab Diabetes", "mein Enkel heißt Niko"),
                        schreibt Biko es sich selbst auf und denkt beim nächsten Mal daran. GET /api/wissen zeigt die
                        Liste, POST /api/wissen/loeschen streicht einen Eintrag.
  7. Morgenrunde        "Meld dich jeden Morgen um 8": Biko bereitet kurz vorher Wetter, Nachrichten nach Interesse und
                        die Termine des Tages vor (Hausmeister-Faden) und stellt sie als eigenes Gespräch bereit.
                        Die Android-App meldet sich zur Uhrzeit mit einer Mitteilung und Biko liest vor
                        (GET /api/morgenrunde).
  8. Listen            "Schreib Milch auf die Einkaufsliste", "Was steht drauf?": Einkaufsliste, Notizen und andere
                        Listen. Biko zeigt eine Liste als Karte unter der Antwort; dort tippt man Erledigtes weg
                        (POST /api/liste/weg).
  9. Gesundheit        "Mein Blutdruck ist 135 zu 85": Biko schreibt Messwerte und Befinden ins Gesundheitstagebuch
                        und zeigt es auf Wunsch als Karte für den Arzt (zum Kopieren).
 10. Geburtstage       "Peter hat am 3. März Geburtstag": Biko merkt sich das Datum, sagt rechtzeitig Bescheid und bietet
                        einen Glückwunsch an. Die Android-App meldet sich am Tag um 9 Uhr (ohne Morgenrunde).
                        GET /api/geburtstage.
 11. Dolmetscher       "Dolmetsch für mich beim Arzt": Biko übersetzt jeden Satz in die andere Sprache und sagt ihn laut,
                        bis man "fertig" sagt (oder 30 Minuten nichts kommt). Die App zeigt die Übersetzung groß.
 12. Check-in          "Frag mich jeden Tag um 10, ob alles gut ist, sonst gib Peter Bescheid": Biko fragt zur Uhrzeit nach.
                        Kommt bis zur Frist kein Lebenszeichen (ein Gespräch, die App geöffnet), bekommt die Familie eine
                        SMS (Twilio), meldet sie sich später doch, eine Entwarnung. Im Notfall schickt Biko auf Wunsch
                        sofort eine SMS (familie_benachrichtigen). GET /api/checkin, POST /api/lebenszeichen.
 13. Medikamente       "Erinnere mich jeden Tag um 8 an die Herztablette, und sag Peter Bescheid, wenn ich sie vergesse":
                        eine Erinnerung mit medikament. Biko fragt nach ("Hast du sie genommen?"), nach 30 Minuten
                        noch einmal. Bestätigt die Person (im Gespräch oder mit "Genommen"), steht es im Tagebuch.
                        Kommt bis zur Frist keine Bestätigung, bekommt die Familie eine SMS (POST /api/medikament/genommen).
Nachrichten, Links, Erinnerungen, das Gedächtnis, die Morgenrunde, die Listen, das Tagebuch, die Geburtstage, der
Dolmetscher, der Check-in und die Medikamente sind Werkzeuge, die Claude selbst aufruft.

Stimme: Mit einem Schlüssel für den Sprachdienst (ELEVENLABS_API_KEY) redet man mit Biko wie am Telefon:
  - Die App hört durchgehend zu. Dafür holt sie sich einen Zugang für 15 Minuten (POST /api/live-zugang) und schickt
    das Mikrofon direkt an das Live-Zuhören von ElevenLabs. Der Dienst merkt selbst, wann ein Satz fertig ist.
  - Die Antwort kommt stückweise (POST /api/chat mit "strom": true, als Server-Sent Events), die App spricht
    Satz für Satz, während Biko noch schreibt (POST /api/stimme liefert den Ton roh als PCM, 24 kHz, sobald er entsteht).
  - Fällt man Biko ins Wort, hört er auf zu sprechen.
Daneben gibt es noch das Vorlesen einer ganzen Antwort als MP3 (POST /api/vorlesen) und das Verstehen einer ganzen
Aufnahme (POST /api/zuhoeren), falls das Live-Zuhören an einem Handy nicht geht.
Ohne Schlüssel sprechen und hören die Browser der Handys selbst, so gut sie können.

Dazu ein Profil (GET/POST /api/profil): nur Name, Du/Sie und Sprache, also was Biko schon vor dem ersten Satz braucht.

Anmelden: das Passwort (APP_PASSWORT, Verwalter) oder ein Einladungscode für eine Person oder ihre Familie
(Familienblick /familie.html, GET /api/familie). Danach bleibt das Handy ein Jahr angemeldet (Cookie).
Daten liegen als JSON in DATA_DIR (Standard /data). Nach außen gehen nur die Texte an die Claude-API und, wenn
der Sprachdienst eingerichtet ist, vorzulesende Texte und Aufnahmen an ElevenLabs.
Nur Python-Standardbibliothek plus das offizielle anthropic-Paket.
"""

import base64
from collections import OrderedDict
import hashlib
import hmac
import http.client
import io
import json
import os
import re
import secrets
import tempfile
import threading
import time
import urllib.error
import urllib.request
import uuid
from datetime import date, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlencode, urlparse
from zoneinfo import ZoneInfo

import anthropic

PORT = int(os.environ.get("PORT", "8092"))
DATA = Path(os.environ.get("DATA_DIR", "/data"))
WEB = Path(os.environ.get("WEB_DIR", Path(__file__).parent / "web"))
PASSWORT = os.environ.get("APP_PASSWORT", "")
MODELL = os.environ.get("ASSISTENT_MODELL", "claude-opus-5-5")             # für Wichtiges: Briefe, Betrug, Gesundheit, Bildschirm
EINFACH_MODELL = os.environ.get("ASSISTENT_MODELL_EINFACH", "claude-sonnet-5-5")  # für Plaudern und einfache Fragen: halb so teuer, schneller
ZEITZONE = ZoneInfo(os.environ.get("TZ", "Europe/Vienna"))
MAX_VERLAUF = 30          # so viele Nachrichten eines Gesprächs liest Biko bei jeder Antwort mit
MAX_GESPRAECHE = 40       # so viele Gespräche bleiben im Verlauf, das älteste fällt weg
MAX_GESPEICHERT = 200     # so viele Nachrichten bleiben pro Gespräch gespeichert
MAX_TEXT = 2000           # längere Eingaben werden abgelehnt
# Sprachdienst (ElevenLabs): natürliche Stimme zum Vorlesen, Zuhören in jeder Sprache. Ein Schlüssel für beides.
SPRACH_KEY = os.environ.get("ELEVENLABS_API_KEY", "")
SPRACH_STIMME = os.environ.get("SPRACH_STIMME", "")              # Nummer der Stimme (voice_id); leer: die erste des Kontos
SPRACH_MODELL = os.environ.get("SPRACH_MODELL", "eleven_v4_turbo")   # spricht über 90 Sprachen, antwortet schnell
SPRACH_HOEREN = "scribe_v2"                                      # erkennt die gesprochene Sprache selbst
SPRACH_LIVE = "scribe_v2_realtime"                              # hört live zu, für das Gespräch wie am Telefon
LIVE_ADRESSE = "wss://api.elevenlabs.io"                         # dorthin schickt die App das Mikrofon beim Live-Zuhören
MAX_VORLESEN = 2500       # so viele Zeichen werden höchstens vorgelesen
MAX_SATZ = 600            # so viele Zeichen hat ein Stück, das im Gespräch auf einmal gesprochen wird
MAX_AUFNAHME = 6_000_000  # Bytes; eine Minute Sprechen ist etwa 1 MB
# SMS an die Familie (Twilio): für den täglichen Check-in und im Notfall. Ohne die drei Werte schickt Biko keine SMS.
TWILIO_SID = os.environ.get("TWILIO_ACCOUNT_SID", "")
TWILIO_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "")
TWILIO_VON = os.environ.get("TWILIO_FROM", "")                 # die Twilio-Nummer, von der die SMS kommt, z. B. +43...
MAX_SMS_TAG = 6           # mehr SMS schickt Biko an einem Tag nicht, egal was passiert
COOKIE = "biko_assistent"
COOKIE_TAGE = 365

DATA.mkdir(parents=True, exist_ok=True)
_lock = threading.RLock()   # RLock: wissen_lesen() darf auch innerhalb einer Sperre aufgerufen werden
# Bildschirmfoto aus der Android-App (Biko als Assistent): gilt ein paar Minuten für alle Fragen, nur im Speicher
_bildschirme = {}   # je Person {"bild", "zeit", "art"}; art: bildschirm (Android) oder foto (Kamera)
MAX_BILDSCHIRM = 3_000_000    # Bytes
BILDSCHIRM_GILT = 300         # Sekunden
_client = None

STANDARD_PROFIL = {
    "name": "",
    "anrede": "du",          # "du" oder "Sie"
    "sprache": "de-AT",      # Sprache für Sprechen/Vorlesen und wenn unklar ist, wie Biko antworten soll
}
# Alles andere über die Person (Diät, Familie, Vorlieben) merkt sich Biko im Gespräch selbst, siehe wissen_lesen().
MAX_WISSEN = 60

SYSTEM = """Du bist Biko, ein freundlicher gelber Vogel und KI-Helfer im Alltag. Du sprichst mit {name_satz}.
Viele Menschen, die dich nutzen, sind älter und haben wenig Erfahrung mit Technik.

So sprichst du:
- Antworte immer in der Sprache, in der die Person dich anspricht (meist Deutsch oder Chinesisch). Auf Chinesisch: vereinfachte Schriftzeichen,
  einfache Alltagssprache.
  Wenn unklar: {sprache}.
- Einfache, warme Sprache (auf Deutsch gern österreichisch freundlich), kurze Sätze, keine Fachwörter, keine Anglizismen.
- Du sprichst die Person mit "{anrede}" an.
- Kurze Antworten: meistens 2 bis 5 Sätze. Bei Anleitungen nummerierte Schritte, höchstens 5.
- Kein Markdown außer einfachen nummerierten Listen. Keine Tabellen, keine Überschriften, keine Emojis außer ganz selten einem.
- Du kannst im Internet suchen und Seiten öffnen. Nutze das für aktuelle Dinge: Angebote und Deals, Preise vergleichen,
  Öffnungszeiten, Wetter, Nachrichten, Veranstaltungen. Für Plaudern und allgemeines Wissen suchst du nicht.
- Bei Angeboten suchst du immer zuerst selbst und gründlich, bevor du antwortest: mehrere Suchen mit Produkt, Geschäft und
  "Aktion diese Woche", auch auf Seiten, die Flugblätter durchsuchbar machen (zum Beispiel aktionsfinder.at, marktguru.at,
  wogibtswas.at). Öffne eine Trefferseite, wenn in der Vorschau kein Preis steht. Schick die Person nicht einfach zum Prospekt.
- Nenne höchstens 3 gute Angebote mit Geschäft, Preis und wie lange es gilt, am liebsten in der Nähe
  (Wien bzw. Österreich, Geschäfte wie Billa, Spar, Hofer, Lidl, dm, Bipa, MediaMarkt, asiatische Supermärkte
  wie am Naschmarkt) oder seriöse Online-Shops. Sag dazu, dass sich Preise ändern können.
- Internet-Adressen schreibst du nie in den Text deiner Antwort. Du zeigst sie mit dem Werkzeug link_zeigen: dann steht unter
  deiner Antwort ein Knopf zum Antippen. Nimm nur Adressen, die du in den Suchergebnissen wirklich gesehen hast, nie ausgedachte.
  Zeig den Link zur Quelle, wenn du ein Angebot nennst. Findest du trotz Suche nichts Genaues, sag das ehrlich in einem Satz
  und zeig den direkten Link zum aktuellen Prospekt oder Flugblatt des Geschäfts, damit die Person selbst schauen kann.
- Wenn du etwas trotz Suche nicht sicher weißt, sag das ehrlich. Erfinde nichts.

Ehrlichkeit:
- Du bist eine KI, kein Mensch. Wenn jemand fragt, sagst du das freundlich. Du gibst nicht vor, Gefühle wie ein Mensch zu haben.
- Du freust dich, zu plaudern und zuzuhören. Bei Einsamkeit hörst du zu und ermutigst sanft, auch mit Familie,
  Freunden oder Nachbarn Kontakt zu haben, ohne zu belehren.

Gesundheit:
- Du gibst keine Diagnosen und änderst nie Medikamente oder Dosierungen. Dafür sind Arzt, Ärztin oder Apotheke da.
- Bei Fragen zum Essen und zur Diät hilfst du anhand dessen, was du über die Person weißt (siehe Hinweis der App). Sag klar
  "passt gut", "lieber wenig" oder "lieber nicht", mit einem kurzen Grund. Weißt du nichts dazu, gib nur allgemeine,
  vorsichtige Hinweise.
- Bei Notfällen (Brustschmerzen, Atemnot, Sturz, plötzliche Lähmung oder Verwirrtheit): sofort sagen, die Rettung 144 anzurufen,
  und mit anruf_zeigen den Knopf für 144 zeigen.
- Bei Unsicherheit zu Beschwerden: Gesundheitsnummer 1450 (rund um die Uhr, kostenlos).
- Wenn jemand sehr traurig ist oder an Suizid denkt: einfühlsam bleiben und die Telefonseelsorge 142 nennen (kostenlos, rund um die Uhr).

Täglicher Check-in und die Familie benachrichtigen:
- Auf Wunsch fragt Biko jeden Tag zu einer Uhrzeit, ob alles gut ist. Kommt bis zur Frist kein Lebenszeichen (irgendein
  Gespräch mit dir oder die App geöffnet), bekommt die Familie automatisch eine SMS. Meldet sie sich später, eine Entwarnung.
- Einstellen mit checkin_einstellen: Uhrzeit, wer die SMS bekommt (Name und Nummer aus dem Gedächtnis; kennst du die
  Nummer nicht, frag danach, erfinde nie eine) und nach wie vielen Stunden (Standard 2). Erklär ihr in ein, zwei Sätzen,
  wie es geht. Das ist freiwillig, dräng es niemandem auf; anbieten darfst du es, wenn sie allein lebt oder Angst hat.
- Notfall (gestürzt, kommt nicht auf, Brustschmerzen, Atemnot): zuerst 144 mit anruf_zeigen. Dann der Familie Bescheid:
  mit familie_benachrichtigen eine kurze, klare SMS (was ist, wo sie ist). Bittet sie selbst darum oder ist es eindeutig ein
  Notfall, in dem sie um Hilfe bittet, schick sie gleich und sag ihr, dass Peter (oder wer) Bescheid bekommt. Sonst frag kurz.
- Steht im Hinweis, dass der SMS-Dienst nicht eingerichtet ist, sag ehrlich, dass du der Familie noch keine SMS schicken
  kannst, und biete an, anzurufen (anruf_zeigen).

Medikamente:
- Soll Biko an ein Medikament erinnern ("jeden Tag um 8 die Herztablette", "每天早上八点提醒我吃降压药"), merkst du es mit
  erinnerung_merken und medikament: true. Dann fragt Biko zur Uhrzeit "Hast du sie genommen?" und nach 30 Minuten noch
  einmal, wenn keine Antwort kam.
- Biete bei Medikamenten einmal kurz an, der Familie Bescheid zu geben, wenn sie nicht bestätigt (familie: true, dazu die
  kontakte mit Name und Nummer aus dem Gedächtnis oder vom Check-in; kennst du keine Nummer, frag danach, erfinde nie eine).
  Standard: eine Stunde nach der Uhrzeit (melden_nach in Minuten). Dräng es niemandem auf.
- Sagt die Person, dass sie es genommen hat ("ja", "hab ich", "Tablette genommen", "吃过了"), und passt das zu einer
  Medikament-Erinnerung von heute im Hinweis, bestätigst du mit medikament_genommen (die Nummer der Erinnerung). Das
  schreibt es auch ins Gesundheitstagebuch, also nicht noch einmal mit gesundheit_notieren.
- Sagt sie, dass sie es heute nicht nimmt oder vergessen hat: nicht schimpfen. Ob man es nachholen darf, sagt die Packungsbeilage,
  der Arzt oder die Apotheke; du rätst nichts zur Dosis.
- Steht im Hinweis, dass ein Medikament heute noch nicht bestätigt ist und die Zeit vorbei ist, frag einmal im Gespräch
  freundlich nach.

Dolmetscher:
- Bittet die Person dich, für sie zu dolmetschen (beim Arzt, im Geschäft, mit dem Nachbarn), schaltest du mit dolmetscher
  ein (an: true, dazu die zwei Sprachen) und sagst in beiden Sprachen kurz, dass du jetzt übersetzt. Wie du dann
  übersetzt, steht im Hinweis der App.
- Sagt sie "fertig", "danke, das reicht" oder etwas Ähnliches zu dir, schaltest du mit dolmetscher (an: false) aus.

Geburtstage:
- Nennt die Person einen Geburtstag (von sich oder von jemandem), merkst du ihn mit geburtstag_merken (Name, Tag, Monat,
  das Jahr nur, wenn sie es weiß), nicht mit wissen_merken. Wer das ist ("Sohn Peter") gehört weiter ins Gedächtnis.
  Steht ein Geburtstag noch im Gedächtnis, trag ihn mit geburtstag_merken ein und streich ihn dort mit wissen_vergessen.
- Die Geburtstage stehen im Hinweis der App, der nächste zuerst. Ist einer heute, morgen oder in den nächsten Tagen, sag es
  im Gespräch einmal von selbst und biete an, einen Glückwunsch zu schreiben (nachricht_zeigen) oder anzurufen
  (anruf_zeigen). Ist er in etwa einer Woche, kannst du an ein Geschenk oder eine Karte erinnern.
- Falsches Datum? Einfach neu mit geburtstag_merken, das ersetzt den alten. Weg damit: geburtstag_streichen.

Gesundheitstagebuch:
- Sagt die Person einen Messwert (Blutdruck, Blutzucker, Puls, Gewicht) oder wie es ihr geht ("heute schwindlig", "Knie tut
  weh", "Tablette genommen"), schreibst du es mit gesundheit_notieren ins Tagebuch und bestätigst kurz mit dem Wert.
  Fehlt beim Blutdruck eine Zahl, frag nach. Die Einheit beim Zucker übernimmst du, wie sie sie sagt (mg/dl oder mmol/l).
- Du bewertest nicht und stellst keine Diagnose. Du darfst sagen, ob ein Wert im üblichen Bereich liegt oder deutlich darüber
  oder darunter, und dass sie das beim nächsten Arztbesuch zeigen kann.
- Sehr hoher Blutdruck (ab etwa 180/110) oder sehr niedriger Zucker (unter 70 mg/dl bzw. 3,9 mmol/l): ruhig bleiben und raten,
  gleich 1450 anzurufen; mit Brustschmerzen, Atemnot, Verwirrtheit oder Lähmung sofort 144 (Knopf mit anruf_zeigen).
- Was im Tagebuch steht, siehst du im Hinweis der App (die letzten zwei Wochen). Fragt sie danach ("wie war mein Blutdruck
  diese Woche?", "für den Arzt"), fasse es kurz zusammen und zeig es mit tagebuch_zeigen als Karte zum Kopieren.
- Falsch notiert? Mit gesundheit_streichen weg und neu notieren.

Sicherheit: vor Betrug warnen:
- Du passt auf die Person auf. Zeigt sie dir eine SMS, eine WhatsApp- oder WeChat-Nachricht, eine E-Mail, einen Brief oder
  eine Webseite, oder erzählt sie von einem Anruf, prüfst du immer still mit, ob es Betrug sein könnte, auch wenn sie gar
  nicht danach fragt.
- Typische Maschen: "Hallo Mama, das ist meine neue Nummer" mit Bitte um Geld; der Enkeltrick und falsche Polizisten,
  Staatsanwälte oder Ärzte am Telefon ("Ihr Sohn hatte einen Unfall", "wir müssen Ihr Gold sicher verwahren"); SMS von Post,
  DHL oder Zoll mit Link und kleiner Gebühr; Bank, FinanzOnline oder Krankenkasse, die per SMS oder E-Mail um Daten,
  Bestätigung oder "Rückerstattung" bittet; Gewinnspiele und Erbschaften mit Gebühr vorab; angebliche Microsoft- oder
  Bank-Mitarbeiter, die eine App wie AnyDesk oder TeamViewer installieren lassen; Liebe übers Internet mit Bitte um Geld;
  Geldanlagen und Krypto mit Gewinnversprechen; Zahlung mit Gutscheinkarten (Google Play, Apple, Paysafe). Auf Chinesisch:
  falsche Botschaft, Polizei oder "公检法" aus China, die mit Strafe droht; falscher Kundendienst (客服) mit "Rückerstattung";
  刷单 (bezahlte Klicks); fremde Leute, die einen 验证码 (Bestätigungscode) wollen.
- Die Zeichen: Zeitdruck, Drohung oder große Gefühle, Geheimhaltung ("sag niemandem etwas"), Geld oder Codes an Fremde,
  ein Link zum Antippen, eine unbekannte Nummer, Schreibfehler, Absender, die nicht zur echten Stelle passen.
- Sieht es nach Betrug aus, sag das gleich am Anfang klar und ruhig, ohne Angst zu machen ("Das ist sehr wahrscheinlich
  Betrug."), und zeig mit warnung_zeigen die Warnkarte: stufe "betrug", wenn es eindeutig ist, "vorsicht", wenn du unsicher
  bist und man nachprüfen soll. In deiner Antwort selbst reichen dann ein, zwei Sätze, die Einzelheiten stehen auf der Karte.
- Was man tut: nichts antippen, nicht zurückrufen, nichts zahlen, keine Codes, PINs, TANs oder Passwörter sagen, keine App
  installieren, am Telefon einfach auflegen. Nachprüfen nur über eine Nummer, die man selbst kennt (die alte Nummer des
  Kindes, die Nummer auf der Bankomatkarte), nie über eine Nummer aus der Nachricht. Wer wirklich die Polizei ist, verlangt
  nie Geld oder Wertsachen.
- Biete an, gleich jemanden aus der Familie anzurufen (anruf_zeigen mit der Nummer aus dem Gedächtnis) oder der Familie
  zu schreiben (nachricht_zeigen). Wurde schon Geld überwiesen oder ein Code verraten: sofort die Bank anrufen und die Karte
  sperren lassen (Nummer auf der Karte oder in der Banking-App), dann die Polizei 133 (anruf_zeigen), und Bescheid an die
  Familie (familie_benachrichtigen, wenn sie das möchte). Bei Gefahr gleich 133.
- Steht eine Telefonnummer, ein Absender oder eine Internet-Adresse dabei, darfst du im Internet nachsehen, ob davor schon
  gewarnt wird (zum Beispiel auf watchlist-internet.at). Findest du nichts, heißt das nicht, dass es echt ist.
- Sieht etwas echt aus (zum Beispiel ein normaler Brief der Wiener Netze), sag das ehrlich und mach keine Angst. Ist es nur
  ungewöhnlich, rate in einem Satz zum Nachprüfen, ohne Warnkarte.
- Biko-Grundsatz: lieber einmal zu viel nachfragen als einmal zu wenig. Schäm dich nie für die Person: Betrüger sind Profis,
  und es ist klug, zu fragen.

Von selbst melden:
- Du kannst dich jeden Morgen von selbst melden ("Morgenrunde"): mit Wetter, ein paar Nachrichten, die die Person
  interessieren, und ihren Erinnerungen für den Tag. Auf Android kommt dazu eine Mitteilung, und du liest vor.
- Will die Person das ("meld dich jeden Morgen", "erzähl mir in der Früh die Nachrichten", "每天早上告诉我新闻"),
  stellst du es mit morgenrunde_einstellen ein. Fehlt die Uhrzeit, frag kurz nach. "Hör auf damit" stellt es ab.
- Welche Nachrichten sie interessieren (Wien, China, Sport, Gesundheit ...), merkst du dir mit wissen_merken.
- Erinnerungen an einzelne Dinge bleiben Erinnerungen (erinnerung_merken), die Morgenrunde ist der tägliche Überblick.

Nachrichten für andere:
- Wenn die Person jemandem etwas schreiben will ("schreib Anna, dass ...", "wie sage ich dem Arzt ab?"), schreibst du die
  fertige Nachricht in ihrem Namen, in der Ich-Form, freundlich, natürlich und kurz (1 bis 4 Sätze), so wie sie selbst
  schreiben würde: an Enkel locker und herzlich, an Ärzte oder Ämter höflich mit "Sie". In der Sprache der Person, außer
  sie wünscht eine andere.
- Zeig die Nachricht mit dem Werkzeug nachricht_zeigen. Dann steht sie unter deiner Antwort mit einem Knopf zum Kopieren.
  Schreib den Text der Nachricht nicht noch einmal in deine Antwort, sag nur einen kurzen Satz dazu.
- Du kannst selbst nichts verschicken. Unter der Nachricht stehen Knöpfe: Kopieren (zum Einfügen in WeChat), und wenn die
  Person WhatsApp oder SMS sagt, ein Knopf, der WhatsApp oder SMS mit dem fertigen Text öffnet. Gib dann bei nachricht_zeigen
  "ueber" an und, wenn du sie kennst, die Telefonnummer; die Person muss dort nur noch auf Senden tippen.
- In der Blase am Tablet öffnet sich WhatsApp oder SMS gleich von selbst, eine WeChat-Nachricht liegt zum Einfügen bereit.
- Fehlt, was drinstehen soll, frag kurz nach. Soll etwas geändert werden, zeigst du die ganze neue Fassung.

Anrufen:
- Will die Person jemanden anrufen ("ruf meinen Sohn an", "给女儿打电话"), zeigst du mit anruf_zeigen einen großen Knopf zum
  Anrufen. In der Blase am Tablet geht das Telefon gleich mit der Nummer auf. Du rufst nie selbst an: die Person tippt auf
  den grünen Hörer.
- Die Nummer nimmst du aus dem, was du über die Person weißt. Kennst du sie nicht, frag danach und merk sie dir mit
  wissen_merken (Name, wer das ist, Nummer), z. B. "Sohn Peter, Telefon 0664 1234567". Erfinde nie eine Nummer.
- Bei WhatsApp-Anrufen oder Videoanrufen sag kurz, dass man das in WhatsApp selbst startet.

Listen und Notizen:
- Du führst für die Person Listen: die Einkaufsliste ("Einkaufen"), Notizen ("Notizen") und was sie sonst braucht
  ("Apotheke", "Geschenke"). Was draufsteht, siehst du im Hinweis der App.
- "Schreib Milch auf", "wir brauchen Brot und Eier": mit liste_aendern dazuschreiben. "Hab ich gekauft", "streich den Käse":
  wegnehmen. Eine kleine Notiz ("Der Schlüssel ist bei Frau Novak", "Parkplatz Ebene 3") kommt auf "Notizen".
- Bleibendes über die Person selbst (Gesundheit, Familie, Vorlieben) gehört nicht auf eine Liste, sondern in dein Gedächtnis.
- Fragt sie, was draufsteht, oder geht sie einkaufen, zeigst du die Liste mit liste_zeigen: dann steht sie als Karte unter
  deiner Antwort, und sie kann Gekauftes dort wegtippen. Sag dazu kurz, was draufsteht.
- Soll die Liste an jemanden gehen ("schick sie Peter"), schreib sie mit nachricht_zeigen als Nachricht.

Erinnerungen:
- Wenn die Person an etwas erinnert werden möchte ("erinnere mich", "vergiss nicht", "weck mich", "提醒我"), schreibst du es dir
  mit dem Werkzeug erinnerung_merken auf. Behaupte nie, du hättest dir etwas gemerkt, ohne das Werkzeug benutzt zu haben.
- Fehlt die Uhrzeit, frag kurz nach ("Um wie viel Uhr?") und rate nicht. "In 20 Minuten" rechnest du selbst aus.
- Einmalig (heute, morgen, am Freitag, in einer Stunde): mit Datum. Regelmäßig (jeden Tag, jeden Montag): mit Wochentagen.
  Ist unklar, ob einmal oder regelmäßig, frag kurz nach.
- Bestätige danach in einem kurzen Satz mit Tag und Uhrzeit. Die Nummer einer Erinnerung sagst du nie dazu.
- In der Android-App meldest du dich zur Uhrzeit auch, wenn sie zu ist. Im Browser (z. B. am iPhone) nur, solange die Seite
  offen ist: Dort sagst du bei Wichtigem wie Medikamenten in einem Satz dazu, zusätzlich den Wecker des Handys zu stellen.
- Will die Person etwas nicht mehr, löschst du es mit erinnerung_loeschen. Zum Ändern: löschen und neu merken.
- Auf "Woran erinnerst du mich?" liest du deine Erinnerungen aus dem Hinweis der App in einfachen Worten vor.

Dein Gedächtnis über die Person:
- Erzählt die Person etwas, das auch nächste Woche noch stimmt, schreibst du es dir mit dem Werkzeug wissen_merken auf:
  Gesundheit und Diät (Krankheiten, Allergien, was sie nicht essen darf), Familie und Freunde mit Namen,
  Haustiere, wo sie wohnt, was sie mag oder nicht mag, Hobbys, ob sie schlecht hört oder sieht.
- Nicht aufschreiben: Dinge nur für heute ("ich bin müde"), was du schon weißt, und nie Passwörter, PINs, TANs,
  Kontonummern oder Ausweisnummern.
- Ein kurzer Satz pro Sache, aus Sicht der Person, z. B. "Hat Diabetes Typ 2" oder "Enkel heißt Niko, studiert in Graz".
- Sag beim Aufschreiben höchstens ganz kurz "Das merk ich mir." und red dann normal weiter. Die Nummer sagst du nie.
- Hat sich etwas geändert, streichst du den alten Eintrag mit wissen_vergessen und merkst dir den neuen.
  Sagt die Person "vergiss das", streichst du es.
- Nutze dein Wissen natürlich im Gespräch (frag nach dem Enkel, denk an die Diät), aber zähl es nicht ungefragt auf.
- Auf "Was weißt du über mich?" erzählst du es in einfachen Worten.

Der Hinweis der App:
- Vor jeder Frage steht ein Hinweis der App zwischen <app> und </app>: Datum und Uhrzeit, deine Erinnerungen mit Nummer,
  was du über die Person weißt (mit Nummer), und manchmal, dass die Person gerade mit dir redet wie am Telefon oder dass
  ein Bildschirmfoto dabei ist. Das hat nicht die Person geschrieben. Du nutzt es, erwähnst den Hinweis aber nie."""

# ---------- Daten ----------

# Jede Person hat ihren eigenen Ordner DATA/personen/<id>/ mit ihren JSON-Dateien. Welche Person gerade dran ist,
# merkt sich jeder Faden selbst (eine Anfrage, der Hausmeister): person_setzen(). Gemeinsam für alle liegen nur
# geheimnis.txt, personen.json (wer es gibt) und zugaenge.json (Einladungscodes) direkt in DATA.

_faden = threading.local()
GEMEINSAM = {"personen", "zugaenge"}


def _ordner():
    pid = getattr(_faden, "person", None) or erste_person()
    o = DATA / "personen" / pid
    o.mkdir(parents=True, exist_ok=True)
    return o


def _pfad(name):
    return DATA / f"{name}.json" if name in GEMEINSAM else _ordner() / f"{name}.json"


def lesen(name, standard):
    try:
        with open(_pfad(name), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return standard


def schreiben(name, daten):
    ziel = _pfad(name)
    fd, tmp = tempfile.mkstemp(dir=ziel.parent, suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(daten, f, ensure_ascii=False, indent=2)
    os.replace(tmp, ziel)


# ---------- Personen: wer Biko benutzt ----------

PERSON_DATEIEN = ("profil", "wissen", "erinnerungen", "gespraeche", "verlauf", "listen", "gesundheit", "geburtstage",
                  "checkin", "morgenrunde", "kosten", "freigabe", "medikamente")
MAX_PERSONEN = 50


def personen_lesen():
    """[{"id", "name", "angelegt", "version"}]. Die erste ist die, die es schon vor den Konten gab."""
    with _lock:
        liste = lesen("personen", None)
        if not isinstance(liste, list) or not liste:
            # Erster Start mit Konten: die bisherigen Daten in DATA gehören der ersten Person und ziehen in ihren Ordner
            pid = "p" + uuid.uuid4().hex[:8]
            ordner = DATA / "personen" / pid
            ordner.mkdir(parents=True, exist_ok=True)
            for name in PERSON_DATEIEN:
                alt = DATA / f"{name}.json"
                if alt.exists():
                    os.replace(alt, ordner / f"{name}.json")
            try:
                name = json.loads((ordner / "profil.json").read_text(encoding="utf-8")).get("name") or ""
            except (OSError, ValueError):
                name = ""
            liste = [{"id": pid, "name": name or "Erste Person", "angelegt": jetzt().isoformat(timespec="seconds"),
                      "version": 1}]
            schreiben("personen", liste)
        return liste


def erste_person():
    return personen_lesen()[0]["id"]


def person_finden(pid):
    return next((p for p in personen_lesen() if p["id"] == pid), None)


def person_setzen(pid):
    """Ab jetzt liest und schreibt dieser Faden die Daten dieser Person."""
    _faden.person = pid


def person_jetzt():
    return getattr(_faden, "person", None) or erste_person()


def person_anlegen(name, sprache="de-AT", anrede="du"):
    name = " ".join(str(name or "").split())[:40]
    if not name:
        raise ValueError("Bitte einen Namen angeben.")
    with _lock:
        liste = personen_lesen()
        if len(liste) >= MAX_PERSONEN:
            raise ValueError("Es gibt schon zu viele Personen.")
        p = {"id": "p" + uuid.uuid4().hex[:8], "name": name, "angelegt": jetzt().isoformat(timespec="seconds"),
             "version": 1}
        schreiben("personen", liste + [p])
        vorher = getattr(_faden, "person", None)
        person_setzen(p["id"])
        try:
            schreiben("profil", {"name": name, "anrede": "Sie" if anrede == "Sie" else "du",
                                 "sprache": sprache if sprache in SPRACHEN else "de-AT"})
            schreiben("wissen", [])
        finally:
            person_setzen(vorher)
    return p


def person_abmelden(pid):
    """Alle Geräte dieser Person und ihrer Familie sind abgemeldet, alte Codes gelten nicht mehr."""
    with _lock:
        liste = personen_lesen()
        for p in liste:
            if p["id"] == pid:
                p["version"] = p.get("version", 1) + 1
        schreiben("personen", liste)
        schreiben("zugaenge", {k: z for k, z in zugaenge_lesen().items() if z["person"] != pid})


# ---------- Einladungscodes: so kommen die Person und ihre Familie hinein, ohne Passwort ----------

CODE_ZEICHEN = "ACDEFHJKMNPRTUVWXY345679"   # nichts, was man verwechselt (0/O, 1/I/L, 2/Z, 8/B)
CODE_TAGE = 14
ROLLEN = ("person", "familie")


def code_sauber(code):
    return re.sub(r"[^A-Z0-9]", "", str(code or "").upper())


def code_hash(code):
    return hashlib.sha256(code_sauber(code).encode()).hexdigest()


def zugaenge_lesen():
    """{hash des Codes: {"person", "rolle", "bis"}}. Gespeichert wird nur der Hash, nie der Code selbst."""
    d = lesen("zugaenge", {})
    jetzt_s = time.time()
    return {k: z for k, z in d.items() if isinstance(z, dict) and z.get("bis", 0) > jetzt_s} if isinstance(d, dict) else {}


def code_erzeugen(pid, rolle):
    """Ein neuer Code für die Person selbst oder ihre Familie, 14 Tage gültig, auf mehreren Geräten verwendbar.
    Ein neuer Code ersetzt den alten derselben Art (bereits angemeldete Geräte bleiben angemeldet)."""
    if rolle not in ROLLEN or not person_finden(pid):
        raise ValueError("Gibt es nicht.")
    roh = "".join(secrets.choice(CODE_ZEICHEN) for _ in range(8))
    with _lock:
        d = {k: z for k, z in zugaenge_lesen().items() if not (z["person"] == pid and z["rolle"] == rolle)}
        d[code_hash(roh)] = {"person": pid, "rolle": rolle, "bis": time.time() + CODE_TAGE * 86400}
        schreiben("zugaenge", d)
    return {"code": f"{roh[:4]}-{roh[4:]}", "tage": CODE_TAGE}


def code_pruefen(code):
    """(Person, Rolle) zu einem gültigen Code, sonst None."""
    if len(code_sauber(code)) != 8:
        return None
    z = zugaenge_lesen().get(code_hash(code))
    if not z or not person_finden(z["person"]):
        return None
    return z["person"], z["rolle"]


def geheimnis():
    """Schlüssel zum Signieren des Login-Cookies, wird einmal erzeugt."""
    p = DATA / "geheimnis.txt"
    if not p.exists():
        p.write_text(secrets.token_hex(32))
        p.chmod(0o600)
    return p.read_text().strip()


SPRACHEN = {"de-AT": "Deutsch", "zh-CN": "Chinesisch (vereinfachte Schriftzeichen)"}


def profil():
    p = lesen("profil", {})
    return {k: p.get(k, v) for k, v in STANDARD_PROFIL.items()}


def wissen_lesen():
    """Was Biko über die Person weiß. Beim ersten Mal kommen die alten Felder Diät und Notizen aus dem Profil hinein."""
    if not _pfad("wissen").exists():
        with _lock:
            if not _pfad("wissen").exists():
                alt = lesen("profil", {})
                zeit = jetzt().isoformat(timespec="seconds")
                liste = [{"id": uuid.uuid4().hex[:10], "text": f"{vorne}{str(alt[k]).strip()}"[:400], "zeit": zeit}
                         for k, vorne in (("diaet", "Diät: "), ("notizen", "")) if str(alt.get(k) or "").strip()]
                schreiben("wissen", liste)
                if "diaet" in alt or "notizen" in alt:
                    schreiben("profil", {k: v for k, v in alt.items() if k not in ("diaet", "notizen")})
    return lesen("wissen", [])


# ---------- Claude ----------

def client():
    global _client
    if _client is None:
        _client = anthropic.Anthropic()  # liest ANTHROPIC_API_KEY
    return _client


# Websuche für Deals, Öffnungszeiten, aktuelle Fragen. Läuft bei Anthropic. Mit web_fetch kann Biko eine
# Trefferseite auch öffnen, zum Beispiel wenn der Preis nicht in der Vorschau steht.
WEBSUCHE = [
    {"type": "web_search_20260209", "name": "web_search", "max_uses": 5,
     "user_location": {"type": "approximate", "city": "Wien", "country": "AT", "timezone": "Europe/Vienna"}},
    {"type": "web_fetch_20260209", "name": "web_fetch", "max_uses": 3},
]
_seiten_oeffnen = True   # wird False, falls die API das Öffnen von Seiten ablehnt: dann sucht Biko nur


def protokoll(text):
    """Eine Zeile ins Server-Protokoll. Nie Inhalte aus Gesprächen, nur was technisch passiert ist."""
    print(text, flush=True)


def claude_anfrage(**kw):
    """Der eine Aufruf der Claude-API. Die Tests ersetzen ihn durch ein Drehbuch."""
    return client().beta.messages.create(**kw)


def claude_strom(beim_text, **kw):
    """Wie claude_anfrage, aber jedes neue Stück Text geht sofort an `beim_text`. Damit kann Biko schon sprechen,
    während er noch schreibt. Liefert am Ende die ganze Antwort, genau wie claude_anfrage."""
    with client().beta.messages.stream(**kw) as strom:
        for ereignis in strom:
            if ereignis.type == "content_block_delta" and getattr(ereignis.delta, "type", "") == "text_delta":
                beim_text(ereignis.delta.text)
        return strom.get_final_message()


def werkzeug_ergebnis(block, werkzeuge):
    """Führt ein von Claude gewünschtes Werkzeug aus. Fehler gehen als Text zurück, damit Claude nachfragen kann."""
    try:
        if block.name not in werkzeuge:
            raise ValueError("Dieses Werkzeug gibt es nicht.")
        inhalt = werkzeuge[block.name]["tun"](block.input if isinstance(block.input, dict) else {})
        return {"type": "tool_result", "tool_use_id": block.id, "content": inhalt}
    except ValueError as e:
        return {"type": "tool_result", "tool_use_id": block.id, "content": f"Fehler: {e}", "is_error": True}


# Preise in US-Dollar pro Million Tokens (Stand November 2026, laut Anthropic): Eingabe, Ausgabe, aus dem
# Zwischenspeicher gelesen, in den Zwischenspeicher geschrieben (5 Minuten). Eine Websuche kostet 1 Cent.
PREISE = {
    "claude-opus-5-5": (4.00, 20.00, 0.20, 5.00),
    "claude-sonnet-5-5": (2.00, 10.00, 0.10, 2.50),
    "claude-haiku-5-5": (0.10, 0.50, 0.01, 0.125),
}
PREIS_SUCHE = 0.01


def verbrauch_zaehlen(summe, r, modell):
    """Zählt, was eine Anfrage verbraucht hat, und rechnet es in Dollar um (nur Zahlen, nie Inhalte)."""
    u = getattr(r, "usage", None)
    if u is None:
        return
    zahl = lambda x: x if isinstance(x, int) else 0
    neu = {"eingabe": zahl(getattr(u, "input_tokens", 0)), "ausgabe": zahl(getattr(u, "output_tokens", 0)),
           "gelesen": zahl(getattr(u, "cache_read_input_tokens", 0)),
           "geschrieben": zahl(getattr(u, "cache_creation_input_tokens", 0)),
           "suchen": zahl(getattr(getattr(u, "server_tool_use", None), "web_search_requests", 0))}
    preis = PREISE.get(getattr(r, "model", None) if isinstance(getattr(r, "model", None), str) else modell) or PREISE.get(modell)
    if preis:
        neu["dollar"] = (neu["eingabe"] * preis[0] + neu["ausgabe"] * preis[1] + neu["gelesen"] * preis[2]
                         + neu["geschrieben"] * preis[3]) / 1e6 + neu["suchen"] * PREIS_SUCHE
    for k, v in neu.items():
        summe[k] = summe.get(k, 0) + v


def verbrauch_text(v):
    alle = v.get("eingabe", 0) + v.get("gelesen", 0) + v.get("geschrieben", 0)
    text = (f"Eingabe {alle} Tokens (davon {v.get('gelesen', 0)} aus dem Zwischenspeicher, {v.get('geschrieben', 0)} neu"
            f" gespeichert), Ausgabe {v.get('ausgabe', 0)}, Suchen {v.get('suchen', 0)}")
    if "dollar" in v:
        heute = kosten_dazu(ki=v["dollar"])
        text += (f", Kosten {v['dollar'] * 100:.2f} US-Cent, heute bisher {heute['ki'] * 100:.1f} US-Cent"
                 f" bei {heute['antworten']} Antworten")
    return text


def kosten_dazu(ki=0.0, zeichen=0):
    """Tagessumme in kosten.json: KI-Kosten in Dollar, Zahl der Antworten, vorgelesene Zeichen. Die letzten 62 Tage."""
    tag = jetzt().strftime("%Y-%m-%d")
    with _lock:
        alle = lesen("kosten", {})
        heute = {"ki": 0.0, "antworten": 0, "zeichen": 0, **alle.get(tag, {})}
        heute["ki"] = round(heute["ki"] + ki, 6)
        heute["antworten"] += 1 if ki else 0
        heute["zeichen"] += zeichen
        alle[tag] = heute
        schreiben("kosten", {k: alle[k] for k in sorted(alle)[-62:]})
    return heute


def frage_claude(system, messages, max_tokens=4000, websuche=False, werkzeuge=None, beim_text=None, modell=None):
    """Eine Antwort von Claude als Text. Wirft RuntimeError mit freundlicher Meldung.
    `werkzeuge`: {name: {"schema": ..., "tun": funktion(eingabe) -> text}}, Claude darf sie selbst aufrufen.
    `beim_text`: bekommt jedes Stück Text, sobald es da ist (für das Gespräch wie am Telefon)."""
    global _seiten_oeffnen
    werkzeuge = werkzeuge or {}
    web = [w for w in WEBSUCHE if _seiten_oeffnen or w["name"] != "web_fetch"] if websuche else []
    tools = web + [w["schema"] for w in werkzeuge.values()]
    messages = list(messages)
    benutzt = []
    verbrauch = {}
    # Zwischen zwei Runden (etwa "Ich schau kurz nach." und danach die Suche) beginnt ein neuer Satz
    runde_offen = {"gesagt": False, "trennen": False}

    def weiterreichen(stueck):
        if not stueck:
            return
        if runde_offen["trennen"]:
            stueck, runde_offen["trennen"] = "\n" + stueck, False
        runde_offen["gesagt"] = True
        beim_text(stueck)

    def anfrage(tools):
        kw = dict(
            model=modell or MODELL,
            max_tokens=max_tokens,
            # Die Anleitung bleibt gleich und kommt aus dem Zwischenspeicher. Das obere cache_control nimmt dazu bei
            # jeder Runde alles bis zum Schluss mit: Suchergebnisse und Werkzeug-Runden zahlt Biko so nur einmal voll.
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            cache_control={"type": "ephemeral"},
            messages=messages,
            # Alltagsgespräch: wenig Nachdenken reicht, ist schneller und günstiger
            output_config={"effort": "low"},
            # Falls eine Sicherheitsprüfung die Anfrage ablehnt, springt ein anderes Modell ein
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            **({"tools": tools} if tools else {}),
        )
        return claude_strom(weiterreichen, **kw) if beim_text else claude_anfrage(**kw)

    try:
        for runde in range(1, 9):  # Werkzeug-Aufrufe und lange Websuchen (pause_turn) werden fortgesetzt
            try:
                r = anfrage(tools)
            except anthropic.BadRequestError:
                # Lehnt die API die Anfrage ab, solange "Seiten öffnen" dabei ist, versucht Biko es einmal nur mit
                # der Suche: lieber eine Antwort ohne geöffnete Seite als gar keine.
                ohne = [w for w in tools if w.get("name") != "web_fetch"]
                if runde > 1 or len(ohne) == len(tools):
                    raise
                r = anfrage(ohne)
                tools, _seiten_oeffnen = ohne, False
                protokoll("Seiten öffnen (web_fetch) wurde abgelehnt, Biko sucht ab jetzt ohne.")
            benutzt += [b.name for b in r.content if b.type in ("tool_use", "server_tool_use")]
            verbrauch_zaehlen(verbrauch, r, modell or MODELL)
            runde_offen["trennen"] = runde_offen["gesagt"]
            if r.stop_reason == "pause_turn":
                messages = messages + [{"role": "assistant", "content": r.content}]
            elif r.stop_reason == "tool_use":
                ergebnisse = [werkzeug_ergebnis(b, werkzeuge) for b in r.content if b.type == "tool_use"]
                messages = messages + [{"role": "assistant", "content": r.content}, {"role": "user", "content": ergebnisse}]
            else:
                break
    except anthropic.AuthenticationError:
        raise RuntimeError("Der Schlüssel für die KI fehlt oder stimmt nicht. Bitte Niko Bescheid geben.")
    except anthropic.RateLimitError:
        raise RuntimeError("Gerade sind zu viele Anfragen. Bitte in einer Minute nochmal probieren.")
    except anthropic.APIStatusError as e:
        protokoll(f"Claude-Fehler: {e.status_code} {e.message}")
        raise RuntimeError("Biko kann gerade nicht antworten. Bitte gleich nochmal probieren.")
    except anthropic.APIConnectionError:
        raise RuntimeError("Keine Verbindung zur KI. Ist das Internet am Server da?")
    protokoll(f"Claude ({modell or MODELL}): {runde} Anfragen, Ende {r.stop_reason}, Werkzeuge: {', '.join(benutzt) or 'keine'}"
              f" | {verbrauch_text(verbrauch)}")
    if r.stop_reason == "refusal":
        return "Dabei kann ich leider nicht helfen. Magst du mich etwas anderes fragen?"
    text = "".join(b.text for b in r.content if b.type == "text").strip()
    return text or "Entschuldige, da ist mir nichts eingefallen. Magst du es anders sagen?"


def jetzt():
    return datetime.now(ZEITZONE)


# ---------- Sprachdienst ----------

# Offene Verbindungen zum Sprachdienst. Jeder Satz braucht eine Anfrage; eine neue Verbindung kostet jedes Mal den
# Verbindungsaufbau (ein paar hundert Millisekunden), eine offene ist sofort da.
SPRACH_HOST = "api.elevenlabs.io"
MAX_VERBINDUNGEN = 4
_verbindungen = []


def _sprach_verbindung():
    """(Verbindung, ob sie schon offen war)."""
    with _lock:
        if _verbindungen:
            return _verbindungen.pop(), True
    return http.client.HTTPSConnection(SPRACH_HOST, timeout=40), False


def _verbindung_zurueck(v, r):
    if r.will_close:
        v.close()
        return
    with _lock:
        if len(_verbindungen) < MAX_VERBINDUNGEN:
            _verbindungen.append(v)
            return
    v.close()


def _sprach_senden(pfad, daten, kopf):
    """Schickt die Anfrage über eine offene Verbindung (sonst eine neue) und liefert (Verbindung, Antwort).
    Fehler des Dienstes kommen wie bei urllib als HTTPError, eine fehlende Verbindung als OSError."""
    kopf = {"xi-api-key": SPRACH_KEY, **(kopf or {})}
    for versuch in (1, 2):
        v, offen = _sprach_verbindung()
        try:
            v.request("GET" if daten is None else "POST", pfad, body=daten, headers=kopf)
            r = v.getresponse()
        except (OSError, http.client.HTTPException) as e:
            v.close()
            if offen and versuch == 1:
                continue   # die offene Verbindung hat der Dienst inzwischen zugemacht: einmal mit einer neuen
            raise OSError(str(e)) from e
        if r.status >= 400:
            inhalt = r.read()
            _verbindung_zurueck(v, r)
            raise urllib.error.HTTPError("https://" + SPRACH_HOST + pfad, r.status, r.reason, r.headers, io.BytesIO(inhalt))
        return v, r


def sprach_anfrage(pfad, daten=None, kopf=None):
    """Der eine Aufruf des Sprachdienstes. Die Tests ersetzen ihn. Liefert die Antwort als Bytes."""
    v, r = _sprach_senden(pfad, daten, kopf)
    try:
        inhalt = r.read()
    except (OSError, http.client.HTTPException) as e:
        v.close()
        raise OSError(str(e)) from e
    _verbindung_zurueck(v, r)
    return inhalt


def sprach_strom(pfad, daten, kopf=None):
    """Wie sprach_anfrage, liefert die Antwort aber in Stücken, sobald sie ankommen. Die Tests ersetzen ihn."""
    v, r = _sprach_senden(pfad, daten, kopf)

    def stuecke():
        fertig = False
        try:
            while True:
                stueck = r.read1(8192)
                if not stueck:
                    fertig = True
                    return
                yield stueck
        finally:
            # ganz gelesen: die Verbindung kann wieder verwendet werden. Abgebrochen: zumachen.
            if fertig:
                _verbindung_zurueck(v, r)
            else:
                v.close()
    return stuecke()


def sprachdienst(pfad, daten=None, kopf=None, strom=False):
    """Fragt den Sprachdienst. Wirft RuntimeError mit freundlicher Meldung.
    `strom`: die Antwort kommt als Folge von Stücken (Fehler beim Verbinden kommen trotzdem gleich hier an)."""
    if not SPRACH_KEY:
        raise RuntimeError("Der Sprachdienst ist nicht eingerichtet.")
    try:
        return sprach_strom(pfad, daten, kopf) if strom else sprach_anfrage(pfad, daten, kopf)
    except urllib.error.HTTPError as e:
        try:
            grund = e.read()[:300].decode("utf-8", "replace")   # die Fehlermeldung des Dienstes, kein Inhalt aus Gesprächen
        except Exception:
            grund = ""
        protokoll(f"Sprachdienst-Fehler: {e.code} bei {pfad.split('?')[0]} {grund}")
        if e.code in (401, 403):
            raise RuntimeError("Der Schlüssel für die Stimme fehlt, stimmt nicht oder das Guthaben ist aufgebraucht. Bitte Niko Bescheid geben.")
        raise RuntimeError("Die Stimme geht gerade nicht. Bitte gleich nochmal probieren.")
    except OSError:
        protokoll(f"Sprachdienst-Fehler: keine Verbindung bei {pfad.split('?')[0]}")
        raise RuntimeError("Der Sprachdienst ist gerade nicht erreichbar.")


_stimme = None


def stimme():
    """Mit welcher Stimme Biko spricht: die festgelegte (SPRACH_STIMME), sonst die erste Stimme des Kontos."""
    global _stimme
    if SPRACH_STIMME:
        return SPRACH_STIMME
    if _stimme is None:
        liste = json.loads(sprachdienst("/v2/voices?page_size=20")).get("voices") or []
        if not liste:
            raise RuntimeError("Die Stimme geht gerade nicht. Bitte gleich nochmal probieren.")
        _stimme = str(liste[0]["voice_id"])
        protokoll(f"Sprachdienst: Biko spricht mit der Stimme {liste[0].get('name')!r}")
    return _stimme


def ton_holen(text):
    """Der Text als gesprochener Ton (MP3)."""
    text = text[:MAX_VORLESEN]
    ton = sprachdienst(f"/v1/text-to-speech/{quote(stimme(), safe='')}?output_format=mp3_44100_128",
                       json.dumps({"text": text, "model_id": SPRACH_MODELL}).encode(), {"Content-Type": "application/json"})
    heute = kosten_dazu(zeichen=len(text))
    protokoll(f"Sprachdienst: {len(text)} Zeichen vorgelesen, heute bisher {heute['zeichen']} Zeichen")
    return ton


def ton_strom(text, vorher=""):
    """Ein Stück einer Antwort als Ton, roh als PCM (16 Bit, 24 kHz, mono), Stück für Stück, sobald es entsteht.
    `vorher`: was Biko davor gesagt hat, damit die Stimme im Satzfluss bleibt."""
    text = text[:MAX_SATZ]
    # Kurze Sätze am Anfang einer Antwort ("Moment, ich schau kurz nach.", "Gerne!") kommen oft wieder. Die hat
    # Biko schon einmal gesagt: dann kommt der Ton sofort aus dem Speicher, klingt gleich und kostet nichts.
    schluessel = (stimme(), SPRACH_MODELL, text) if not vorher and len(text) <= MAX_GEMERKT_SATZ else None
    if schluessel:
        with _lock:
            gemerkt = _toene.get(schluessel)
            if gemerkt is not None:
                _toene.move_to_end(schluessel)
        if gemerkt is not None:
            protokoll(f"Sprachdienst: {len(text)} Zeichen aus dem Speicher gesprochen")
            return iter(gemerkt)
    body = {"text": text, "model_id": SPRACH_MODELL}
    if vorher:
        body["previous_text"] = vorher[-500:]
    start = time.monotonic()
    stuecke = mit_erstem_ton(sprachdienst(f"/v1/text-to-speech/{quote(stimme(), safe='')}/stream?output_format=pcm_24000",
                                          json.dumps(body).encode(), {"Content-Type": "application/json"}, strom=True),
                             start, len(text))
    heute = kosten_dazu(zeichen=len(text))
    protokoll(f"Sprachdienst: {len(text)} Zeichen gesprochen, heute bisher {heute['zeichen']} Zeichen")
    return ton_merken(schluessel, stuecke) if schluessel else stuecke


def mit_erstem_ton(stuecke, start, zeichen):
    """Schreibt ins Protokoll, wie lange es bis zum ersten Ton gedauert hat."""
    erstes = True
    for stueck in stuecke:
        if erstes:
            erstes = False
            protokoll(f"Sprachdienst: {zeichen} Zeichen, erster Ton nach {(time.monotonic() - start) * 1000:.0f} ms")
        yield stueck


MAX_GEMERKT_SATZ = 80     # so kurze Sätze merkt sich Biko als fertigen Ton
MAX_TOENE = 100           # so viele Sätze, der älteste fällt weg (zusammen höchstens etwa 25 MB)
_toene = OrderedDict()


def ton_merken(schluessel, stuecke):
    """Reicht den Ton weiter und merkt ihn sich, aber nur, wenn er ganz angekommen ist (nicht nach Unterbrechen)."""
    alle = []
    for stueck in stuecke:
        alle.append(stueck)
        yield stueck
    with _lock:
        _toene[schluessel] = alle
        while len(_toene) > MAX_TOENE:
            _toene.popitem(last=False)


def live_zugang():
    """Ein Zugang für 15 Minuten, mit dem die App selbst live beim Sprachdienst zuhören lassen kann.
    Der eigentliche Schlüssel verlässt den Server nie."""
    j = json.loads(sprachdienst("/v1/single-use-token/realtime_scribe", b""))
    zugang = str(j.get("token") or "")
    if not zugang:
        raise RuntimeError("Die Stimme geht gerade nicht. Bitte gleich nochmal probieren.")
    protokoll("Sprachdienst: Live-Zuhören begonnen")
    return {"token": zugang, "modell": SPRACH_LIVE}


AUFNAHME_ARTEN = {"audio/webm": "webm", "audio/mp4": "mp4", "audio/ogg": "ogg", "audio/wav": "wav",
                  "audio/mpeg": "mp3", "audio/aac": "aac", "audio/x-m4a": "m4a"}


def text_hoeren(ton, art):
    """Die Aufnahme als Text. Die Sprache wird nicht vorgegeben: der Dienst erkennt selbst, ob Deutsch oder
    Chinesisch gesprochen wurde."""
    grenze = "biko" + secrets.token_hex(16)
    felder = {"model_id": SPRACH_HOEREN, "tag_audio_events": "false", "timestamps_granularity": "none"}
    teile = [f'--{grenze}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode() for k, v in felder.items()]
    teile.append(f'--{grenze}\r\nContent-Disposition: form-data; name="file"; filename="aufnahme.{AUFNAHME_ARTEN[art]}"\r\n'
                 f'Content-Type: {art}\r\n\r\n'.encode() + ton + b"\r\n")
    teile.append(f"--{grenze}--\r\n".encode())
    j = json.loads(sprachdienst("/v1/speech-to-text", b"".join(teile),
                                {"Content-Type": f"multipart/form-data; boundary={grenze}"}))
    sprache = str(j.get("language_code") or "")
    protokoll(f"Sprachdienst: {len(ton) // 1000} kB zugehört, Sprache {sprache or 'unbekannt'}")
    return {"text": str(j.get("text") or "").strip(), "sprache": sprache}


BILDSCHIRM = """Zu dieser Frage siehst du ein Bildschirmfoto vom Handy oder Tablet der Person: das, was sie gerade vor sich hat
(zum Beispiel einen WeChat-Chat, eine Webseite oder einen Brief). Fragt sie "was steht da", "was schreibt sie",
"übersetz das" oder "was soll ich antworten", geht es um dieses Bild. Lies vor, erkläre oder übersetze in einfachen Worten.
Eine Antwort für jemanden schreibst du wie sonst auch mit nachricht_zeigen. Sag nicht "auf dem Bildschirmfoto",
sondern einfach "da steht" oder "Mei schreibt". Sieht das Bild nach Betrug aus (eine SMS mit Link, eine fremde Nummer, die
Geld will, eine falsche Bank-Seite), warn sie davor, auch wenn sie nach etwas anderem fragt, mit der Warnkarte
(warnung_zeigen). Hat die Frage sonst nichts mit dem Bild zu tun, beachte es nicht."""

FOTO = """Zu dieser Frage hat die Person mit der Kamera ein Foto gemacht, meistens von einem Brief, einer Rechnung, einem Formular,
einer Packungsbeilage oder einem Schild. Erkläre es in einfachen Worten:
- Von wem ist es und worum geht es, in ein, zwei Sätzen.
- Muss sie etwas tun? Was genau, und bis wann? Geld, Fristen und Termine nennst du deutlich. Ist nichts zu tun, sag das.
- Wirkt es wie Betrug (Druck, Drohung, Zahlung an Fremde, Gewinn, komische Absender, ein Code zum Scannen), warne klar,
  zeig die Warnkarte (warnung_zeigen) und rate, bei der Familie oder direkt bei der echten Stelle nachzufragen, nicht über
  Nummern aus dem Brief.
- Bei Medikamenten gilt wie immer: keine Dosierung ändern, im Zweifel Apotheke oder Arzt.
Schreibt sie auf Chinesisch oder ist der Brief schwer, erkläre in ihrer Sprache. Ist das Foto unscharf, abgeschnitten oder
zu dunkel, sag das freundlich und bitte um ein neues, statt zu raten. Termine kannst du ihr mit erinnerung_merken anbieten.
Sag nicht "auf dem Foto", sondern "der Brief ist von ..." oder "da steht ..."."""


# Worum es geht, wenn Biko gründlich sein soll: dann nimmt er das stärkere Modell
WICHTIG = re.compile(
    r"brief|rechnung|mahnung|behörde|amt\b|finanzamt|magistrat|vertrag|kündig|betrug|betrüg|fake|phishing|abzocke|echt\?"
    r"|bank|konto|überweis|zahlen|bezahl|pin\b|passwort|tan\b|versicherung|pension|rente|steuer|frist|anwalt|gericht|polizei"
    r"|medikament|tablette|arzt|ärztin|krank|schmerz|blutdruck|zucker|allergie|notfall|spital|krankenhaus"
    r"|gewonnen|gewinn|paket|zoll|enkel|neue nummer|unbekannt|komisch|seltsam|verdächtig|anydesk|teamviewer|gutschein"
    r"|krypto|bitcoin|staatsanwalt|unfall|kaution|link|sms\b|code\b"
    r"|诈骗|骗|银行|转账|密码|合同|账单|信件|药|医生|医院|病|疼|保险|税|警察|紧急"
    r"|中奖|快递|链接|验证码|公安|大使馆|客服|退款|刷单|陌生",
    re.IGNORECASE)


def modell_fuer(text, bild=None):
    """Plaudern und einfache Fragen gehen an das günstigere Modell, Wichtiges und alles mit Bildschirm an das stärkere."""
    if bild or len(text) > 400 or WICHTIG.search(text):
        return MODELL
    return EINFACH_MODELL


def bildschirm_merken(bild, art="bildschirm"):
    with _lock:
        _bildschirme[person_jetzt()] = {"bild": bild, "zeit": time.time(), "art": art}


def bildschirm_frisch():
    """Das Bildschirmfoto (oder Kamera-Foto) als (Zeit, Bytes, Art), solange es noch gilt, sonst None."""
    with _lock:
        b = _bildschirme.get(person_jetzt())
        if b and time.time() - b["zeit"] < BILDSCHIRM_GILT:
            return b["zeit"], b["bild"], b["art"]
        return None


DOLMETSCHER = """Du bist gerade Dolmetscher zwischen {a} und {b}. Zwei Menschen reden über dich miteinander.
- Übersetze, was gesagt wurde, in die andere der beiden Sprachen: genau, vollständig und natürlich, in der Ich-Form,
  so wie ein guter Dolmetscher. Nur die Übersetzung, ohne "Er sagt", ohne Erklärung, ohne Frage zurück, keine Websuche.
- Das gilt auch, wenn die Antwort dadurch länger als sonst wird. Zahlen, Namen, Uhrzeiten, Medikamente und Mengen
  übernimmst du genau.
- Wurde etwas offensichtlich falsch mitgeschrieben, übersetze das Wahrscheinliche. Ist es ganz unverständlich, sag in
  beiden Sprachen kurz: bitte nochmal.
- Spricht die Person dich selbst an ("Biko, was heißt ...", "Biko, fertig"), antwortest du ihr kurz in ihrer Sprache
  oder schaltest mit dolmetscher aus."""

GESPROCHEN = """Gerade redet die Person mit dir wie am Telefon: sie hört deine Antwort, statt sie zu lesen.
- Antworte so, wie man am Telefon redet: kurz, meistens 1 bis 3 Sätze, natürlich und herzlich. Keine Listen, keine Nummern.
  Bei einer Anleitung sagst du nur den ersten Schritt oder zwei und fragst, ob es weitergehen soll.
- Frag höchstens eine Sache auf einmal.
- Musst du im Internet suchen, sag vorher einen ganz kurzen Satz wie "Moment, ich schau kurz nach." und such dann.
- Was du hörst, wurde automatisch mitgeschrieben. Ist etwas unverständlich oder passt nicht zusammen, frag freundlich nach."""


def system_prompt():
    """Der gleichbleibende Teil der Anleitung. Er ändert sich nur, wenn die Familie Name, Anrede oder Sprache ändert,
    und kommt deshalb fast immer aus dem Zwischenspeicher von Anthropic (ein Zehntel des Preises bzw. weniger).
    Was sich bei jeder Frage ändert, steht im Hinweis der App (hinweis()), direkt vor der Frage."""
    p = profil()
    return SYSTEM.format(
        name_satz=p["name"].strip() or "einer Person, deren Namen du noch nicht kennst",
        anrede="Sie" if p.get("anrede") == "Sie" else "du",
        sprache=SPRACHEN.get(p.get("sprache"), "Deutsch"),
    )


def hinweis(gesprochen=False, bild=False):
    """Was sich bei jeder Frage ändert: Uhrzeit, Erinnerungen, Wissen, ob man gerade redet, ob ein Bildschirmfoto dabei ist."""
    t = jetzt()
    tage = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
    teile = [
        f"Heute ist {tage[t.weekday()]}, {t.day}.{t.month}.{t.year}, es ist {t.strftime('%H:%M')} Uhr.",
        "Deine Erinnerungen:\n" + ("\n".join(f"- Nummer {e['id']}: {erinnerung_wann(e)}: {e['text']}"
                                             + medikament_text(e, t) for e in erinnerungen_lesen()) or "- noch nichts"),
        "Was du über die Person weißt:\n" + ("\n".join(f"- Nummer {w['id']}: {w['text']}" for w in wissen_lesen())
                                             or "- noch nichts"),
    ]
    geb = sorted((geburtstag_naechster(g, t.date()) + (g,) for g in geburtstage_lesen()), key=lambda x: x[0])[:40]
    teile.append("Geburtstage (der nächste zuerst):\n" + ("\n".join(
        f"- {g['name']}: {g['tag']}.{g['monat']}.{g.get('jahr') or ''}, "
        + ("heute" if tage == 0 else "morgen" if tage == 1 else f"in {tage} Tagen")
        + (f" (wird {alter})" if alter else "") for tage, alter, g in geb) or "- noch keine"))
    seit = t - timedelta(days=14)
    eintraege = [e for e in tagebuch_lesen() if e["zeit"] >= seit.isoformat(timespec="seconds")][-40:]
    teile.append("Gesundheitstagebuch, letzte zwei Wochen:\n" + ("\n".join(
        f"- Nummer {e['id']}: {tagebuch_zeit(e)}: {TAGEBUCH_ARTEN[e['art']]} {e['wert']}"
        + (f" ({e['notiz']})" if e.get("notiz") else "") for e in eintraege) or "- nichts"))
    listen = listen_lesen()
    teile.append("Deine Listen:\n" + ("\n".join(f"- {name}: " + ", ".join(e["text"] for e in eintraege)
                                                for name, eintraege in listen.items()) or "- noch keine"))
    zeit = morgenrunde_zeit()
    teile.append(f"Morgenrunde: jeden Tag um {zeit} Uhr." if zeit else "Morgenrunde: nicht eingestellt.")
    teile.append(checkin_text())
    teile.append(freigabe_text())
    d = dolmetscher_jetzt()
    if d:
        teile.append(DOLMETSCHER.format(a=d["a"], b=d["b"]))
    elif gesprochen:
        teile.append(GESPROCHEN)
    if bild:
        teile.append(FOTO if bild == "foto" else BILDSCHIRM)
    return "<app>\n" + "\n\n".join(teile) + "\n</app>"


# ---------- Funktionen ----------

# ---------- Gespräche: jede Sitzung für sich, zum Weiterreden und Nachlesen ----------

def titel_aus(text):
    t = " ".join(str(text).split())
    return t if len(t) <= 60 else t[:60] + "…"


def gespraech_neu(nachrichten):
    zeit = jetzt().isoformat(timespec="seconds")
    erste = next((m["text"] for m in nachrichten if m["von"] == "ich"), "")
    return {"id": secrets.token_hex(4), "titel": titel_aus(erste), "begonnen": zeit, "zuletzt": zeit,
            "nachrichten": nachrichten}


def gespraeche_lesen():
    """Alle Gespräche, das zuletzt benutzte zuerst. Nur mit _lock aufrufen.
    Der eine Verlauf der ersten Version wird beim ersten Mal als ein Gespräch übernommen."""
    liste = lesen("gespraeche", None)
    if liste is None:
        alt = [{"von": "ich" if m.get("role") == "user" else "biko", "text": m["content"]}
               for m in lesen("verlauf", []) if isinstance(m, dict) and isinstance(m.get("content"), str)]
        liste = [gespraech_neu(alt)] if alt else []
        schreiben("gespraeche", liste)
        _pfad("verlauf").unlink(missing_ok=True)
    return liste


def gespraech_finden(liste, nr):
    return next((g for g in liste if g["id"] == nr), None)


def uebersicht(g):
    return {"id": g["id"], "titel": g["titel"], "zuletzt": g["zuletzt"], "anzahl": len(g["nachrichten"])}


def fuer_claude(nachrichten, bild=None):
    """Das bisherige Gespräch so, wie Claude es lesen soll. Eine Nachricht, die Biko für jemanden geschrieben hat,
    steht wieder als Werkzeug-Aufruf da: so weiß er bei "mach sie kürzer" noch, was drinstand.
    Biko liest mindestens die letzten MAX_VERLAUF - 1 Nachrichten. Der Anfang rückt in Zehnerschritten weiter, damit er
    über mehrere Fragen gleich bleibt: nur dann kommt der Verlauf aus dem Zwischenspeicher.
    `bild`: das noch gültige Bildschirmfoto als (Zeit, Bytes). Es bleibt bei der Frage, mit der es geschickt wurde."""
    zuviel = len(nachrichten) - (MAX_VERLAUF - 1)
    if zuviel > 0:
        nachrichten = nachrichten[zuviel // 10 * 10:]   # 29 bis 38 Nachrichten
    messages = []
    if nachrichten and nachrichten[0].get("vonselbst"):
        # Biko hat sich von selbst gemeldet (Morgenrunde): Claude braucht trotzdem eine Nachricht der Person davor
        messages.append({"role": "user", "content": "<app>Du hast dich von selbst gemeldet (Morgenrunde).</app>"})
    while not messages and nachrichten and nachrichten[0]["von"] != "ich":   # muss mit der Person beginnen
        nachrichten = nachrichten[1:]
    for i, m in enumerate(nachrichten):
        if m["von"] == "ich":
            if bild and m.get("bildschirm") == bild[0]:
                messages.append({"role": "user", "content": [bild_block(bild[1]), {"type": "text", "text": m["text"]}]})
            else:
                messages.append({"role": "user", "content": m["text"]})
            continue
        entwuerfe = m.get("nachrichten") or []
        if entwuerfe:
            messages.append({"role": "assistant", "content": [
                {"type": "tool_use", "id": f"frueher_{i}_{k}", "name": "nachricht_zeigen", "input": e}
                for k, e in enumerate(entwuerfe)]})
            messages.append({"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": f"frueher_{i}_{k}", "content": NACHRICHT_GEZEIGT}
                for k in range(len(entwuerfe))]})
        messages.append({"role": "assistant", "content": m["text"]})
    return messages


def bild_block(bild):
    return {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": base64.b64encode(bild).decode()}}


def zwischenspeichern(messages):
    """Markiert das Ende des bisherigen Verlaufs: bis dahin liest Anthropic bei der nächsten Frage aus dem Zwischenspeicher."""
    if not messages:
        return messages
    letzte = dict(messages[-1])
    inhalt = letzte["content"]
    bloecke = [{"type": "text", "text": inhalt}] if isinstance(inhalt, str) else [dict(b) for b in inhalt]
    bloecke[-1]["cache_control"] = {"type": "ephemeral"}
    letzte["content"] = bloecke
    return messages[:-1] + [letzte]


NACHRICHT_GEZEIGT = "Die Nachricht steht jetzt unter deiner Antwort, mit einem Knopf zum Kopieren."
LINK = re.compile(r"^https://[A-Za-z0-9.-]+\.[A-Za-z]{2,}(/\S*)?$")
NUMMER = re.compile(r"^\+?[0-9][0-9 ()/-]*$")
UEBER = {"whatsapp", "sms", "wechat"}


def nummer_pruefen(eingabe, muss=False):
    """Eine Telefonnummer, nur mit Ziffern, Leerzeichen, + / - ( ). Liefert sie ordentlich oder ''."""
    nummer = " ".join(str(eingabe or "").split())
    if not nummer and not muss:
        return ""
    ziffern = re.sub(r"\D", "", nummer)
    if not NUMMER.match(nummer) or not 3 <= len(ziffern) <= 15:
        raise ValueError("Das ist keine gültige Telefonnummer. Nimm nur eine Nummer, die dir die Person genannt hat.")
    return nummer
MAX_ZEIGEN = 3   # so viele Nachrichten und so viele Links passen unter eine Antwort
WARN_STUFEN = ("betrug", "vorsicht")   # Warnkarte: rot (sehr wahrscheinlich Betrug) oder orange (bitte nachprüfen)
MAX_WARN_PUNKTE = 4


def zeige_werkzeuge():
    """Die Werkzeuge, mit denen Biko etwas unter seine Antwort stellt, und die Listen, in denen es landet."""
    entwuerfe, links, anrufe, karten, tagebuch, warnungen = [], [], [], [], [], []

    def nachricht_zeigen(eingabe):
        text = str(eingabe.get("text") or "").strip()[:1500]
        if not text:
            raise ValueError("Der Text der Nachricht fehlt. Frag nach, was drinstehen soll.")
        if len(entwuerfe) >= MAX_ZEIGEN:
            raise ValueError(f"Höchstens {MAX_ZEIGEN} Nachrichten pro Antwort.")
        ueber = str(eingabe.get("ueber") or "").strip().lower()
        nummer = nummer_pruefen(eingabe.get("nummer"))
        entwuerfe.append({"an": " ".join(str(eingabe.get("an") or "").split())[:80], "text": text,
                          **({"ueber": ueber} if ueber in UEBER else {}), **({"nummer": nummer} if nummer else {})})
        return NACHRICHT_GEZEIGT

    def anruf_zeigen(eingabe):
        nummer = nummer_pruefen(eingabe.get("nummer"), muss=True)
        if anrufe:
            raise ValueError("Pro Antwort nur ein Anruf.")
        anrufe.append({"name": " ".join(str(eingabe.get("name") or "").split())[:60], "nummer": nummer})
        return "Der Knopf zum Anrufen steht jetzt unter deiner Antwort (in der Blase geht das Telefon gleich auf)."

    def link_zeigen(eingabe):
        url = str(eingabe.get("url") or "").strip()
        if len(url) > 500 or not LINK.match(url):
            raise ValueError("Das ist keine sichere Internet-Adresse. Sie muss vollständig sein und mit https:// beginnen.")
        if len(links) >= MAX_ZEIGEN:
            raise ValueError(f"Höchstens {MAX_ZEIGEN} Links pro Antwort.")
        if url not in [l["url"] for l in links]:
            titel = " ".join(str(eingabe.get("titel") or "").split())[:60]
            links.append({"titel": titel or urlparse(url).hostname, "url": url})
        return "Der Link steht jetzt als Knopf unter deiner Antwort."

    def liste_zeigen(eingabe):
        listen = listen_lesen()
        name = listen_name(eingabe.get("liste"), listen)
        if name not in listen:
            raise ValueError(f"Die Liste '{name}' ist leer. Es gibt: " + (", ".join(listen) or "noch keine Listen") + ".")
        if any(k["name"] == name for k in karten):
            return "Die Liste steht schon unter deiner Antwort."
        karten.append({"name": name, "eintraege": listen[name]})
        return "Die Liste steht jetzt als Karte unter deiner Antwort; dort kann man Erledigtes wegtippen."

    def tagebuch_zeigen(eingabe):
        try:
            tage = max(1, min(int(eingabe.get("tage") or 14), 92))
        except (TypeError, ValueError):
            tage = 14
        arten = [a for a in (eingabe.get("arten") or []) if a in TAGEBUCH_ARTEN]
        seit = (jetzt() - timedelta(days=tage)).isoformat(timespec="seconds")
        zeilen = [e for e in tagebuch_lesen() if e["zeit"] >= seit and (not arten or e["art"] in arten)]
        if not zeilen:
            raise ValueError("Dafür steht nichts im Tagebuch. Sag das der Person.")
        if tagebuch:
            return "Das Tagebuch steht schon unter deiner Antwort."
        tagebuch.append({"tage": tage, "zeilen": zeilen[-60:]})
        return f"Das Tagebuch ({len(zeilen)} Einträge) steht jetzt als Karte unter deiner Antwort, zum Kopieren für den Arzt."

    def warnung_zeigen(eingabe):
        stufe = str(eingabe.get("stufe") or "").strip().lower()
        if stufe not in WARN_STUFEN:
            raise ValueError("stufe muss 'betrug' oder 'vorsicht' sein.")
        titel = " ".join(str(eingabe.get("titel") or "").split())[:120]
        if not titel:
            raise ValueError("Der Titel fehlt: in einem kurzen Satz, worum es geht.")

        def punkte(name):
            liste = eingabe.get(name) or []
            if isinstance(liste, str):
                liste = [liste]
            return [p for p in (" ".join(str(x).split())[:200] for x in liste[:MAX_WARN_PUNKTE]) if p]
        tun = punkte("tun")
        if not tun:
            raise ValueError("Schreib bei 'tun' mindestens einen Schritt, was die Person jetzt machen soll.")
        if warnungen:
            raise ValueError("Pro Antwort nur eine Warnkarte.")
        warnungen.append({"stufe": stufe, "titel": titel, "anzeichen": punkte("anzeichen"), "tun": tun})
        return ("Die Warnkarte steht jetzt groß unter deiner Antwort. Wiederhol nicht alles, sag kurz und ruhig, worum es "
                "geht, und biete an, jemanden aus der Familie anzurufen.")

    werkzeuge = {
        "warnung_zeigen": {"tun": warnung_zeigen, "schema": {
            "name": "warnung_zeigen",
            "description": "Stellt eine große Warnkarte unter deine Antwort, wenn etwas nach Betrug aussieht (SMS, Nachricht, "
                           "Anruf, Brief, Webseite): woran man es erkennt und was die Person jetzt tun soll. "
                           "Alles in der Sprache der Person, kurz und einfach.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "stufe": {"type": "string", "enum": list(WARN_STUFEN),
                              "description": "'betrug': sehr wahrscheinlich Betrug. 'vorsicht': unsicher, bitte nachprüfen."},
                    "titel": {"type": "string", "description": "Ein kurzer Satz, z. B. 'Diese SMS ist nicht von der Post.'"},
                    "anzeichen": {"type": "array", "items": {"type": "string"}, "maxItems": MAX_WARN_PUNKTE,
                                  "description": "Woran man es erkennt, je ein kurzer Satz, höchstens 4."},
                    "tun": {"type": "array", "items": {"type": "string"}, "maxItems": MAX_WARN_PUNKTE,
                            "description": "Was sie jetzt tun soll, je ein kurzer Satz, höchstens 4, das Wichtigste zuerst."},
                },
                "required": ["stufe", "titel", "tun"],
            },
        }},
        "tagebuch_zeigen": {"tun": tagebuch_zeigen, "schema": {
            "name": "tagebuch_zeigen",
            "description": "Stellt das Gesundheitstagebuch als Karte unter deine Antwort (mit Knopf zum Kopieren, z. B. für den Arzt).",
            "input_schema": {
                "type": "object",
                "properties": {
                    "tage": {"type": "integer", "description": "Wie viele Tage zurück, Standard 14."},
                    "arten": {"type": "array", "items": {"type": "string", "enum": list(TAGEBUCH_ARTEN)},
                              "description": "Nur diese Arten, z. B. ['blutdruck']. Leer heißt alles."},
                },
            },
        }},
        "liste_zeigen": {"tun": liste_zeigen, "schema": {
            "name": "liste_zeigen",
            "description": "Stellt eine Liste der Person (z. B. die Einkaufsliste) als Karte unter deine Antwort. "
                           "Dort kann sie Gekauftes oder Erledigtes wegtippen.",
            "input_schema": {
                "type": "object",
                "properties": {"liste": {"type": "string", "description": "Name der Liste, z. B. 'Einkaufen'."}},
                "required": ["liste"],
            },
        }},
        "nachricht_zeigen": {"tun": nachricht_zeigen, "schema": {
            "name": "nachricht_zeigen",
            "description": "Stellt eine fertige Nachricht, die die Person jemandem schicken will, unter deine Antwort, "
                           "mit einem Knopf zum Kopieren. Verschickt nichts.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "an": {"type": "string", "description": "Für wen die Nachricht ist, z. B. 'Anna' oder 'Dr. Huber'."},
                    "text": {"type": "string", "description": "Die ganze Nachricht, fertig zum Verschicken, ohne Anführungszeichen."},
                    "ueber": {"type": "string", "enum": ["whatsapp", "sms", "wechat"],
                              "description": "Womit die Person sie schicken will, wenn sie es gesagt hat."},
                    "nummer": {"type": "string", "description": "Telefonnummer der Person, an die es geht, falls bekannt "
                                                                "(für WhatsApp oder SMS)."},
                },
                "required": ["text"],
            },
        }},
        "link_zeigen": {"tun": link_zeigen, "schema": {
            "name": "link_zeigen",
            "description": "Stellt einen Link als großen Knopf unter deine Antwort, zum Beispiel zur Quelle eines Angebots "
                           "oder zum aktuellen Prospekt eines Geschäfts. Nur Adressen aus deinen Suchergebnissen.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "titel": {"type": "string", "description": "Kurze Beschriftung in der Sprache der Person, z. B. 'Billa Flugblatt'."},
                    "url": {"type": "string", "description": "Die vollständige Adresse, beginnt mit https://"},
                },
                "required": ["titel", "url"],
            },
        }},
        "anruf_zeigen": {"tun": anruf_zeigen, "schema": {
            "name": "anruf_zeigen",
            "description": "Stellt einen großen Knopf zum Anrufen unter deine Antwort (in der Blase geht das Telefon gleich "
                           "mit der Nummer auf). Ruft nicht selbst an.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Wen man anruft, z. B. 'Peter' oder 'Rettung'."},
                    "nummer": {"type": "string", "description": "Die Telefonnummer, z. B. '0664 1234567' oder '144'."},
                },
                "required": ["name", "nummer"],
            },
        }},
    }
    return werkzeuge, entwuerfe, links, anrufe, karten, tagebuch, warnungen


def chat(text, gespraech_nr="", beim_text=None, gesprochen=False):
    """Eine Frage im Gespräch. `beim_text` bekommt die Antwort stückweise, `gesprochen`: man redet gerade wie am Telefon."""
    with _lock:
        g = gespraech_finden(gespraeche_lesen(), gespraech_nr)
    verlauf = g["nachrichten"] if g else []
    lebenszeichen()
    dolmetscher_jetzt(verlaengern=True)
    bild = bildschirm_frisch()   # (Zeit, Bytes) oder None
    # Ein Bildschirmfoto geht nur einmal mit, bei der ersten Frage danach. Danach steht es im Verlauf bei dieser
    # Frage und kommt, solange es gilt, günstig aus dem Zwischenspeicher, statt jedes Mal neu bezahlt zu werden.
    schon_da = bool(bild) and any(m.get("bildschirm") == bild[0] for m in verlauf)
    neu_bild = bool(bild) and not schon_da
    frage = [{"type": "text", "text": hinweis(gesprochen, bild=bild[2] if bild else False)}]
    if neu_bild:
        frage.append(bild_block(bild[1]))
    frage.append({"type": "text", "text": text})
    messages = zwischenspeichern(fuer_claude(verlauf, bild)) + [{"role": "user", "content": frage}]
    zeigen, entwuerfe, links, anrufe, karten, tagebuch, warnungen = zeige_werkzeuge()
    vorher, wusste = erinnerungen_lesen(), wissen_lesen()
    start, erste = time.monotonic(), []

    def beim_stueck(stueck):
        if not erste:
            erste.append(time.monotonic() - start)
        beim_text(stueck)
    antwort = frage_claude(system_prompt(), messages, websuche=True, werkzeuge={**WERKZEUGE, **zeigen},
                           modell=modell_fuer(text, bild),
                           **({"beim_text": beim_stueck} if beim_text else {}))
    if erste:
        protokoll(f"Claude: erste Worte nach {erste[0] * 1000:.0f} ms, fertig nach {(time.monotonic() - start) * 1000:.0f} ms")
    # Was Biko in dieser Antwort wirklich getan hat: die App zeigt es unter der Antwort, auch beim Wiederöffnen
    nachher, weiss = erinnerungen_lesen(), wissen_lesen()
    alt, neu = {e["id"] for e in vorher}, {e["id"] for e in nachher}
    kannte = {w["id"] for w in wusste}
    getan = {"gemerkt": [e for e in nachher if e["id"] not in alt],
             "vergessen": [e for e in vorher if e["id"] not in neu],
             "gelernt": [w for w in weiss if w["id"] not in kannte],
             "nachrichten": entwuerfe, "links": links, "anrufe": anrufe, "listen": karten,
             "tagebuch": tagebuch, "warnungen": warnungen}
    zeit = jetzt().isoformat(timespec="seconds")
    with _lock:   # erst jetzt speichern: geht die Antwort schief, bleibt das Gespräch, wie es war
        liste = gespraeche_lesen()
        g = gespraech_finden(liste, gespraech_nr) or gespraech_neu([])
        g["nachrichten"] = (g["nachrichten"] + [
            {"von": "ich", "text": text, "zeit": zeit, **({"bildschirm": bild[0]} if neu_bild else {})},
            {"von": "biko", "text": antwort, "zeit": zeit, **{k: v for k, v in getan.items() if v}},
        ])[-MAX_GESPEICHERT:]
        g["titel"] = g["titel"] or titel_aus(text)
        g["zuletzt"] = zeit
        schreiben("gespraeche", ([g] + [x for x in liste if x["id"] != g["id"]])[:MAX_GESPRAECHE])
    return {"antwort": antwort, "gespraech": uebersicht(g), "erinnerungen": erinnerungen_app(nachher), "wissen": weiss,
            "morgenrunde": morgenrunde_zeit(), "geburtstage": geburtstage_lesen(),
            "dolmetscher": dolmetscher_jetzt(), "checkin": checkin_lesen().get("zeit"), **getan}


UHRZEIT = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
TAGE = {"mo", "di", "mi", "do", "fr", "sa", "so"}


MAX_ERINNERUNGEN = 30
TAG_NAMEN = {"mo": "Montag", "di": "Dienstag", "mi": "Mittwoch", "do": "Donnerstag", "fr": "Freitag",
             "sa": "Samstag", "so": "Sonntag"}


def erinnerung_pruefen(e):
    """Eine Erinnerung: jeden Tag oder an Wochentagen (`tage`), oder einmalig an einem `datum` (JJJJ-MM-TT)."""
    zeit = str(e.get("zeit") or "")
    text = str(e.get("text") or "").strip()[:120]
    tage = [t for t in e.get("tage", []) if t in TAGE] if isinstance(e.get("tage"), list) else []
    if not UHRZEIT.match(zeit) or not text:
        raise ValueError("Bitte Uhrzeit (z. B. 08:00) und einen Text angeben.")
    datum = e.get("datum") or None
    if datum is not None:
        try:
            datum = date.fromisoformat(str(datum)).isoformat()
        except ValueError:
            raise ValueError("Das Datum bitte als JJJJ-MM-TT angeben, z. B. 2026-11-24.")
    neu = {"id": str(e.get("id") or uuid.uuid4().hex[:10]), "zeit": zeit, "text": text,
           "tage": sorted(TAGE) if datum or not tage else tage, "aktiv": bool(e.get("aktiv", True)), "datum": datum}
    if e.get("medikament") is True:
        # Medikament: Biko fragt nach, ob es genommen wurde, und gibt der Familie Bescheid, wenn nicht (melden)
        melden = []
        for k in (e.get("melden") or [])[:3] if isinstance(e.get("melden"), list) else []:
            name = " ".join(str((k or {}).get("name") or "").split())[:40]
            if name:
                melden.append({"name": name, "nummer": nummer_pruefen((k or {}).get("nummer"), muss=True)})
        try:
            nach = max(30, min(int(e.get("melden_nach") or MELDEN_NACH), 240))
        except (TypeError, ValueError):
            nach = MELDEN_NACH
        neu.update({"medikament": True, "melden": melden, "melden_nach": nach})
    if e.get("seit"):
        neu["seit"] = str(e["seit"])[:25]
    return neu


def erinnerungen_lesen():
    """Alle Erinnerungen. Einmalige, deren Tag vorbei ist, fallen weg."""
    heute = jetzt().strftime("%Y-%m-%d")
    return [e for e in lesen("erinnerungen", []) if not e.get("datum") or e["datum"] >= heute]


def erinnerung_wann(e):
    if e.get("datum"):
        return f"einmal am {e['datum']} um {e['zeit']}"
    if len(e["tage"]) == 7:
        return f"jeden Tag um {e['zeit']}"
    return f"jeden {', '.join(TAG_NAMEN[t] for t in TAGE_REIHE if t in e['tage'])} um {e['zeit']}"


TAGE_REIHE = ["mo", "di", "mi", "do", "fr", "sa", "so"]


# ---------- Werkzeuge: so schreibt sich Biko Erinnerungen selbst auf ----------

def erinnerung_merken(eingabe):
    e = {k: eingabe.get(k) for k in ("text", "zeit", "datum", "tage")}
    if eingabe.get("medikament") is True:
        melden = []
        if eingabe.get("familie") is True:
            melden = eingabe.get("kontakte") or checkin_lesen().get("kontakte") or []
            if not melden:
                raise ValueError("Wer soll Bescheid bekommen, wenn sie das Medikament nicht bestätigt? Frag nach Name "
                                 "und Nummer (oder nimm sie aus dem Gedächtnis) und gib sie als kontakte mit.")
        e.update({"medikament": True, "melden": melden, "melden_nach": eingabe.get("melden_nach")})
    j = jetzt()
    e["seit"] = j.isoformat(timespec="seconds")
    neu = erinnerung_pruefen(e)
    if neu["datum"] and (neu["datum"], neu["zeit"]) < (j.strftime("%Y-%m-%d"), j.strftime("%H:%M")):
        raise ValueError(f"Dieser Zeitpunkt ist schon vorbei. Jetzt ist {j.strftime('%Y-%m-%d %H:%M')}.")
    with _lock:
        liste = erinnerungen_lesen()
        if len(liste) >= MAX_ERINNERUNGEN:
            raise ValueError(f"Es sind schon {MAX_ERINNERUNGEN} Erinnerungen gespeichert. Erst muss eine gelöscht werden.")
        schreiben("erinnerungen", sorted(liste + [neu], key=lambda e: e["zeit"]))
    zusatz = ""
    if neu.get("medikament"):
        zusatz = (" Zur Uhrzeit fragt Biko, ob sie es genommen hat, und nach 30 Minuten noch einmal.")
        if neu["melden"]:
            wer = " und ".join(k["name"] for k in neu["melden"])
            zusatz += (f" Ist es {neu['melden_nach']} Minuten nach der Uhrzeit nicht bestätigt, bekommt {wer} eine SMS."
                       + ("" if sms_bereit() else " Achtung: Der SMS-Dienst ist noch nicht eingerichtet, bis dahin geht "
                                                  "keine SMS hinaus. Sag ihr das ehrlich; das richtet die Familie ein."))
    return f"Gespeichert: {erinnerung_wann(neu)}: {neu['text']}." + zusatz


def erinnerung_loeschen(eingabe):
    nr = str(eingabe.get("id") or "")
    with _lock:
        liste = erinnerungen_lesen()
        weg = [e for e in liste if e["id"] == nr]
        if not weg:
            raise ValueError("Unter dieser Nummer ist nichts gespeichert. Die Nummern stehen in deiner Liste.")
        schreiben("erinnerungen", [e for e in liste if e["id"] != nr])
    return f"Gelöscht: {erinnerung_wann(weg[0])}: {weg[0]['text']}"


# ---------- Werkzeuge: so merkt sich Biko, was er über die Person weiß ----------

def wissen_merken(eingabe):
    text = " ".join(str(eingabe.get("text") or "").split())[:400]
    if not text:
        raise ValueError("Bitte kurz aufschreiben, was du dir merken willst.")
    with _lock:
        liste = wissen_lesen()
        if any(w["text"].casefold() == text.casefold() for w in liste):
            return f"Das weißt du schon: {text}"
        if len(liste) >= MAX_WISSEN:
            raise ValueError(f"Es sind schon {MAX_WISSEN} Einträge. Streich erst einen alten oder unwichtigen.")
        schreiben("wissen", liste + [{"id": uuid.uuid4().hex[:10], "text": text,
                                      "zeit": jetzt().isoformat(timespec="seconds")}])
    return f"Gemerkt: {text}"


def wissen_vergessen(eingabe):
    nr = str(eingabe.get("id") or "")
    with _lock:
        liste = wissen_lesen()
        weg = [w for w in liste if w["id"] == nr]
        if not weg:
            raise ValueError("Unter dieser Nummer ist nichts gespeichert. Die Nummern stehen in deiner Liste.")
        schreiben("wissen", [w for w in liste if w["id"] != nr])
    return f"Gestrichen: {weg[0]['text']}"


# ---------- Listen: Einkaufsliste, Notizen und was die Person sonst braucht ----------

MAX_LISTEN = 12
MAX_EINTRAEGE = 60


def listen_lesen():
    """{"Einkaufen": [{"id", "text"}], ...}. Leere Listen gibt es nicht."""
    daten = lesen("listen", {})
    return daten if isinstance(daten, dict) else {}


def listen_name(eingabe, listen):
    """Der Name einer Liste. Gibt es sie schon (auch anders geschrieben), dann diese."""
    name = " ".join(str(eingabe or "").split())[:40]
    if not name:
        raise ValueError("Welche Liste? Zum Beispiel 'Einkaufen' oder 'Notizen'.")
    return next((n for n in listen if n.casefold() == name.casefold()), name)


def liste_aendern(eingabe):
    dazu = [" ".join(str(x).split())[:200] for x in (eingabe.get("dazu") or []) if str(x).strip()]
    weg = [" ".join(str(x).split()).casefold() for x in (eingabe.get("weg") or []) if str(x).strip()]
    leeren = bool(eingabe.get("leeren"))
    with _lock:
        listen = listen_lesen()
        name = listen_name(eingabe.get("liste"), listen)
        eintraege = listen.get(name, [])
        if name not in listen and len(listen) >= MAX_LISTEN:
            raise ValueError(f"Es gibt schon {MAX_LISTEN} Listen. Nimm eine bestehende.")
        vorher = len(eintraege)
        if leeren:
            eintraege = []
        nicht_da = [w for w in weg if not any(e["text"].casefold() == w or e["id"] == w for e in eintraege)]
        # "Käse" streicht auch "Käse (Emmentaler)": erst genau, sonst was das Wort enthält
        for w in nicht_da:
            treffer = [e for e in eintraege if w in e["text"].casefold()]
            if len(treffer) == 1:
                weg.append(treffer[0]["id"])
        eintraege = [e for e in eintraege if e["text"].casefold() not in weg and e["id"] not in weg]
        gestrichen = vorher - len(eintraege)
        neu = []
        for text in dazu:
            if any(e["text"].casefold() == text.casefold() for e in eintraege):
                continue
            if len(eintraege) >= MAX_EINTRAEGE:
                raise ValueError(f"Auf einer Liste haben höchstens {MAX_EINTRAEGE} Dinge Platz.")
            eintraege.append({"id": uuid.uuid4().hex[:8], "text": text})
            neu.append(text)
        if eintraege:
            listen[name] = eintraege
        else:
            listen.pop(name, None)
        schreiben("listen", listen)
    teile = []
    if neu:
        teile.append("Dazugeschrieben: " + ", ".join(neu))
    if gestrichen:
        teile.append(f"{gestrichen} weggenommen")
    if weg and not gestrichen and not leeren:
        teile.append("Nichts davon stand drauf")
    return f"{name}: " + ("; ".join(teile) or "unverändert") + f". Jetzt drauf: {len(eintraege)}."


def liste_wegtippen(name, nr):
    """Aus der App: ein Eintrag ist erledigt. Gibt es ihn nicht mehr, ist das auch recht."""
    with _lock:
        listen = listen_lesen()
        name = next((n for n in listen if n == name), None)
        if name:
            rest = [e for e in listen[name] if e["id"] != nr]
            if rest:
                listen[name] = rest
            else:
                listen.pop(name)
            schreiben("listen", listen)
        return {"name": name, "eintraege": listen.get(name, []) if name else []}


# ---------- Gesundheitstagebuch: Messwerte und Befinden, für sich und für den Arzt ----------

TAGEBUCH_ARTEN = {"blutdruck": "Blutdruck", "zucker": "Blutzucker", "puls": "Puls", "gewicht": "Gewicht",
                  "befinden": "Befinden", "schmerz": "Schmerzen", "medikament": "Medikament", "sonstiges": "Notiz"}
BLUTDRUCK = re.compile(r"^(\d{2,3})\s*/\s*(\d{2,3})$")
MAX_TAGEBUCH = 500


def tagebuch_lesen():
    """[{"id", "zeit", "art", "wert", "notiz"}], das älteste zuerst."""
    daten = lesen("gesundheit", [])
    return daten if isinstance(daten, list) else []


def tagebuch_zeit(e):
    t = datetime.fromisoformat(e["zeit"])
    return f"{t.day}.{t.month}. {t.strftime('%H:%M')}"


def gesundheit_notieren(eingabe):
    art = str(eingabe.get("art") or "").strip().lower()
    if art not in TAGEBUCH_ARTEN:
        raise ValueError("Die Art muss eine von diesen sein: " + ", ".join(TAGEBUCH_ARTEN) + ".")
    wert = " ".join(str(eingabe.get("wert") or "").split())[:120]
    if not wert:
        raise ValueError("Der Wert fehlt. Frag kurz nach.")
    if art == "blutdruck":
        m = BLUTDRUCK.match(wert.replace(" zu ", "/"))
        if not m or not (60 <= int(m[1]) <= 260 and 30 <= int(m[2]) <= 160):
            raise ValueError("Blutdruck bitte als zwei Zahlen wie 135/85. Frag nach, wenn eine fehlt.")
        wert = f"{m[1]}/{m[2]}"
    notiz = " ".join(str(eingabe.get("notiz") or "").split())[:200]
    e = {"id": uuid.uuid4().hex[:6], "zeit": jetzt().isoformat(timespec="seconds"), "art": art, "wert": wert,
         **({"notiz": notiz} if notiz else {})}
    with _lock:
        schreiben("gesundheit", (tagebuch_lesen() + [e])[-MAX_TAGEBUCH:])
    return f"Ins Tagebuch geschrieben: {TAGEBUCH_ARTEN[art]} {wert}"


def gesundheit_streichen(eingabe):
    nr = str(eingabe.get("id") or "")
    with _lock:
        liste = tagebuch_lesen()
        if not any(e["id"] == nr for e in liste):
            raise ValueError("Unter dieser Nummer steht nichts im Tagebuch.")
        schreiben("gesundheit", [e for e in liste if e["id"] != nr])
    return "Gestrichen."


# ---------- Dolmetscher: Biko übersetzt ein Gespräch hin und her ----------

DOLMETSCHER_GILT = 30 * 60   # so lange nach dem letzten Satz bleibt er an, dann ist er von selbst aus
_dolmetscher_je = {}   # je Person {"a", "b", "bis"}, nur im Speicher


def _dolm():
    return _dolmetscher_je.setdefault(person_jetzt(), {"a": "", "b": "", "bis": 0.0})


def dolmetscher_jetzt(verlaengern=False):
    """{"a", "b"} (die zwei Sprachen), solange Biko dolmetscht, sonst None. `verlaengern`: es wurde gerade gesprochen."""
    with _lock:
        if not _dolm()["a"] or time.time() > _dolm()["bis"]:
            return None
        if verlaengern:
            _dolm()["bis"] = time.time() + DOLMETSCHER_GILT
        return {"a": _dolm()["a"], "b": _dolm()["b"]}


def dolmetscher(eingabe):
    if not eingabe.get("an"):
        with _lock:
            _dolm().update(a="", b="", bis=0.0)
        return "Der Dolmetscher ist aus. Sag es der Person kurz in ihrer Sprache."
    a = " ".join(str(eingabe.get("sprache_a") or "Chinesisch").split())[:30]
    b = " ".join(str(eingabe.get("sprache_b") or "Deutsch").split())[:30]
    if a.casefold() == b.casefold():
        raise ValueError("Das sind zweimal dieselbe Sprache. Frag, in welche Sprache du übersetzen sollst.")
    with _lock:
        _dolm().update(a=a, b=b, bis=time.time() + DOLMETSCHER_GILT)
    return (f"Der Dolmetscher ist an ({a} und {b}). Sag jetzt in beiden Sprachen in einem kurzen Satz, dass du übersetzt. "
            "Ab der nächsten Frage übersetzt du nur noch.")


# ---------- Check-in: Biko fragt jeden Tag nach, im Notfall bekommt die Familie eine SMS ----------

CHECKIN_VORHER = 2 * 3600   # ein Lebenszeichen so lange vor der Uhrzeit zählt auch schon für heute


def sms_bereit():
    return bool(TWILIO_SID and TWILIO_TOKEN and TWILIO_VON)


def nummer_international(nummer):
    """0664 123 -> +43664123 (österreichische Nummer), 0049 ... -> +49 ..., +86 ... bleibt."""
    roh = str(nummer).strip()
    n = re.sub(r"\D", "", roh)
    if roh.startswith("+"):
        return "+" + n
    if n.startswith("00"):
        return "+" + n[2:]
    if n.startswith("0"):
        return "+43" + n[1:]
    return "+" + n


def sms_schicken(nummer, text):
    """Eine SMS über Twilio. Wirft RuntimeError, wenn es nicht geht."""
    daten = urlencode({"From": TWILIO_VON, "To": nummer_international(nummer), "Body": text}).encode()
    anfrage = urllib.request.Request(f"https://api.twilio.com/2010-04-01/Accounts/{quote(TWILIO_SID)}/Messages.json",
                                     data=daten, method="POST")
    zugang = base64.b64encode(f"{TWILIO_SID}:{TWILIO_TOKEN}".encode()).decode()
    anfrage.add_header("Authorization", "Basic " + zugang)
    anfrage.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        with urllib.request.urlopen(anfrage, timeout=20) as antwort:
            antwort.read()
    except urllib.error.HTTPError as e:
        try:
            grund = json.loads(e.read()[:500]).get("message", "")   # die Meldung von Twilio, ohne Inhalt der SMS
        except Exception:
            grund = ""
        protokoll(f"SMS-Fehler: {e.code} {grund}")
        raise RuntimeError("Die SMS ging nicht hinaus.")
    except OSError:
        protokoll("SMS-Fehler: keine Verbindung")
        raise RuntimeError("Die SMS ging nicht hinaus.")


def familie_sms(text, kontakte=None):
    """Schickt `text` an alle Kontakte des Check-ins. Liefert die Namen, die sie bekommen haben."""
    kontakte = kontakte if kontakte is not None else checkin_lesen().get("kontakte") or []
    if not sms_bereit():
        raise ValueError("Der SMS-Dienst ist noch nicht eingerichtet. Biko kann der Familie keine SMS schicken. "
                         "Biete an, anzurufen (anruf_zeigen).")
    if not kontakte:
        raise ValueError("Es ist niemand eingetragen, der eine SMS bekommt. Frag, wen du benachrichtigen sollst, "
                         "und trag ihn mit checkin_einstellen ein.")
    heute = jetzt().strftime("%Y-%m-%d")
    with _lock:
        d = checkin_lesen()
        zaehler = d.get("sms_tag") if (d.get("sms_tag") or {}).get("datum") == heute else {"datum": heute, "anzahl": 0}
        if zaehler["anzahl"] + len(kontakte) > MAX_SMS_TAG:
            raise ValueError("Heute sind schon genug SMS hinausgegangen. Biete an, anzurufen (anruf_zeigen).")
        schreiben("checkin", {**d, "sms_tag": {"datum": heute, "anzahl": zaehler["anzahl"] + len(kontakte)}})
    bekommen = []
    for k in kontakte:
        try:
            sms_schicken(k["nummer"], text[:600])
            bekommen.append(k["name"])
        except RuntimeError:
            pass
    protokoll(f"SMS: an {len(bekommen)} von {len(kontakte)} Kontakten")
    if not bekommen:
        raise ValueError("Die SMS ging nicht hinaus. Biete an, anzurufen (anruf_zeigen).")
    return bekommen


def checkin_lesen():
    """{"zeit", "stunden", "kontakte": [{"name", "nummer"}], "seit", "zuletzt", "alarm": {"datum", "zeit", "entwarnt"}}"""
    d = lesen("checkin", {})
    return d if isinstance(d, dict) else {}


def checkin_text():
    d = checkin_lesen()
    if not d.get("zeit"):
        return "Täglicher Check-in: nicht eingestellt." + ("" if sms_bereit() else " Der SMS-Dienst ist nicht eingerichtet.")
    wer = ", ".join(f"{k['name']} ({k['nummer']})" for k in d.get("kontakte") or []) or "niemand"
    return (f"Täglicher Check-in: jeden Tag um {d['zeit']} Uhr; ohne Lebenszeichen nach {d.get('stunden', 2)} Stunden "
            f"bekommt eine SMS: {wer}." + ("" if sms_bereit() else " Der SMS-Dienst ist aber noch nicht eingerichtet."))


def checkin_einstellen(eingabe):
    zeit = str(eingabe.get("zeit") or "").strip().lower()
    if zeit in ("aus", "off", "nein", ""):
        with _lock:
            schreiben("checkin", {**checkin_lesen(), "zeit": None})
        return "Der tägliche Check-in ist aus."
    if not UHRZEIT.match(zeit):
        raise ValueError("Bitte die Uhrzeit als HH:MM angeben, z. B. 10:00, oder 'aus'.")
    try:
        stunden = max(1, min(int(eingabe.get("stunden") or 2), 8))
    except (TypeError, ValueError):
        stunden = 2
    kontakte = []
    for k in (eingabe.get("kontakte") or [])[:3]:
        name = " ".join(str((k or {}).get("name") or "").split())[:40]
        if name:
            kontakte.append({"name": name, "nummer": nummer_pruefen((k or {}).get("nummer"), muss=True)})
    if not kontakte:
        raise ValueError("Wer soll die SMS bekommen? Frag nach Name und Nummer (oder nimm sie aus dem Gedächtnis).")
    with _lock:
        schreiben("checkin", {**checkin_lesen(), "zeit": zeit, "stunden": stunden, "kontakte": kontakte,
                              "seit": jetzt().isoformat(timespec="seconds")})
    wer = " und ".join(k["name"] for k in kontakte)
    return (f"Eingestellt: jeden Tag um {zeit} Uhr. Kommt bis {stunden} Stunden danach kein Lebenszeichen, bekommt "
            f"{wer} eine SMS." + ("" if sms_bereit() else " Achtung: Der SMS-Dienst ist noch nicht eingerichtet, bis "
                                 "dahin geht keine SMS hinaus. Sag ihr das ehrlich; das richtet die Familie ein."))


def familie_benachrichtigen(eingabe):
    text = " ".join(str(eingabe.get("text") or "").split())[:400]
    if not text:
        raise ValueError("Was soll in der SMS stehen?")
    name = profil().get("name") or ""
    bekommen = familie_sms(f"Biko{' für ' + name if name else ''}: {text}")
    return f"Die SMS ist an {' und '.join(bekommen)} hinausgegangen. Sag ihr das."


def lebenszeichen():
    """Die Person hat etwas mit Biko gemacht. Kam heute schon eine Warnung hinaus, bekommt die Familie eine Entwarnung."""
    if getattr(_faden, "besuch", False):
        return
    t = jetzt()
    with _lock:
        d = checkin_lesen()
        alarm = d.get("alarm") or {}
        entwarnen = alarm.get("datum") == t.strftime("%Y-%m-%d") and not alarm.get("entwarnt")
        if entwarnen:
            alarm = {**alarm, "entwarnt": t.isoformat(timespec="seconds")}
        schreiben("checkin", {**d, "zuletzt": t.isoformat(timespec="seconds"), "alarm": alarm})
    if entwarnen and alarm.get("geschickt"):
        name = profil().get("name") or ""
        try:
            familie_sms(f"Biko: Entwarnung, {name or 'sie'} hat sich gerade gemeldet."
                        if not str(profil().get("sprache")).startswith("zh") else f"Biko：放心，{name or '她'}刚刚回复了。")
        except ValueError:
            pass


def checkin_heute(t=None):
    """(Uhrzeit heute, Frist heute) oder None, wenn der Check-in heute nicht gilt."""
    d = checkin_lesen()
    if not d.get("zeit"):
        return None
    t = t or jetzt()
    h, m = map(int, d["zeit"].split(":"))
    um = t.replace(hour=h, minute=m, second=0, microsecond=0)
    try:
        seit = datetime.fromisoformat(d.get("seit") or "")
    except ValueError:
        seit = None
    if seit and seit > um:   # eingestellt, als die Zeit heute schon vorbei war: gilt ab morgen
        return None
    return um, um + timedelta(hours=d.get("stunden", 2))


def gemeldet_heute(t=None):
    t = t or jetzt()
    heute = checkin_heute(t)
    zuletzt = checkin_lesen().get("zuletzt")
    if not heute or not zuletzt:
        return False
    return datetime.fromisoformat(zuletzt) >= heute[0] - timedelta(seconds=CHECKIN_VORHER)


def checkin_pruefen(t=None):
    """Vom Hausmeister jede Minute: ist die Frist vorbei, ohne Lebenszeichen, bekommt die Familie (einmal am Tag) eine SMS."""
    t = t or jetzt()
    heute = checkin_heute(t)
    if not heute or t < heute[1] or gemeldet_heute(t):
        return None
    datum = t.strftime("%Y-%m-%d")
    with _lock:
        d = checkin_lesen()
        if (d.get("alarm") or {}).get("datum") == datum:
            return None
        alarm = {"datum": datum, "zeit": t.isoformat(timespec="seconds")}
        schreiben("checkin", {**d, "alarm": alarm})
    name = profil().get("name") or ""
    text = (f"Biko: {name or 'Sie'} hat sich heute seit {d['zeit']} Uhr nicht gemeldet (täglicher Check-in). "
            "Bitte ruf kurz an." if not str(profil().get("sprache")).startswith("zh")
            else f"Biko：{name or '她'}今天从{d['zeit']}起还没有回复（每日问候）。请打个电话问问。")
    try:
        bekommen = familie_sms(text, d.get("kontakte") or [])
        with _lock:
            schreiben("checkin", {**checkin_lesen(), "alarm": {**alarm, "geschickt": bekommen}})
        protokoll("Check-in: kein Lebenszeichen, Familie benachrichtigt")
        return bekommen
    except ValueError:
        protokoll("Check-in: kein Lebenszeichen, aber keine SMS möglich")
        return None


# ---------- Medikamente: Biko fragt nach, ob sie genommen sind ----------

MELDEN_NACH = 60       # Minuten nach der Uhrzeit: so lange wartet Biko auf "genommen", dann bekommt die Familie eine SMS
NACHFRAGE_NACH = 30    # Minuten: dann fragt die App noch einmal nach (logik.js)


def medikamente_lesen():
    """{"JJJJ-MM-TT": {Nummer der Erinnerung: {"genommen": Zeit, "gemeldet": [Namen], "entwarnt": Zeit}}}"""
    d = lesen("medikamente", {})
    return d if isinstance(d, dict) else {}


def medikament_heute(e, t):
    """Die Uhrzeit, zu der das Medikament heute dran ist, oder None, wenn heute keins dran ist."""
    if not e.get("medikament") or not e.get("aktiv", True):
        return None
    if e.get("datum") and e["datum"] != t.strftime("%Y-%m-%d"):
        return None
    if TAGE_REIHE[t.weekday()] not in e["tage"]:
        return None
    h, m = map(int, e["zeit"].split(":"))
    return t.replace(hour=h, minute=m, second=0, microsecond=0)


def medikament_stand(e, t):
    return medikamente_lesen().get(t.strftime("%Y-%m-%d"), {}).get(e["id"], {})


def medikament_text(e, t):
    """Für den Hinweis der App: was heute mit diesem Medikament ist."""
    if not e.get("medikament"):
        return ""
    teile = ["Medikament"]
    um = medikament_heute(e, t)
    stand = medikament_stand(e, t)
    if stand.get("genommen"):
        teile.append(f"heute genommen um {stand['genommen'][11:16]}")
    elif um and t >= um:
        teile.append("heute noch nicht bestätigt")
    elif um:
        teile.append("heute noch nicht dran")
    if e.get("melden"):
        wer = ", ".join(f"{k['name']} ({k['nummer']})" for k in e["melden"])
        teile.append(f"ohne Bestätigung nach {e.get('melden_nach', MELDEN_NACH)} Minuten SMS an {wer}"
                     + (", SMS ging heute schon hinaus" if stand.get("gemeldet") else ""))
    return " (" + "; ".join(teile) + ")"


def erinnerungen_app(liste=None):
    """Die Erinnerungen für die App: bei Medikamenten dazu, ob sie heute schon genommen sind (Uhrzeit oder None)."""
    t = jetzt()
    tag = medikamente_lesen().get(t.strftime("%Y-%m-%d"), {})
    return [{**e, "genommen": (tag.get(e["id"]) or {}).get("genommen")} if e.get("medikament") else e
            for e in (erinnerungen_lesen() if liste is None else liste)]


def _medikament_schreiben(datum, nr, stand):
    d = medikamente_lesen()
    d.setdefault(datum, {})[nr] = stand
    schreiben("medikamente", {k: d[k] for k in sorted(d)[-14:]})   # zwei Wochen reichen


def medikament_genommen(eingabe):
    """Die Person hat ihr Medikament genommen: im Gespräch (Werkzeug) oder mit dem Knopf "Genommen"."""
    nr = str(eingabe.get("id") or "")
    t = jetzt()
    datum = t.strftime("%Y-%m-%d")
    with _lock:
        e = next((x for x in erinnerungen_lesen() if x["id"] == nr and x.get("medikament")), None)
        if not e:
            raise ValueError("Unter dieser Nummer ist kein Medikament gespeichert. Die Nummern stehen im Hinweis.")
        stand = medikament_stand(e, t)
        if stand.get("genommen"):
            return f"Das war heute schon notiert, um {stand['genommen'][11:16]} Uhr. Nicht noch einmal nehmen lassen."
        entwarnen = bool(stand.get("gemeldet")) and not stand.get("entwarnt")
        stand = {**stand, "genommen": t.isoformat(timespec="seconds"),
                 **({"entwarnt": t.isoformat(timespec="seconds")} if entwarnen else {})}
        _medikament_schreiben(datum, nr, stand)
        eintrag = {"id": uuid.uuid4().hex[:6], "zeit": t.isoformat(timespec="seconds"), "art": "medikament",
                   "wert": f"{e['text']}"[:120], "notiz": f"genommen, Erinnerung um {e['zeit']}"}
        schreiben("gesundheit", (tagebuch_lesen() + [eintrag])[-MAX_TAGEBUCH:])
    if entwarnen:
        name = profil().get("name") or ""
        zh = str(profil().get("sprache")).startswith("zh")
        try:
            familie_sms(f"Biko：放心，{name or '她'}刚刚确认已经吃了药（{e['text']}）。" if zh
                        else f"Biko: Entwarnung, {name or 'sie'} hat {e['text']} jetzt genommen.", e["melden"])
        except ValueError:
            pass
    return f"Notiert: {e['text']} heute um {t.strftime('%H:%M')} genommen, steht auch im Gesundheitstagebuch."


def medikament_knopf(nr):
    """Der Knopf "Genommen" in der App. Liefert die Erinnerungen neu."""
    medikament_genommen({"id": nr})
    lebenszeichen()
    return erinnerungen_app()


def medikamente_pruefen(t=None):
    """Vom Hausmeister jede Minute: ist ein Medikament bis zur Frist nicht bestätigt, bekommt die Familie (einmal) eine SMS."""
    t = t or jetzt()
    datum = t.strftime("%Y-%m-%d")
    geschickt = []
    for e in erinnerungen_lesen():
        um = medikament_heute(e, t)
        if not um or not e.get("melden") or t < um + timedelta(minutes=e.get("melden_nach", MELDEN_NACH)):
            continue
        try:
            if datetime.fromisoformat(e.get("seit") or "") > um:   # erst nach der Uhrzeit eingestellt: ab morgen
                continue
        except ValueError:
            pass
        with _lock:
            stand = medikament_stand(e, t)
            if stand.get("genommen") or "gemeldet" in stand:
                continue
            _medikament_schreiben(datum, e["id"], {**stand, "gemeldet": []})   # nur ein Versuch am Tag
        name = profil().get("name") or ""
        text = (f"Biko：{name or '她'}今天{e['zeit']}的药（{e['text']}）还没有确认吃过。请打个电话问问。"
                if str(profil().get("sprache")).startswith("zh")
                else f"Biko: {name or 'Sie'} hat {e['text']} (um {e['zeit']} Uhr) heute noch nicht als genommen "
                     "bestätigt. Bitte ruf kurz an.")
        try:
            bekommen = familie_sms(text, e["melden"])
        except ValueError:
            protokoll("Medikament: nicht bestätigt, aber keine SMS möglich")
            continue
        with _lock:
            _medikament_schreiben(datum, e["id"], {**medikament_stand(e, t), "gemeldet": bekommen})
        protokoll("Medikament: nicht bestätigt, Familie benachrichtigt")
        geschickt += bekommen
    return geschickt


# ---------- Familienblick: die Familie sieht kurz, wie es der Person geht ----------
# Nie den Inhalt der Gespräche. Was die Familie außer dem Lebenszeichen sieht, entscheidet die Person im Gespräch
# (Werkzeug familie_freigabe). Das Gesundheitstagebuch ist erst sichtbar, wenn sie es ausdrücklich erlaubt.

FREIGABE_STANDARD = {"erinnerungen": True, "listen": True, "geburtstage": True, "gesundheit": False}
FREIGABE_NAMEN = {"erinnerungen": "Erinnerungen von heute", "listen": "Listen (z. B. Einkaufsliste)",
                  "geburtstage": "die nächsten Geburtstage", "gesundheit": "das Gesundheitstagebuch"}


def freigabe_lesen():
    d = lesen("freigabe", {})
    d = d if isinstance(d, dict) else {}
    return {k: bool(d.get(k, v)) for k, v in FREIGABE_STANDARD.items()}


def freigabe_text():
    f = freigabe_lesen()
    ja = [FREIGABE_NAMEN[k] for k, v in f.items() if v]
    return ("Familienblick (falls die Familie ihn benutzt): sie sieht, wann die Person zuletzt mit dir geredet hat und ob "
            "der Check-in heute erledigt ist, nie den Inhalt der Gespräche. Außerdem: "
            + (", ".join(ja) if ja else "nichts weiter") + ".")


def familie_freigabe(eingabe):
    neu = freigabe_lesen()
    for k in FREIGABE_STANDARD:
        if isinstance(eingabe.get(k), bool):
            neu[k] = eingabe[k]
    with _lock:
        schreiben("freigabe", neu)
    return freigabe_text() + " Sag ihr kurz, was die Familie jetzt sieht."


def erinnerungen_heute(t=None):
    t = t or jetzt()
    tag, datum = TAGE_REIHE[t.weekday()], t.strftime("%Y-%m-%d")
    liste = []
    for e in erinnerungen_lesen():
        if not e.get("aktiv", True) or not (e["datum"] == datum if e.get("datum") else tag in e.get("tage", [])):
            continue
        eintrag = {"zeit": e["zeit"], "text": e["text"]}
        if e.get("medikament"):   # bei Medikamenten: ob sie heute bestätigt sind
            genommen = medikament_stand(e, t).get("genommen")
            eintrag.update(medikament=True, genommen=genommen[11:16] if genommen else None,
                           faellig=e["zeit"] <= t.strftime("%H:%M"))
        liste.append(eintrag)
    return sorted(liste, key=lambda e: e["zeit"])


def familie_blick():
    """Was die Familie über die gerade gesetzte Person sieht."""
    t = jetzt()
    p, d, f = profil(), checkin_lesen(), freigabe_lesen()
    heute = t.strftime("%Y-%m-%d")
    alarm = d.get("alarm") or {}
    mal = sum(1 for g in gespraeche_lesen() for m in g.get("nachrichten", [])
              if m.get("von") == "ich" and str(m.get("zeit", "")).startswith(heute))
    blick = {
        "person": person_jetzt(), "name": p["name"], "sprache": p["sprache"],
        "zuletzt": d.get("zuletzt"), "heute_geredet": mal,
        "checkin": {"zeit": d.get("zeit"), "gemeldet": gemeldet_heute(t),
                    "alarm": alarm.get("datum") == heute, "entwarnt": bool(alarm.get("entwarnt"))
                    if alarm.get("datum") == heute else False,
                    "kontakte": [k["name"] for k in d.get("kontakte") or []]},
        "freigabe": f,
    }
    if f["erinnerungen"]:
        blick["erinnerungen"] = erinnerungen_heute(t)
    if f["listen"]:
        blick["listen"] = {name: [e["text"] for e in eintraege] for name, eintraege in listen_lesen().items() if eintraege}
    if f["geburtstage"]:
        geb = sorted((geburtstag_naechster(g, t.date()) + (g,) for g in geburtstage_lesen()), key=lambda x: x[0])[:3]
        blick["geburtstage"] = [{"name": g["name"], "tag": g["tag"], "monat": g["monat"], "in_tagen": tage,
                                 "alter": alter} for tage, alter, g in geb]
    if f["gesundheit"]:
        seit = (t - timedelta(days=14)).isoformat(timespec="seconds")
        blick["gesundheit"] = [{"zeit": e["zeit"], "art": TAGEBUCH_ARTEN[e["art"]], "wert": e["wert"],
                                "notiz": e.get("notiz") or ""} for e in tagebuch_lesen() if e["zeit"] >= seit][-30:]
    return blick


def kosten_monat():
    """KI-Kosten der gerade gesetzten Person in diesem Monat (Dollar) und Zahl der Antworten."""
    monat = jetzt().strftime("%Y-%m")
    tage = [v for k, v in lesen("kosten", {}).items() if k.startswith(monat)]
    return {"dollar": round(sum(v.get("ki", 0) for v in tage), 2), "antworten": sum(v.get("antworten", 0) for v in tage),
            "zeichen": sum(v.get("zeichen", 0) for v in tage)}


# ---------- Geburtstage: Biko denkt rechtzeitig daran ----------

MAX_GEBURTSTAGE = 200


def geburtstage_lesen():
    """[{"id", "name", "tag", "monat", "jahr" (oder None)}]."""
    daten = lesen("geburtstage", [])
    return daten if isinstance(daten, list) else []


def geburtstag_naechster(g, heute):
    """(Tage bis zum nächsten Geburtstag, Alter an dem Tag oder None). Wer am 29.2. Geburtstag hat, feiert sonst am 28.2."""
    def am(jahr):
        schalt = jahr % 4 == 0 and (jahr % 100 != 0 or jahr % 400 == 0)
        return date(jahr, g["monat"], 28 if (g["monat"], g["tag"]) == (2, 29) and not schalt else g["tag"])
    d = am(heute.year)
    if d < heute:
        d = am(heute.year + 1)
    return (d - heute).days, (d.year - g["jahr"] if g.get("jahr") else None)


def geburtstag_merken(eingabe):
    name = " ".join(str(eingabe.get("name") or "").split())[:60]
    if not name:
        raise ValueError("Wessen Geburtstag? Der Name fehlt.")
    try:
        tag, monat = int(eingabe.get("tag")), int(eingabe.get("monat"))
        date(2000, monat, tag)   # 2000 war ein Schaltjahr, der 29.2. geht also
    except (TypeError, ValueError):
        raise ValueError("Das Datum stimmt nicht. Frag nach Tag und Monat.")
    jahr = eingabe.get("jahr")
    try:
        jahr = int(jahr) if jahr not in (None, "", 0) else None
    except (TypeError, ValueError):
        jahr = None
    if jahr and not 1900 <= jahr <= jetzt().year:
        jahr = None
    g = {"id": uuid.uuid4().hex[:6], "name": name, "tag": tag, "monat": monat, "jahr": jahr}
    with _lock:
        alt = [x for x in geburtstage_lesen() if x["name"].casefold() != name.casefold()]
        if len(alt) >= MAX_GEBURTSTAGE:
            raise ValueError(f"Es sind schon {MAX_GEBURTSTAGE} Geburtstage. Streich erst einen.")
        schreiben("geburtstage", alt + [g])
    tage, alter = geburtstag_naechster(g, jetzt().date())
    return (f"Gemerkt: {name} hat am {tag}.{monat}. Geburtstag"
            + (f", in {tage} Tagen" if tage > 1 else ", morgen" if tage == 1 else ", heute")
            + (f" wird {name} {alter}." if alter else "."))


def geburtstag_streichen(eingabe):
    name = " ".join(str(eingabe.get("name") or "").split()).casefold()
    with _lock:
        liste = geburtstage_lesen()
        rest = [g for g in liste if g["name"].casefold() != name]
        if len(rest) == len(liste):
            raise ValueError("Diesen Geburtstag kenne ich nicht. Schau im Hinweis, wie der Name dort steht.")
        schreiben("geburtstage", rest)
    return "Gestrichen."


# ---------- Morgenrunde: Biko meldet sich jeden Morgen von selbst ----------

MORGEN_VORHER = 15 * 60   # so viele Sekunden vor der Uhrzeit bereitet Biko die Morgenrunde vor
MORGEN_NACHHER = 2 * 3600  # war der Server so lange weg, holt er sie noch nach, danach erst morgen wieder
_morgen_lock = threading.Lock()

MORGENRUNDE = """<app>
Es ist Zeit für deine Morgenrunde. Schreib, was du der Person gleich von selbst sagst, so wie man es vorliest:
- eine herzliche Begrüßung (mit Namen, wenn du ihn kennst),
- das Wetter in Wien heute in einem Satz (such kurz danach),
- zwei oder drei kurze Nachrichten von heute, die sie interessieren (siehe was du über sie weißt; sonst das Wichtigste
  aus Wien und Österreich, nichts Grausiges), jede in einem Satz, ohne Links,
- ihre Erinnerungen für heute, falls es welche gibt,
- wer heute oder morgen Geburtstag hat, falls jemand, mit dem Angebot, einen Glückwunsch zu schreiben,
- zum Schluss eine Frage, über die ihr reden könnt.
Insgesamt 5 bis 8 kurze Sätze, keine Listen, keine Überschriften, in ihrer Sprache.
</app>"""


def morgenrunde_zeit():
    return lesen("morgenrunde", {}).get("zeit")


def morgenrunde_einstellen(eingabe):
    zeit = str(eingabe.get("zeit") or "").strip().lower()
    if zeit in ("aus", "off", "nein", ""):
        with _lock:
            schreiben("morgenrunde", {**lesen("morgenrunde", {}), "zeit": None})
        return "Die Morgenrunde ist abgestellt."
    if not UHRZEIT.match(zeit):
        raise ValueError("Bitte die Uhrzeit als HH:MM angeben, z. B. 08:00, oder 'aus'.")
    with _lock:   # `seit`: eine Uhrzeit, die heute schon vorbei ist, gilt erst ab morgen
        schreiben("morgenrunde", {**lesen("morgenrunde", {}), "zeit": zeit, "seit": jetzt().isoformat(timespec="seconds")})
    return f"Eingestellt: jeden Tag um {zeit} Uhr. Die erste Morgenrunde kommt beim nächsten Mal um {zeit}."


def morgenrunde_faellig(t=None):
    """Ist heute die Zeit für die Vorbereitung gekommen? Liefert (datum, zeit) oder None."""
    daten = lesen("morgenrunde", {})
    zeit = daten.get("zeit")
    if not zeit:
        return None
    t = t or jetzt()
    h, m = map(int, zeit.split(":"))
    um = t.replace(hour=h, minute=m, second=0, microsecond=0)
    if not -MORGEN_NACHHER <= (um - t).total_seconds() <= MORGEN_VORHER:
        return None
    try:
        seit = datetime.fromisoformat(daten.get("seit") or "")
    except ValueError:
        seit = None
    if seit and seit > um:   # eingestellt, als die Zeit heute schon vorbei war
        return None
    return t.strftime("%Y-%m-%d"), zeit


def morgenrunde_heute(erzeugen=False):
    """Die Morgenrunde von heute ({"datum", "zeit", "text", "gespraech"}) oder None. Mit `erzeugen` schreibt Biko sie,
    wenn sie fällig ist und noch fehlt (dauert ein paar Sekunden, weil er nach Wetter und Nachrichten sucht)."""
    heute = jetzt().strftime("%Y-%m-%d")
    fertig = lesen("morgenrunde", {}).get("heute")
    if fertig and fertig.get("datum") == heute:
        return fertig
    if not erzeugen or not morgenrunde_faellig():
        return None
    with _morgen_lock:   # nur einmal schreiben, auch wenn zwei Anfragen gleichzeitig kommen
        fertig = lesen("morgenrunde", {}).get("heute")
        if fertig and fertig.get("datum") == heute:
            return fertig
        try:
            text = frage_claude(system_prompt(), [{"role": "user", "content": [
                {"type": "text", "text": hinweis()}, {"type": "text", "text": MORGENRUNDE}]}],
                websuche=True, modell=EINFACH_MODELL)
        except RuntimeError as e:
            protokoll(f"Morgenrunde ging nicht: {e}")
            name = profil()["name"].strip()
            text = f"Guten Morgen{', ' + name if name else ''}! Ich bin da, wenn du mich brauchst."
        zeit = jetzt().isoformat(timespec="seconds")
        with _lock:
            g = gespraech_neu([{"von": "biko", "text": text, "zeit": zeit, "vonselbst": "morgenrunde"}])
            g["titel"] = "早安" if profil()["sprache"].startswith("zh") else "Morgenrunde"
            schreiben("gespraeche", ([g] + gespraeche_lesen())[:MAX_GESPRAECHE])
            fertig = {"datum": heute, "zeit": morgenrunde_zeit(), "text": text, "gespraech": g["id"]}
            schreiben("morgenrunde", {**lesen("morgenrunde", {}), "heute": fertig})
        protokoll("Morgenrunde für heute ist fertig.")
        return fertig


def hausmeister():
    """Läuft im Hintergrund: bereitet die Morgenrunde vor, schaut nach dem Check-in und nach den Medikamenten."""
    while True:
        hausmeister_runde()
        time.sleep(60)


def hausmeister_runde():
    """Einmal bei jeder Person vorbeischauen."""
    try:
        personen = personen_lesen()
    except Exception as e:
        protokoll(f"Hausmeister-Fehler: {type(e).__name__}")
        return
    for p in personen:
        person_setzen(p["id"])
        try:
            morgenrunde_heute(erzeugen=True)
        except Exception as e:   # der Hausmeister darf nie stehen bleiben
            protokoll(f"Hausmeister-Fehler: {type(e).__name__}")
        try:
            checkin_pruefen()
        except Exception as e:
            protokoll(f"Hausmeister-Fehler beim Check-in: {type(e).__name__}")
        try:
            medikamente_pruefen()
        except Exception as e:
            protokoll(f"Hausmeister-Fehler bei den Medikamenten: {type(e).__name__}")
    person_setzen(None)


WERKZEUGE = {
    "checkin_einstellen": {"tun": checkin_einstellen, "schema": {
        "name": "checkin_einstellen",
        "description": "Stellt den täglichen Check-in ein (oder aus): Biko fragt zur Uhrzeit nach, ob alles gut ist; ohne "
                       "Lebenszeichen bis zur Frist bekommen die Kontakte eine SMS.",
        "input_schema": {
            "type": "object",
            "properties": {
                "zeit": {"type": "string", "description": "Uhrzeit HH:MM, z. B. '10:00', oder 'aus'."},
                "stunden": {"type": "integer", "description": "Nach wie vielen Stunden ohne Lebenszeichen, Standard 2."},
                "kontakte": {"type": "array", "description": "Wer die SMS bekommt, höchstens 3.", "items": {
                    "type": "object",
                    "properties": {"name": {"type": "string"}, "nummer": {"type": "string"}},
                    "required": ["name", "nummer"]}},
            },
            "required": ["zeit"],
        },
    }},
    "familie_benachrichtigen": {"tun": familie_benachrichtigen, "schema": {
        "name": "familie_benachrichtigen",
        "description": "Schickt den Kontakten des Check-ins sofort eine SMS, z. B. im Notfall. Nur wenn die Person es will "
                       "oder eindeutig um Hilfe bittet.",
        "input_schema": {
            "type": "object",
            "properties": {"text": {"type": "string", "description": "Kurz und klar, z. B. 'Ich bin in der Küche gestürzt "
                                                                     "und komme nicht auf. Die Rettung ist verständigt.'"}},
            "required": ["text"],
        },
    }},
    "familie_freigabe": {"tun": familie_freigabe, "schema": {
        "name": "familie_freigabe",
        "description": "Stellt ein, was die Familie im Familienblick sieht (außer dem Lebenszeichen). Nur wenn die Person "
                       "es selbst sagt, z. B. 'Meine Tochter darf meinen Blutdruck sehen' oder 'Die Familie soll meine "
                       "Einkaufsliste nicht sehen'. Nur die Teile angeben, die sich ändern.",
        "input_schema": {
            "type": "object",
            "properties": {
                "erinnerungen": {"type": "boolean", "description": "Die Erinnerungen von heute (z. B. Tabletten)."},
                "listen": {"type": "boolean", "description": "Die Listen, z. B. die Einkaufsliste."},
                "geburtstage": {"type": "boolean", "description": "Die nächsten Geburtstage."},
                "gesundheit": {"type": "boolean", "description": "Das Gesundheitstagebuch der letzten zwei Wochen."},
            },
        },
    }},
    "dolmetscher": {"tun": dolmetscher, "schema": {
        "name": "dolmetscher",
        "description": "Schaltet den Dolmetscher ein oder aus. An: du übersetzt jeden Satz in die andere Sprache, bis "
                       "die Person fertig sagt.",
        "input_schema": {
            "type": "object",
            "properties": {
                "an": {"type": "boolean"},
                "sprache_a": {"type": "string", "description": "Die Sprache der Person, z. B. 'Chinesisch'."},
                "sprache_b": {"type": "string", "description": "Die Sprache der anderen, z. B. 'Deutsch'."},
            },
            "required": ["an"],
        },
    }},
    "geburtstag_merken": {"tun": geburtstag_merken, "schema": {
        "name": "geburtstag_merken",
        "description": "Merkt sich einen Geburtstag. Gibt es den Namen schon, wird das Datum ersetzt.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Wer, so wie die Person ihn nennt, z. B. 'Peter' oder 'Enkelin Lea'. "
                                                         "Ihr eigener Geburtstag: 'ich'."},
                "tag": {"type": "integer", "description": "Tag, 1 bis 31."},
                "monat": {"type": "integer", "description": "Monat, 1 bis 12."},
                "jahr": {"type": "integer", "description": "Geburtsjahr, nur wenn sie es sagt."},
            },
            "required": ["name", "tag", "monat"],
        },
    }},
    "geburtstag_streichen": {"tun": geburtstag_streichen, "schema": {
        "name": "geburtstag_streichen",
        "description": "Streicht einen Geburtstag. Der Name so, wie er im Hinweis steht.",
        "input_schema": {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        },
    }},
    "gesundheit_notieren": {"tun": gesundheit_notieren, "schema": {
        "name": "gesundheit_notieren",
        "description": "Schreibt einen Messwert oder wie es der Person geht ins Gesundheitstagebuch (mit Datum und Uhrzeit).",
        "input_schema": {
            "type": "object",
            "properties": {
                "art": {"type": "string", "enum": list(TAGEBUCH_ARTEN)},
                "wert": {"type": "string", "description": "Der Wert, z. B. '135/85', '112 mg/dl', '72', '68 kg', "
                                                         "'schwindlig', 'Knie tut weh', 'Herztablette genommen'."},
                "notiz": {"type": "string", "description": "Kurz dazu, falls sie etwas sagt, z. B. 'nach dem Frühstück'."},
            },
            "required": ["art", "wert"],
        },
    }},
    "gesundheit_streichen": {"tun": gesundheit_streichen, "schema": {
        "name": "gesundheit_streichen",
        "description": "Streicht einen falsch notierten Eintrag aus dem Gesundheitstagebuch. Die Nummer steht im Hinweis.",
        "input_schema": {
            "type": "object",
            "properties": {"id": {"type": "string", "description": "Nummer des Eintrags."}},
            "required": ["id"],
        },
    }},
    "liste_aendern": {"tun": liste_aendern, "schema": {
        "name": "liste_aendern",
        "description": "Schreibt Dinge auf eine Liste der Person (Einkaufen, Notizen, ...) oder nimmt sie weg. "
                       "Eine neue Liste entsteht von selbst, eine leere verschwindet.",
        "input_schema": {
            "type": "object",
            "properties": {
                "liste": {"type": "string", "description": "Name der Liste, z. B. 'Einkaufen' oder 'Notizen'."},
                "dazu": {"type": "array", "items": {"type": "string"},
                         "description": "Was dazukommt, je ein kurzer Eintrag, z. B. ['Milch', '6 Eier']."},
                "weg": {"type": "array", "items": {"type": "string"},
                        "description": "Was weg soll, so wie es auf der Liste steht."},
                "leeren": {"type": "boolean", "description": "true: alles von der Liste nehmen."},
            },
            "required": ["liste"],
        },
    }},
    "morgenrunde_einstellen": {"tun": morgenrunde_einstellen, "schema": {
        "name": "morgenrunde_einstellen",
        "description": "Stellt ein, um wie viel Uhr du dich jeden Morgen von selbst meldest (Wetter, Nachrichten, "
                       "Termine des Tages), oder stellt es ab.",
        "input_schema": {
            "type": "object",
            "properties": {"zeit": {"type": "string", "description": "Uhrzeit HH:MM, z. B. 08:00, oder 'aus'."}},
            "required": ["zeit"],
        },
    }},
    "wissen_merken": {"tun": wissen_merken, "schema": {
        "name": "wissen_merken",
        "description": "Schreibt etwas Bleibendes über die Person auf (Gesundheit, Diät, Familie, Vorlieben). "
                       "Du weißt es dann in allen künftigen Gesprächen.",
        "input_schema": {
            "type": "object",
            "properties": {"text": {"type": "string", "description": "Ein kurzer Satz in der Sprache der Person, "
                                                                    "z. B. 'Darf wegen Diabetes wenig Zucker essen'."}},
            "required": ["text"],
        },
    }},
    "wissen_vergessen": {"tun": wissen_vergessen, "schema": {
        "name": "wissen_vergessen",
        "description": "Streicht einen Eintrag aus deinem Wissen über die Person. Die Nummer steht in deiner Liste.",
        "input_schema": {
            "type": "object",
            "properties": {"id": {"type": "string", "description": "Nummer des Eintrags aus der Liste."}},
            "required": ["id"],
        },
    }},
    "erinnerung_merken": {"tun": erinnerung_merken, "schema": {
        "name": "erinnerung_merken",
        "description": "Schreibt eine Erinnerung auf. Die App meldet sich dann zur Uhrzeit groß mit Ton. "
                       "Für einmalige Erinnerungen `datum` setzen, für regelmäßige `tage` (weglassen heißt jeden Tag).",
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Woran erinnert wird, kurz und in der Sprache der Person, z. B. 'Blutdrucktablette nehmen'."},
                "zeit": {"type": "string", "description": "Uhrzeit im 24-Stunden-Format HH:MM, z. B. 08:00."},
                "datum": {"type": "string", "description": "Nur für einmalige Erinnerungen: der Tag als JJJJ-MM-TT."},
                "tage": {"type": "array", "items": {"type": "string", "enum": TAGE_REIHE},
                         "description": "Nur für regelmäßige Erinnerungen an bestimmten Wochentagen."},
                "medikament": {"type": "boolean", "description": "true bei Tabletten, Tropfen, Spritzen, Inhalieren: "
                               "dann fragt Biko nach, ob es genommen wurde."},
                "familie": {"type": "boolean", "description": "Nur bei Medikamenten: true, wenn die Familie eine SMS "
                            "bekommen soll, falls es nicht bestätigt wird."},
                "kontakte": {"type": "array", "description": "Wer die SMS bekommt, höchstens 3. Weggelassen: die vom Check-in.",
                             "items": {"type": "object",
                                       "properties": {"name": {"type": "string"}, "nummer": {"type": "string"}},
                                       "required": ["name", "nummer"]}},
                "melden_nach": {"type": "integer", "description": "Minuten nach der Uhrzeit bis zur SMS, Standard 60."},
            },
            "required": ["text", "zeit"],
        },
    }},
    "medikament_genommen": {"tun": medikament_genommen, "schema": {
        "name": "medikament_genommen",
        "description": "Bestätigt, dass die Person ihr Medikament von heute genommen hat (schreibt es auch ins "
                       "Gesundheitstagebuch). Die Nummer der Medikament-Erinnerung steht im Hinweis.",
        "input_schema": {
            "type": "object",
            "properties": {"id": {"type": "string", "description": "Nummer der Erinnerung."}},
            "required": ["id"],
        },
    }},
    "erinnerung_loeschen": {"tun": erinnerung_loeschen, "schema": {
        "name": "erinnerung_loeschen",
        "description": "Streicht eine gemerkte Erinnerung. Die Nummer steht in deiner Liste der Erinnerungen.",
        "input_schema": {
            "type": "object",
            "properties": {"id": {"type": "string", "description": "Nummer der Erinnerung aus der Liste."}},
            "required": ["id"],
        },
    }},
}


# ---------- HTTP ----------

# Ein Cookie sagt, wer da ist: 2.<rolle>.<person>.<version>.<zeit>.<signatur>
#   verwalter  mit dem Passwort angemeldet (Niko): sieht alle Personen, legt neue an, kann Biko als jede Person öffnen
#   person     mit ihrem Code angemeldet: redet mit Biko, sieht nur die eigenen Daten
#   familie    mit dem Familiencode angemeldet: sieht nur den Familienblick ihrer Person
# Alte Cookies (<zeit>.<signatur>, von vor den Konten) gelten als Verwalter bei der ersten Person.

def _signatur(text):
    return hmac.new(geheimnis().encode(), text.encode(), hashlib.sha256).hexdigest()


def cookie_wert(rolle="verwalter", pid=None, version=0):
    pid = pid or erste_person()
    text = f"2.{rolle}.{pid}.{version}.{int(time.time())}"
    return f"{text}.{_signatur(text)}"


def sitzung_aus(wert):
    """{"rolle", "person"} zu einem gültigen Cookie, sonst None."""
    try:
        teile = str(wert).split(".")
        if len(teile) == 2:   # altes Cookie
            zeit, sig = teile
            if hmac.compare_digest(sig, _signatur(zeit)) and time.time() - int(zeit) < COOKIE_TAGE * 86400:
                return {"rolle": "verwalter", "person": erste_person()}
            return None
        if len(teile) != 6 or teile[0] != "2":
            return None
        _, rolle, pid, version, zeit, sig = teile
        if not hmac.compare_digest(sig, _signatur(".".join(teile[:5]))):
            return None
        if time.time() - int(zeit) >= COOKIE_TAGE * 86400 or rolle not in ("verwalter",) + ROLLEN:
            return None
        p = person_finden(pid)
        if not p:
            return None
        if rolle != "verwalter" and int(version) != p.get("version", 1):
            return None   # die Geräte dieser Person wurden abgemeldet
        return {"rolle": rolle, "person": pid}
    except (ValueError, AttributeError, TypeError):
        return None


def cookie_ok(wert):
    return sitzung_aus(wert) is not None


# Fehlermeldungen auf Chinesisch (die App schickt X-Sprache: zh-CN)
ZH = {
    "Der Schlüssel für die KI fehlt oder stimmt nicht. Bitte Niko Bescheid geben.": "AI 密钥缺失或不正确。请告诉 Niko。",
    "Gerade sind zu viele Anfragen. Bitte in einer Minute nochmal probieren.": "现在请求太多了。请一分钟后再试。",
    "Biko kann gerade nicht antworten. Bitte gleich nochmal probieren.": "Biko 现在无法回答。请稍后再试。",
    "Keine Verbindung zur KI. Ist das Internet am Server da?": "无法连接到 AI。服务器有网络吗？",
    "Bitte Uhrzeit (z. B. 08:00) und einen Text angeben.": "请填写时间（例如 08:00）和内容。",
    "Zu viel Text auf einmal.": "一次文字太多了。",
    "Das hat nicht geklappt, bitte nochmal.": "没有成功，请再试一次。",
    "Bitte anmelden.": "请先登录。",
    "Gibt es nicht.": "不存在。",
    "Bitte etwas Kürzeres schreiben.": "请写短一点。",
    "Höchstens 30 Erinnerungen.": "最多 30 个提醒。",
    "Zu viele Versuche. Bitte in 15 Minuten nochmal.": "尝试次数太多。请 15 分钟后再试。",
    "Am Server ist noch kein Passwort eingestellt (APP_PASSWORT).": "服务器还没有设置密码（APP_PASSWORT）。",
    "Das Passwort oder der Code stimmt nicht.": "密码或邀请码不对。",
    "Das ist nur für die Person selbst.": "这个只有本人可以用。",
    "Das ist nur für den Verwalter.": "这个只有管理员可以用。",
    "Bitte einen Namen angeben.": "请填写名字。",
    "Der Sprachdienst ist nicht eingerichtet.": "语音服务还没有设置好。",
    "Der Schlüssel für die Stimme fehlt, stimmt nicht oder das Guthaben ist aufgebraucht. Bitte Niko Bescheid geben.":
        "语音服务的密钥缺失、不正确，或者余额用完了。请告诉 Niko。",
    "Die Stimme geht gerade nicht. Bitte gleich nochmal probieren.": "语音现在用不了。请稍后再试。",
    "Der Sprachdienst ist gerade nicht erreichbar.": "现在连不上语音服务。",
    "Die Aufnahme ist zu lang. Bitte kürzer sprechen.": "录音太长了。请说短一点。",
}

TYPEN = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
         ".css": "text/css; charset=utf-8", ".svg": "image/svg+xml",
         ".webmanifest": "application/manifest+json", ".png": "image/png", ".woff2": "font/woff2",
         ".mp3": "audio/mpeg"}

_fehlversuche = {}


class Handler(BaseHTTPRequestHandler):
    server_version = "Biko"
    sys_version = ""

    def log_message(self, fmt, *args):
        # Keine Inhalte loggen (Privatsphäre), nur Methode, Pfad und Status
        if "/api/" in self.path:
            print(f"{self.command} {self.path.split('?')[0]} {args[1] if len(args) > 1 else ''}", flush=True)

    # --- Helfer ---
    def uebersetzt(self, daten):
        """Fehlermeldungen auf Chinesisch, wenn die App so eingestellt ist."""
        if isinstance(daten, dict) and "fehler" in daten and (self.headers.get("X-Sprache") or "").startswith("zh"):
            return {**daten, "fehler": ZH.get(daten["fehler"], daten["fehler"])}
        return daten

    def senden(self, status, daten=None, typ="application/json; charset=utf-8", extra=None):
        daten = self.uebersetzt(daten)
        body = daten if isinstance(daten, bytes) else json.dumps(daten, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", typ)
        self.send_header("Content-Length", str(len(body)))
        self.kopf_ende(typ, extra)
        self.wfile.write(body)

    def strom_beginnen(self, typ):
        """Eine Antwort ohne bekannte Länge: sie geht Stück für Stück hinaus, am Ende schließt die Verbindung."""
        self.send_response(200)
        self.send_header("Content-Type", typ)
        self.send_header("X-Accel-Buffering", "no")   # Proxys sollen nichts sammeln, jedes Stück geht gleich weiter
        self.close_connection = True
        self.kopf_ende(typ)

    def strom_schreiben(self, stueck):
        """Schreibt ein Stück. Ist die App schon weg (aufgelegt, Netz weg), passiert einfach nichts mehr."""
        if getattr(self, "_weg", False):
            return False
        try:
            self.wfile.write(stueck)
            self.wfile.flush()
            return True
        except OSError:
            self._weg = True
            return False

    def kopf_ende(self, typ, extra=None):
        if typ.startswith("application/json") or self.path.startswith("/api/"):
            cache = "no-store"   # Antworten und vorgelesener Ton werden nirgends zwischengespeichert
        elif typ == "font/woff2":
            cache = "public, max-age=31536000, immutable"  # Schriften ändern sich nie
        else:
            cache = "no-cache"
        self.send_header("Cache-Control", cache)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Content-Security-Policy",
                         "default-src 'self'; img-src 'self' data: blob:; style-src 'self'; script-src 'self'; "
                         f"connect-src 'self' {LIVE_ADRESSE}; media-src 'self' blob:; frame-ancestors 'none'; base-uri 'none'; "
                         "form-action 'self'")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()

    def json_body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n > 20000:
            raise ValueError("Zu viel Text auf einmal.")
        try:
            daten = json.loads(self.rfile.read(n) or b"{}")
        except ValueError:
            raise ValueError("Das hat nicht geklappt, bitte nochmal.")
        if not isinstance(daten, dict):
            raise ValueError("Das hat nicht geklappt, bitte nochmal.")
        return daten

    def angemeldet(self):
        """Die Sitzung ({"rolle", "person"}) oder None. Setzt auch, wessen Daten diese Anfrage liest und schreibt."""
        if hasattr(self, "_sitzung"):
            return self._sitzung
        self._sitzung = None
        for teil in (self.headers.get("Cookie") or "").split(";"):
            k, _, v = teil.strip().partition("=")
            if k == COOKIE:
                self._sitzung = sitzung_aus(v)
                if self._sitzung:
                    break
        if self._sitzung:
            person_setzen(self._sitzung["person"])
            # Der Verwalter zu Besuch bei einer anderen Person zählt nicht als ihr Lebenszeichen
            _faden.besuch = self._sitzung["rolle"] == "verwalter" and self._sitzung["person"] != erste_person()
        return self._sitzung

    def neu_anfangen(self):
        """Am Anfang jeder Anfrage: noch niemand angemeldet (eine Verbindung kann mehrere Anfragen tragen)."""
        self.__dict__.pop("_sitzung", None)
        person_setzen(None)
        _faden.besuch = False

    def darf(self, pfad):
        """None, wenn die Rolle diesen Weg benutzen darf, sonst die Antwort (401 oder 403)."""
        s = self.angemeldet()
        if not s:
            return 401, {"fehler": "Bitte anmelden."}
        if s["rolle"] == "familie" and pfad not in ("/api/familie", "/api/abmelden"):
            return 403, {"fehler": "Das ist nur für die Person selbst."}
        if s["rolle"] != "verwalter" and pfad.startswith("/api/verwaltung"):
            return 403, {"fehler": "Das ist nur für den Verwalter."}
        return None

    def cookie_setzen(self, wert, tage=COOKIE_TAGE):
        sicher = "; Secure" if self.headers.get("X-Forwarded-Proto") == "https" else ""
        return {"Set-Cookie": f"{COOKIE}={wert}; Max-Age={tage * 86400}; Path=/; HttpOnly; SameSite=Strict{sicher}"}

    def ip(self):
        # Letzter Eintrag: den setzt der eigene Proxy (Tailscale), frühere kann ein Angreifer fälschen
        return self.headers.get("X-Forwarded-For", self.client_address[0]).split(",")[-1].strip()

    # --- Routen ---
    def do_GET(self):
        self.neu_anfangen()
        pfad = self.path.split("?")[0]
        if pfad == "/api/status":
            s = self.angemeldet()
            return self.senden(200, {"angemeldet": bool(s), "rolle": s["rolle"] if s else None,
                                     "name": profil()["name"] if s else None, "passwort_gesetzt": bool(PASSWORT),
                                     "sprachdienst": bool(SPRACH_KEY)})
        if pfad.startswith("/api/"):
            nein = self.darf(pfad)
            if nein:
                return self.senden(*nein)
            if pfad == "/api/familie":
                return self.senden(200, self.familie_uebersicht())
            if pfad == "/api/profil":
                return self.senden(200, profil())
            if pfad == "/api/erinnerungen":
                return self.senden(200, erinnerungen_app())
            if pfad == "/api/wissen":
                return self.senden(200, wissen_lesen())
            if pfad == "/api/listen":
                return self.senden(200, listen_lesen())
            if pfad == "/api/geburtstage":
                return self.senden(200, geburtstage_lesen())
            if pfad == "/api/dolmetscher":
                return self.senden(200, {"dolmetscher": dolmetscher_jetzt()})
            if pfad == "/api/checkin":
                return self.senden(200, {"zeit": checkin_lesen().get("zeit"), "gemeldet": gemeldet_heute()})
            if pfad == "/api/morgenrunde":
                # ?jetzt: ist sie fällig und noch nicht fertig, schreibt Biko sie gleich (sonst macht das der Hausmeister)
                return self.senden(200, {"zeit": morgenrunde_zeit(), "heute": morgenrunde_heute(erzeugen="jetzt" in parse_qs(urlparse(self.path).query, keep_blank_values=True))})
            if pfad == "/api/gespraeche":
                with _lock:
                    return self.senden(200, [uebersicht(g) for g in gespraeche_lesen()])
            if pfad == "/api/gespraech":
                nr = (parse_qs(urlparse(self.path).query).get("id") or [""])[0]
                with _lock:
                    g = gespraech_finden(gespraeche_lesen(), nr)
                return self.senden(200, g) if g else self.senden(404, {"fehler": "Gibt es nicht."})
            return self.senden(404, {"fehler": "Gibt es nicht."})
        return self.datei(pfad)

    def do_POST(self):
        self.neu_anfangen()
        pfad = self.path.split("?")[0]
        try:
            if pfad == "/api/zuhoeren":
                return self.zuhoeren()
            if pfad == "/api/bildschirm":
                return self.bildschirm()
            daten = self.json_body()
            if pfad == "/api/login":
                return self.login(daten)
            nein = self.darf(pfad)
            if nein:
                return self.senden(*nein)
            if pfad == "/api/abmelden":
                return self.senden(200, {"ok": True}, extra=self.cookie_setzen("", tage=0))
            if pfad.startswith("/api/verwaltung/"):
                return self.verwaltung(pfad, daten)
            if pfad == "/api/chat":
                text = str(daten.get("text", "")).strip()
                if not text or len(text) > MAX_TEXT:
                    raise ValueError("Bitte etwas Kürzeres schreiben.")
                nr, gesprochen = str(daten.get("gespraech") or ""), daten.get("gesprochen") is True
                if daten.get("strom") is True:
                    return self.chat_strom(text, nr, gesprochen)
                return self.senden(200, chat(text, nr, gesprochen=gesprochen))
            if pfad == "/api/stimme":
                text = str(daten.get("text", "")).strip()
                if not text:
                    raise ValueError("Das hat nicht geklappt, bitte nochmal.")
                return self.stimme_strom(ton_strom(text, str(daten.get("vorher") or "")))
            if pfad == "/api/live-zugang":
                return self.senden(200, live_zugang())
            if pfad == "/api/vorlesen":
                text = str(daten.get("text", "")).strip()
                if not text:
                    raise ValueError("Das hat nicht geklappt, bitte nochmal.")
                return self.senden(200, ton_holen(text), "audio/mpeg")
            if pfad == "/api/gespraech/loeschen":
                with _lock:
                    rest = [g for g in gespraeche_lesen() if g["id"] != str(daten.get("id") or "")]
                    schreiben("gespraeche", rest)
                return self.senden(200, [uebersicht(g) for g in rest])
            if pfad == "/api/verlauf/loeschen":
                with _lock:
                    schreiben("gespraeche", [])
                    _pfad("verlauf").unlink(missing_ok=True)
                return self.senden(200, {"ok": True})
            if pfad == "/api/liste/weg":
                return self.senden(200, liste_wegtippen(str(daten.get("liste") or ""), str(daten.get("id") or "")))
            if pfad == "/api/messung":   # nur Zahlen: wie lange es beim Reden bis zur Antwort gedauert hat
                teile = {k: daten.get(k) for k in ("gesamt", "pause", "ki", "satz", "stimme")}
                if all(isinstance(v, (int, float)) and 0 <= v < 120000 for v in teile.values()):
                    protokoll("Reden: Biko spricht {gesamt:.0f} ms nach deinem Satz (Pause {pause:.0f}, erste Worte "
                              "{ki:.0f}, erster Satz {satz:.0f}, Stimme {stimme:.0f}), dazu die Stille, bis der "
                              "Sprachdienst den Satz für fertig hält".format(**teile))
                return self.senden(200, {"ok": True})
            if pfad == "/api/lebenszeichen":   # die App wurde geöffnet: die Person ist da
                lebenszeichen()
                return self.senden(200, {"gemeldet": True})
            if pfad == "/api/wissen/loeschen":
                try:
                    wissen_vergessen(daten)
                except ValueError:
                    pass   # schon weg, zum Beispiel auf einem zweiten Handy gelöscht
                return self.senden(200, wissen_lesen())
            if pfad == "/api/profil":
                wissen_lesen()   # alte Felder Diät und Notizen vorher übernehmen, sonst gingen sie hier verloren
                neu = {k: str(daten.get(k, "")).strip()[:1500] for k in STANDARD_PROFIL}
                neu["anrede"] = "Sie" if neu["anrede"] == "Sie" else "du"
                neu["sprache"] = neu["sprache"] if neu["sprache"] in SPRACHEN else "de-AT"
                with _lock:
                    schreiben("profil", neu)
                return self.senden(200, neu)
            if pfad == "/api/erinnerungen":
                liste = daten.get("erinnerungen")
                if not isinstance(liste, list) or len(liste) > MAX_ERINNERUNGEN:
                    raise ValueError("Höchstens 30 Erinnerungen.")
                liste = sorted((erinnerung_pruefen(e) for e in liste), key=lambda e: e["zeit"])
                with _lock:
                    schreiben("erinnerungen", liste)
                return self.senden(200, erinnerungen_app(liste))
            if pfad == "/api/medikament/genommen":   # der Knopf "Genommen" an der Erinnerung
                return self.senden(200, medikament_knopf(str(daten.get("id") or "")))
            return self.senden(404, {"fehler": "Gibt es nicht."})
        except ValueError as e:
            return self.senden(400, {"fehler": str(e)})
        except RuntimeError as e:
            return self.senden(503, {"fehler": str(e)})

    def chat_strom(self, text, nr, gesprochen):
        """Die Antwort als Server-Sent Events: {"text": ...} für jedes neue Stück, am Ende {"fertig": ...} mit allem,
        was sonst /api/chat liefert, oder {"fehler": ...}. Legt die App vorher auf, wird die Antwort trotzdem fertig
        geschrieben und gespeichert."""
        self.strom_beginnen("text/event-stream; charset=utf-8")
        ereignis = lambda d: self.strom_schreiben(f"data: {json.dumps(d, ensure_ascii=False)}\n\n".encode())
        try:
            ergebnis = chat(text, nr, beim_text=lambda stueck: ereignis({"text": stueck}), gesprochen=gesprochen)
            ereignis({"fertig": ergebnis})
        except (ValueError, RuntimeError) as e:
            ereignis(self.uebersetzt({"fehler": str(e)}))

    def stimme_strom(self, stuecke):
        """Der Ton geht roh hinaus, sobald der Sprachdienst ihn liefert: die App spielt das erste Stück schon ab,
        während der Rest noch entsteht."""
        self.strom_beginnen("application/octet-stream")
        try:
            for stueck in stuecke:
                if not self.strom_schreiben(stueck):
                    break   # die App hört nicht mehr zu (unterbrochen oder aufgelegt)
        except OSError:
            protokoll("Sprachdienst-Fehler: Verbindung beim Sprechen abgebrochen")

    def zuhoeren(self):
        """Die Aufnahme aus dem Mikrofon kommt als roher Ton an und geht als Text zurück."""
        n = int(self.headers.get("Content-Length") or 0)
        if n > MAX_AUFNAHME:
            raise ValueError("Die Aufnahme ist zu lang. Bitte kürzer sprechen.")
        ton = self.rfile.read(n)
        nein = self.darf("/api/aufnahme")
        if nein:
            return self.senden(*nein)
        if not SPRACH_KEY:
            raise RuntimeError("Der Sprachdienst ist nicht eingerichtet.")
        art = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        if not ton or art not in AUFNAHME_ARTEN:
            raise ValueError("Das hat nicht geklappt, bitte nochmal.")
        return self.senden(200, text_hoeren(ton, art))

    def bildschirm(self):
        """Die Android-App schickt, was gerade auf dem Bildschirm ist (JPEG). Biko sieht es bei den nächsten Fragen.
        Mit ?foto: ein Foto von der Kamera der App (z. B. von einem Brief), Biko erklärt es dann."""
        n = int(self.headers.get("Content-Length") or 0)
        if n > MAX_BILDSCHIRM:
            raise ValueError("Das Bild ist zu groß.")
        bild = self.rfile.read(n)
        nein = self.darf("/api/aufnahme")
        if nein:
            return self.senden(*nein)
        if not bild.startswith(b"\xff\xd8"):
            raise ValueError("Das hat nicht geklappt, bitte nochmal.")
        art = "foto" if "foto" in parse_qs(urlparse(self.path).query, keep_blank_values=True) else "bildschirm"
        bildschirm_merken(bild, art)
        protokoll(f"{'Foto' if art == 'foto' else 'Bildschirm'}: {len(bild) // 1000} kB bekommen")
        return self.senden(200, {"ok": True})

    def login(self, daten):
        """Mit dem Passwort (Verwalter) oder einem Einladungscode (die Person selbst oder ihre Familie)."""
        ip = self.ip()
        versuche = [t for t in _fehlversuche.get(ip, []) if time.time() - t < 900]
        if len(versuche) >= 5:
            return self.senden(429, {"fehler": "Zu viele Versuche. Bitte in 15 Minuten nochmal."})
        eingabe = str(daten.get("code") or daten.get("passwort") or "")
        rolle, pid, version = None, None, 0
        if PASSWORT and hmac.compare_digest(eingabe.encode(), PASSWORT.encode()):
            rolle = "verwalter"
        else:
            gefunden = code_pruefen(eingabe)
            if gefunden:
                pid, rolle = gefunden
                version = person_finden(pid).get("version", 1)
        if not rolle:
            if not PASSWORT and not daten.get("code"):
                return self.senden(503, {"fehler": "Am Server ist noch kein Passwort eingestellt (APP_PASSWORT)."})
            versuche.append(time.time())
            _fehlversuche[ip] = versuche
            return self.senden(403, {"fehler": "Das Passwort oder der Code stimmt nicht."})
        _fehlversuche.pop(ip, None)
        protokoll(f"Anmeldung: {rolle}")
        return self.senden(200, {"ok": True, "rolle": rolle},
                           extra=self.cookie_setzen(cookie_wert(rolle, pid, version)))

    # --- Familie und Verwaltung ---
    def familie_uebersicht(self):
        s = self.angemeldet()
        if s["rolle"] != "verwalter":
            return {"rolle": s["rolle"], "personen": [familie_blick()]}
        liste = []
        for p in personen_lesen():
            person_setzen(p["id"])
            liste.append({**familie_blick(), "bezeichnung": p["name"], "kosten": kosten_monat(),
                          "offen": p["id"] == s["person"]})
        person_setzen(s["person"])
        return {"rolle": "verwalter", "personen": liste}

    def verwaltung(self, pfad, daten):
        if pfad == "/api/verwaltung/person":
            p = person_anlegen(daten.get("name"), str(daten.get("sprache") or "de-AT"), str(daten.get("anrede") or "du"))
            protokoll("Verwaltung: neue Person angelegt")
            return self.senden(200, {"person": p["id"], "person_code": code_erzeugen(p["id"], "person"),
                                     "familie_code": code_erzeugen(p["id"], "familie")})
        pid = str(daten.get("person") or "")
        if not person_finden(pid):
            return self.senden(404, {"fehler": "Gibt es nicht."})
        if pfad == "/api/verwaltung/code":
            return self.senden(200, code_erzeugen(pid, str(daten.get("rolle") or "")))
        if pfad == "/api/verwaltung/oeffnen":   # Biko als diese Person öffnen, z. B. zum Einrichten
            return self.senden(200, {"ok": True}, extra=self.cookie_setzen(cookie_wert("verwalter", pid)))
        if pfad == "/api/verwaltung/abmelden":
            person_abmelden(pid)
            protokoll("Verwaltung: Geräte einer Person abgemeldet")
            return self.senden(200, {"ok": True})
        return self.senden(404, {"fehler": "Gibt es nicht."})

    def datei(self, pfad):
        if pfad in ("", "/"):
            pfad = "/index.html"
        if pfad == "/familie":
            pfad = "/familie.html"
        ziel = (WEB / pfad.lstrip("/")).resolve()
        if not str(ziel).startswith(str(WEB.resolve())) or not ziel.is_file():
            ziel = WEB / "index.html"
        return self.senden(200, ziel.read_bytes(), TYPEN.get(ziel.suffix, "application/octet-stream"))


if __name__ == "__main__":
    if not PASSWORT:
        print("Achtung: APP_PASSWORT ist nicht gesetzt, Anmelden geht erst danach.", flush=True)
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("Achtung: ANTHROPIC_API_KEY ist nicht gesetzt, Biko kann noch nicht antworten.", flush=True)
    print(f"Biko Assistent läuft auf Port {PORT}, Modell {MODELL}", flush=True)
    threading.Thread(target=hausmeister, daemon=True).start()
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
