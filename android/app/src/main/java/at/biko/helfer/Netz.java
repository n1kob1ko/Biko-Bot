package at.biko.helfer;

import android.Manifest;
import android.annotation.SuppressLint;
import android.app.Activity;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.net.Uri;
import android.webkit.CookieManager;
import android.webkit.PermissionRequest;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;

/** Gemeinsame Einstellungen für das Fenster, in dem die Biko-Seite läuft. */
final class Netz {
    static final int MIKRO_ANFRAGE = 7;
    private static PermissionRequest wartend; // Mikrofon-Wunsch der Seite, solange Android noch fragt
    static int vorne; // wie viele Biko-Fenster gerade vorne sind (dann meldet sich die Seite selbst)

    private Netz() {}

    static Uri adresse() { return Uri.parse(BuildConfig.BIKO_ADRESSE); }

    @SuppressLint("SetJavaScriptEnabled")
    static WebView bauen(Activity a) { return bauen(a, a); }

    /** `a` darf null sein (im Assistenten-Fenster gibt es keine Activity): dann bekommt die Seite das Mikrofon nur,
     *  wenn es schon erlaubt ist. */
    static WebView bauen(Context c, Activity a) {
        WebView w = new WebView(c);
        WebSettings s = w.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setMediaPlaybackRequiresUserGesture(false); // Biko darf sofort sprechen, auch ohne Antippen
        s.setTextZoom(100);
        CookieManager.getInstance().setAcceptCookie(true); // angemeldet bleiben
        w.setBackgroundColor(0xFFFFF6E8);
        w.addJavascriptInterface(new Wecker.Bruecke(c), "BikoWecker");
        w.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView v, WebResourceRequest r) {
                Uri u = r.getUrl();
                if (adresse().getHost().equals(u.getHost())) return false;
                // Links zu Angeboten usw. gehen im normalen Browser auf
                try {
                    c.startActivity(new Intent(Intent.ACTION_VIEW, u).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
                } catch (Exception e) { /* kein Browser */ }
                return true;
            }
        });
        w.setWebChromeClient(new WebChromeClient() {
            @Override
            public void onPermissionRequest(PermissionRequest r) {
                w.post(() -> {
                    if (c.checkSelfPermission(Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED) {
                        r.grant(new String[] { PermissionRequest.RESOURCE_AUDIO_CAPTURE });
                    } else if (a != null) {
                        wartend = r;
                        a.requestPermissions(new String[] { Manifest.permission.RECORD_AUDIO }, MIKRO_ANFRAGE);
                    } else {
                        r.deny();
                    }
                });
            }
        });
        return w;
    }

    /** Aus onRequestPermissionsResult: der Seite sagen, ob sie das Mikrofon bekommt. */
    static void mikroAntwort(int code, int[] ergebnis) {
        if (code != MIKRO_ANFRAGE || wartend == null) return;
        if (ergebnis.length > 0 && ergebnis[0] == PackageManager.PERMISSION_GRANTED) {
            wartend.grant(new String[] { PermissionRequest.RESOURCE_AUDIO_CAPTURE });
        } else {
            wartend.deny();
        }
        wartend = null;
    }

    static void sichern() { CookieManager.getInstance().flush(); }

    /** Schickt das Bildschirmfoto an Biko (im Hintergrund). Er sieht es dann bei den nächsten Fragen. */
    static void bildschirmSchicken(android.graphics.Bitmap bild) {
        if (bild == null) return;
        // Verkleinern spart Zeit und reicht zum Lesen
        float f = Math.min(1f, 1600f / Math.max(bild.getWidth(), bild.getHeight()));
        android.graphics.Bitmap klein = f < 1f
                ? android.graphics.Bitmap.createScaledBitmap(bild, Math.round(bild.getWidth() * f), Math.round(bild.getHeight() * f), true)
                : bild;
        java.io.ByteArrayOutputStream aus = new java.io.ByteArrayOutputStream();
        klein.compress(android.graphics.Bitmap.CompressFormat.JPEG, 80, aus);
        byte[] daten = aus.toByteArray();
        String keks = CookieManager.getInstance().getCookie(BuildConfig.BIKO_ADRESSE);
        new Thread(() -> {
            try {
                java.net.HttpURLConnection v = (java.net.HttpURLConnection)
                        new java.net.URL(BuildConfig.BIKO_ADRESSE + "api/bildschirm").openConnection();
                v.setRequestMethod("POST");
                v.setDoOutput(true);
                v.setConnectTimeout(8000);
                v.setReadTimeout(15000);
                v.setRequestProperty("Content-Type", "image/jpeg");
                if (keks != null) v.setRequestProperty("Cookie", keks);
                v.setFixedLengthStreamingMode(daten.length);
                try (java.io.OutputStream o = v.getOutputStream()) { o.write(daten); }
                v.getResponseCode();
                v.disconnect();
            } catch (Exception e) { /* dann eben ohne Bild */ }
        }).start();
    }
}
