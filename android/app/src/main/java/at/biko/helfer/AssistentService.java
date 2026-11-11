package at.biko.helfer;

import android.os.Bundle;
import android.service.voice.VoiceInteractionService;
import android.service.voice.VoiceInteractionSession;

/**
 * Biko als Standard-Assistent des Geräts: Einschaltknopf halten (oder aus der Ecke wischen) öffnet Biko,
 * und Android gibt ihm dabei das Bild vom Bildschirm mit.
 */
public class AssistentService extends VoiceInteractionService {
    private static AssistentService laeuft;

    @Override
    public void onReady() {
        super.onReady();
        laeuft = this;
    }

    @Override
    public void onShutdown() {
        laeuft = null;
        super.onShutdown();
    }

    /** Für die Blase: nur ein Bildschirmfoto holen, ohne Fenster. Geht nur, wenn Biko der Assistent ist. */
    static void stillesFoto() {
        AssistentService s = laeuft;
        if (s == null) return;
        Bundle b = new Bundle();
        b.putBoolean("still", true);
        try { s.showSession(b, VoiceInteractionSession.SHOW_WITH_SCREENSHOT); } catch (Exception e) { /* dann ohne */ }
    }

    /** Für die Blase: Biko wie über den Einschaltknopf öffnen, mit Bildschirm. Geht nur, wenn Biko der Assistent ist. */
    static boolean oeffnen() {
        AssistentService s = laeuft;
        if (s == null) return false;
        try {
            s.showSession(new Bundle(), VoiceInteractionSession.SHOW_WITH_ASSIST | VoiceInteractionSession.SHOW_WITH_SCREENSHOT);
            return true;
        } catch (Exception e) {
            return false;
        }
    }
}
