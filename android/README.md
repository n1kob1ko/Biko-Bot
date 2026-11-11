# Biko Helfer für Android: Biko als Blase

Kleine Android-App um den Biko Helfer (`assistent/`). Biko schwebt als runde Blase über allen Apps.

- **Antippen:** Biko hört sofort zu, ganz ohne Fenster. Die Blase zeigt, was er tut: mint pulsierender Ring = er hört zu,
  gelb und wackelnd = er überlegt, orange und hüpfend = er spricht. Nochmal antippen legt auf.
  Schreibt Biko eine Nachricht für jemanden (z. B. eine WeChat-Antwort), liegt sie gleich zum Einfügen bereit.
- **Lange drücken:** Biko groß als Karte, zum Lesen und Schreiben.
- **Ziehen** verschiebt ihn, auf das ✕ unten ziehen blendet ihn aus (bis man die App wieder öffnet).

Das kleine Gespräch führt die Biko-Seite selbst (`?mini`) in einem unsichtbaren 1-Pixel-Fenster in der Blase;
sie meldet über `BikoNativ.zustand()` zurück, ob Biko zuhört, nachdenkt oder spricht.

Die App zeigt die Seite `https://biko-helfer-production.up.railway.app/` (eingestellt in `app/build.gradle`,
`BIKO_ADRESSE`). Alles, was Biko kann, kommt also wie bisher vom Server; die App bringt nur die Blase,
das Mikrofon und das Fenster dazu. Öffnet sie Biko über die Blase, hängt sie `?reden` an die Adresse,
dann beginnt die Seite das Gespräch von selbst.

## Biko als Assistent: immer bereit, sieht den Bildschirm

Die App kann der **Standard-Assistent** des Geräts sein (wie sonst Google Gemini). Dann gilt:

- **Einschaltknopf gedrückt halten** (oder aus der unteren Ecke wischen, je nach Gerät): Biko kommt als Karte von unten
  und hört gleich zu, egal welche App offen ist.
- Android gibt ihm dabei ein **Bildschirmfoto** mit. Die App schickt es an den Server (`POST /api/bildschirm`),
  und Biko sieht es 5 Minuten lang bei jeder Frage (nur im Speicher, nicht im Verlauf). So geht „Was schreibt Mei?“,
  „Übersetz das“ oder „Was soll ich antworten?“.
- Ein Tipp auf die Blase holt dann auch still ein Bildschirmfoto, ohne Fenster.

Bei **Xiaomi** startet der Einschaltknopf erst einmal die Xiaomi-KI. Umstellen: Einstellungen › Zusätzliche Einstellungen ›
Gesten-Shortcuts (oder „Tastenkürzel“) › „Ein/Aus-Taste gedrückt halten“ › „Digitaler Assistent“ statt Xiaomi HyperAI.
Die Namen ändern sich je nach HyperOS-Version; wenn es das nicht gibt, bleibt die Blase der Weg.

Einstellen: Einstellungen › Apps › Standard-Apps › Digitaler Assistent › „Biko Helfer“, dort „Screenshot verwenden“
einschalten. Die App bietet das beim Start selbst an. Ein ständiges „Hey Biko“ gibt es nicht: Android erlaubt
das Dauer-Zuhören nur Google, und es würde den Akku leeren.

## Anrufen und WhatsApp aus der Blase

Sagt man der Blase „Ruf Peter an“ oder „Schreib Peter auf WhatsApp …“, öffnet die App nach Bikos Antwort gleich das Telefon
mit der Nummer (anrufen tippt man selbst) oder WhatsApp bzw. SMS mit dem fertigen Text (`BikoNativ.oeffnen()`).

## Biko meldet sich von selbst

Erinnerungen und die **Morgenrunde** kommen pünktlich, auch wenn die App gerade zu ist. Die Biko-Seite schickt der App
die Zeitpunkte der nächsten zwei Tage (`BikoWecker.planen()`), die App stellt dafür Android-Wecker (`Wecker.java`).
Geht einer los:

- Ist die **Blase** zu sehen, sagt Biko es gleich selbst („Erinnerung: Herztablette“, oder er erzählt die Morgenrunde).
- Dazu kommt eine **Mitteilung**. Ein Tipp auf „Guten Morgen!“ öffnet Biko als Karte, und er liest die Morgenrunde vor;
  ein Tipp auf eine Erinnerung öffnet Biko groß mit „Erledigt“ und „Später“.
- Nach einem Neustart des Tablets stellt die App die Wecker wieder und schaltet die Blase ein.

Die Morgenrunde stellt man im Gespräch ein: „Meld dich jeden Morgen um 8“ (oder „Hör auf mit der Morgenrunde“).
Biko schreibt sie kurz vorher am Server (Wetter in Wien, zwei, drei Nachrichten, die Termine des Tages) als eigenes Gespräch,
in dem man gleich weiterreden kann.

## Installieren (Test)

1. Auf dem Tablet im Browser öffnen:
   https://github.com/n1kob1ko/Biko-Bot/releases/download/android-test/biko-helfer.apk
2. Die Datei öffnen. Fragt Android, ob der Browser Apps installieren darf: erlauben.
   Warnt Play Protect vor einer unbekannten App: „Trotzdem installieren“.
3. „Biko Helfer“ öffnen. Mikrofon und Mitteilungen erlauben, dann bei „Über anderen Apps anzeigen“ den Schalter einschalten
   und zurück. Biko ist jetzt groß da; sobald man die App verlässt, schwebt er als Blase.

### Zusätzlich bei Xiaomi (HyperOS)

Xiaomi sperrt manches zusätzlich. Unter Einstellungen › Apps › Apps verwalten › Biko Helfer:

- **Weitere Berechtigungen:** „Pop-up-Fenster im Hintergrund anzeigen“ und „Über anderen Apps anzeigen“ erlauben
  (sonst geht nach dem Tipp auf die Blase nichts auf).
- **Autostart** einschalten und **Akkusparmodus** auf „Keine Einschränkungen“ (sonst verschwindet die Blase nach einer Weile).

## Strom

Die Blase selbst braucht fast nichts. Mikrofon und Stimme laufen nur, während das Gespräch offen ist;
schließt man es oder wechselt die App, legt Biko auf.

## Bauen

GitHub baut die App bei jeder Änderung in `android/` (Workflow „Android-App bauen“) und stellt sie nach dem Merge
unter dem Link oben bereit. Lokal: `cd android && ./gradlew assembleDebug` (braucht das Android SDK).

Die App ist mit einem festen Test-Schlüssel (`app/test-schluessel.jks`, Passwort steht in `app/build.gradle`) signiert,
damit neue Versionen sich über die alte installieren lassen. Der Schlüssel ist öffentlich und nur zum Testen:
für den Play Store braucht es einen eigenen, geheimen Schlüssel.
