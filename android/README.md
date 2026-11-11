# Biko Helfer für Android: Biko als Blase

Kleine Android-App um den Biko Helfer (`assistent/`). Biko schwebt als runde Blase über allen Apps.
Ein Tipp auf die Blase öffnet ihn als Karte über der App, die gerade offen ist, und er hört gleich zu.
Ziehen verschiebt ihn, auf das ✕ unten ziehen blendet ihn aus (bis man die App wieder öffnet).

Die App zeigt die Seite `https://biko-helfer-production.up.railway.app/` (eingestellt in `app/build.gradle`,
`BIKO_ADRESSE`). Alles, was Biko kann, kommt also wie bisher vom Server; die App bringt nur die Blase,
das Mikrofon und das Fenster dazu. Öffnet sie Biko über die Blase, hängt sie `?reden` an die Adresse,
dann beginnt die Seite das Gespräch von selbst.

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
