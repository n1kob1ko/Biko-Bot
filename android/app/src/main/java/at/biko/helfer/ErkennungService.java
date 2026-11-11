package at.biko.helfer;

import android.content.Intent;
import android.speech.RecognitionService;

/** Android verlangt von jedem Assistenten auch eine Spracherkennung. Biko hört über den Server zu, daher bleibt sie leer. */
public class ErkennungService extends RecognitionService {
    @Override protected void onStartListening(Intent i, Callback c) {
        try { c.error(android.speech.SpeechRecognizer.ERROR_CLIENT); } catch (Exception e) { /* egal */ }
    }
    @Override protected void onCancel(Callback c) {}
    @Override protected void onStopListening(Callback c) {}
}
