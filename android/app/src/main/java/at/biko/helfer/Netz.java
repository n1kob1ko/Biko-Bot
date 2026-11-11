package at.biko.helfer;

import android.Manifest;
import android.annotation.SuppressLint;
import android.app.Activity;
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

    private Netz() {}

    static Uri adresse() { return Uri.parse(BuildConfig.BIKO_ADRESSE); }

    @SuppressLint("SetJavaScriptEnabled")
    static WebView bauen(Activity a) {
        WebView w = new WebView(a);
        WebSettings s = w.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setMediaPlaybackRequiresUserGesture(false); // Biko darf sofort sprechen, auch ohne Antippen
        s.setTextZoom(100);
        CookieManager.getInstance().setAcceptCookie(true); // angemeldet bleiben
        w.setBackgroundColor(0xFFFFF6E8);
        w.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView v, WebResourceRequest r) {
                Uri u = r.getUrl();
                if (adresse().getHost().equals(u.getHost())) return false;
                // Links zu Angeboten usw. gehen im normalen Browser auf
                try { a.startActivity(new Intent(Intent.ACTION_VIEW, u)); } catch (Exception e) { /* kein Browser */ }
                return true;
            }
        });
        w.setWebChromeClient(new WebChromeClient() {
            @Override
            public void onPermissionRequest(PermissionRequest r) {
                a.runOnUiThread(() -> {
                    if (a.checkSelfPermission(Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED) {
                        r.grant(new String[] { PermissionRequest.RESOURCE_AUDIO_CAPTURE });
                    } else {
                        wartend = r;
                        a.requestPermissions(new String[] { Manifest.permission.RECORD_AUDIO }, MIKRO_ANFRAGE);
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
}
