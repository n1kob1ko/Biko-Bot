# Biko Helfer: Produktbild

Kurzfassung für alle, die an der Oberfläche arbeiten. Grundlage ist Nikos Auftrag vom 9.11.2026;
was dort nicht gesagt wurde, ist als Annahme markiert.

## Für wen

Ältere Menschen aus Familie und Bekanntenkreis. Sie können mit dem Handy telefonieren, mit Apple Pay zahlen
und in WeChat Sprachnachrichten schicken. KI nutzen sie noch nicht. Sie sprechen Deutsch und Chinesisch.

Eingerichtet wird die App von jemandem aus der Familie (Name, Du/Sie, Passwort). Alles andere, etwa Diät oder Familie, erzählt man Biko einfach im Gespräch und er merkt es sich.

## Wofür

1. **Jemanden zum Reden haben.** Das ist das Wichtigste. Sprechen und Vorlesen stehen deshalb vorne.
2. Alles fragen können, so wie Niko KI nutzt: Angebote und Deals, Wetter, Kochen mit Diät-Regeln.
3. Kurze Nachrichten schreiben lassen (für WeChat, WhatsApp, SMS). Man sagt es Biko, der Text steht dann im Gespräch.
4. An Dinge erinnern, vor allem an Medikamente. Man sagt es Biko, er schreibt es sich selbst auf.

## Grundsatz: Funktionen laufen über das Gespräch

Nikos Korrektur vom 10.11.2026: keine eigenen Bereiche mit Formularen für einzelne Funktionen. Wer etwas
will, sagt es Biko ("erinnere mich an ..."), und Biko erledigt es im Hintergrund. Die Oberfläche zeigt nur,
dass es passiert ist ("Gemerkt" unter der Antwort), und bietet der Familie eine Liste zum Nachsehen.
Bevor eine neue Funktion einen Knopf oder ein Formular bekommt, zuerst fragen: Kann Biko das im Gespräch?

Seit dem ersten Live-Test (10.11.2026) gilt das auch für Nachrichten und Links: "Schreib Anna, dass ..." stellt den
fertigen Text mit "Kopieren" ins Gespräch, und findet Biko kein genaues Angebot, stellt er den Prospekt als Knopf
dazu, statt die Person zum Suchen zu schicken. Die Leiste hat drei Bereiche: Reden, Verlauf, Einstellen.
Der Verlauf ist kein Formular, sondern nur die Liste früherer Gespräche zum Wiederöffnen.

## Wie es sich anfühlen soll

- Ruhig, hell, freundlich. Biko ist süß und lebendig, die Oberfläche um ihn herum bleibt still.
- Vertraut: Der große runde Knopf funktioniert wie eine WeChat-Sprachnachricht.
- Eine Sache pro Bild. Lieber ein Schritt mehr als zwei Entscheidungen auf einmal.

## Gestaltungsregeln

- **Eine Akzentfarbe:** Biko-Gelb. Rot nur für Löschen, Fehler und "Aufnahme läuft", Grün nur für "an" und "geschafft".
- **Biko ist die Statusanzeige:** winkt, hört zu, tippt, freut sich, ist traurig bei einem Fehler. Kein zweiter Ladebalken daneben.
- **Groß und klar:** Schrift ab 19 px (einstellbar bis 130 %), Tippflächen mindestens 48 px, Kontrast mindestens 4,5 zu 1 in Hell und Dunkel.
- **Symbole immer mit Wort**, keine Emojis. Ausnahme: der Sprachknopf neben einem Titel zeigt nur sein Symbol.
- **Zweisprachig denken:** Jeder Text steht in `web/texte.js` auf Deutsch und Chinesisch. Einfache Wörter, ganze Sätze, keine Fachbegriffe.
- **Nichts geht still verloren:** Löschen fragt nach, ein fehlgeschlagener Text bleibt im Feld.
- **Bewegung erklärt, woher etwas kommt und wohin es geht.** Die 20 Regeln stehen in der README.

## Leitplanken

Biko sagt ehrlich, dass er eine KI ist. Bei Gesundheit erinnert er und gibt Hinweise, aber keine Beratung
(Notruf 144, Gesundheitstelefon 1450, Telefonseelsorge 142). Er warnt vor Betrugsmaschen.

## Annahmen

- Die meisten nutzen ein iPhone mit Safari (wegen Apple Pay). Getestet ist bisher nur in Chromium.
- Eine Person pro Installation.
