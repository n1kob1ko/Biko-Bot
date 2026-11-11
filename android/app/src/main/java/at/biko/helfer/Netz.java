package at.biko.helfer;

import android.Manifest;
import android.annotation.SuppressLint;
import android.app.Activity;
import android.content.ContentValues;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.net.Uri;
import android.os.Build;
import android.os.Environment;
import android.provider.MediaStore;
import android.webkit.ValueCallback;
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
    static final int FOTO_ANFRAGE = 8;
    private static ValueCallback<Uri[]> fotoWartet; // die Seite wartet auf ein Foto (Kamera-Knopf)
    private static Uri fotoZiel;                    // dorthin schreibt die Kamera das Foto
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
            /** Der Kamera-Knopf der Seite: gleich die Kamera öffnen (sonst ein Bild aussuchen). */
            @Override
            public boolean onShowFileChooser(WebView v, ValueCallback<Uri[]> antwort, FileChooserParams p) {
                if (a == null) return false;
                if (fotoWartet != null) fotoWartet.onReceiveValue(null);
                fotoWartet = antwort;
                fotoZiel = null;
                Intent i = null;
                if (p.isCaptureEnabled() && Build.VERSION.SDK_INT >= 29) {
                    try {
                        altesFotoWeg(a);
                        ContentValues werte = new ContentValues();
                        werte.put(MediaStore.Images.Media.DISPLAY_NAME, "biko-foto.jpg");
                        werte.put(MediaStore.Images.Media.MIME_TYPE, "image/jpeg");
                        werte.put(MediaStore.Images.Media.RELATIVE_PATH, Environment.DIRECTORY_PICTURES + "/Biko");
                        fotoZiel = a.getContentResolver().insert(MediaStore.Images.Media.EXTERNAL_CONTENT_URI, werte);
                        if (fotoZiel != null) {
                            i = new Intent(MediaStore.ACTION_IMAGE_CAPTURE)
                                    .putExtra(MediaStore.EXTRA_OUTPUT, fotoZiel)
                                    .addFlags(Intent.FLAG_GRANT_WRITE_URI_PERMISSION);
                        }
                    } catch (Exception e) { fotoZiel = null; }
                }
                try {
                    a.startActivityForResult(i != null ? i : p.createIntent(), FOTO_ANFRAGE);
                } catch (Exception e) {
                    try {
                        a.startActivityForResult(p.createIntent(), FOTO_ANFRAGE); // keine Kamera-App: aussuchen
                    } catch (Exception e2) {
                        fotoWartet = null;
                        return false;
                    }
                }
                return true;
            }

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

    static boolean waehltFoto() { return fotoWartet != null; }

    /** Aus onActivityResult: das Foto (oder nichts) an die Seite geben. */
    static void fotoAntwort(Activity a, int code, int ergebnis, Intent daten) {
        if (code != FOTO_ANFRAGE || fotoWartet == null) return;
        Uri[] wahl;
        if (fotoZiel != null && ergebnis == Activity.RESULT_OK) {
            wahl = new Uri[] { fotoZiel };
            a.getSharedPreferences("biko", Context.MODE_PRIVATE).edit().putString("foto", fotoZiel.toString()).apply();
        } else {
            if (fotoZiel != null) {
                try { a.getContentResolver().delete(fotoZiel, null, null); } catch (Exception e) { /* egal */ }
            }
            wahl = WebChromeClient.FileChooserParams.parseResult(ergebnis, daten);
        }
        fotoWartet.onReceiveValue(wahl);
        fotoWartet = null;
        fotoZiel = null;
    }

    /** Es bleibt nur das letzte Foto in der Galerie (Bilder/Biko): Briefe sollen sich dort nicht sammeln. */
    private static void altesFotoWeg(Context c) {
        String alt = c.getSharedPreferences("biko", Context.MODE_PRIVATE).getString("foto", null);
        if (alt == null) return;
        try { c.getContentResolver().delete(Uri.parse(alt), null, null); } catch (Exception e) { /* schon weg */ }
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
