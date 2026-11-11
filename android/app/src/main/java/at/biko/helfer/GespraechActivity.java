package at.biko.helfer;

import android.app.Activity;
import android.content.Intent;
import android.content.res.Configuration;
import android.graphics.drawable.GradientDrawable;
import android.os.Build;
import android.os.Bundle;
import android.util.DisplayMetrics;
import android.view.Gravity;
import android.view.View;
import android.view.WindowInsets;
import android.widget.FrameLayout;
import android.webkit.WebView;

/**
 * Nach einem Tipp auf die Blase: Biko kommt als Karte von unten über die App, die gerade offen ist,
 * und hört gleich zu. Tippen daneben oder "Zurück" schließt ihn wieder; die andere App bleibt, wo sie war.
 */
public class GespraechActivity extends Activity {
    private WebView web;
    private FrameLayout karte;
    private FrameLayout.LayoutParams lp;
    private int unten; // Höhe der Navigationsleiste

    @Override
    protected void onCreate(Bundle b) {
        super.onCreate(b);
        DisplayMetrics m = getResources().getDisplayMetrics();
        float dp = m.density;

        FrameLayout wurzel = new FrameLayout(this);
        wurzel.setOnClickListener(v -> finish()); // daneben getippt

        karte = new FrameLayout(this);
        GradientDrawable form = new GradientDrawable();
        form.setColor(0xFFFFF6E8);
        form.setCornerRadius(28 * dp);
        karte.setBackground(form);
        karte.setClipToOutline(true);
        karte.setElevation(16 * dp);
        karte.setClickable(true); // Tipps auf der Karte schließen nicht

        web = Netz.bauen(this);
        karte.addView(web, new FrameLayout.LayoutParams(-1, -1));

        lp = new FrameLayout.LayoutParams(0, 0, Gravity.BOTTOM | Gravity.CENTER_HORIZONTAL);
        groesse();
        wurzel.addView(karte, lp);

        // Nicht unter die Navigationsleiste rutschen
        wurzel.setOnApplyWindowInsetsListener((v, ins) -> {
            unten = Build.VERSION.SDK_INT >= 30
                    ? ins.getInsets(WindowInsets.Type.systemBars()).bottom
                    : ins.getSystemWindowInsetBottom();
            groesse();
            return ins;
        });

        setContentView(wurzel);
        web.loadUrl(adresse(getIntent()));
    }

    /** Normal hört Biko gleich zu (?reden). Aus der Mitteilung "Guten Morgen!" erzählt er die Morgenrunde. */
    private static String adresse(Intent i) {
        String seite = i == null ? null : i.getStringExtra("seite");
        return BuildConfig.BIKO_ADRESSE + "?" + ("morgenrunde".equals(seite) ? "morgenrunde" : "reden");
    }

    @Override
    protected void onNewIntent(Intent i) {
        super.onNewIntent(i);
        if (i.hasExtra("seite")) web.loadUrl(adresse(i));
    }

    /** Auf dem Handy fast so breit wie der Bildschirm, auf dem Tablet höchstens 560 dp. */
    private void groesse() {
        DisplayMetrics m = getResources().getDisplayMetrics();
        float dp = m.density;
        lp.width = Math.min(m.widthPixels - Math.round(24 * dp), Math.round(560 * dp));
        lp.height = Math.round(Math.min(m.heightPixels * 0.82f, 860 * dp));
        lp.bottomMargin = Math.round(12 * dp) + unten;
        karte.setLayoutParams(lp);
    }

    @Override
    public void onConfigurationChanged(Configuration c) {
        super.onConfigurationChanged(c);
        groesse(); // Tablet gedreht
    }

    @Override
    protected void onResume() {
        super.onResume();
        Netz.vorne++;
        web.onResume();
        BlaseService.sichtbar(false);
    }

    @Override
    protected void onPause() {
        Netz.vorne--;
        super.onPause();
    }

    @Override
    protected void onStop() {
        // Weggewechselt (nicht nur eine Rückfrage von Android): Gespräch zu, Blase wieder da
        web.onPause();
        Netz.sichern();
        BlaseService.sichtbar(true);
        super.onStop();
        if (!isChangingConfigurations() && !Netz.waehltFoto()) finish(); // die Kamera ist kein Wegwechseln
    }

    @Override
    protected void onActivityResult(int code, int ergebnis, Intent daten) {
        super.onActivityResult(code, ergebnis, daten);
        Netz.fotoAntwort(this, code, ergebnis, daten);
    }

    @Override
    public void onRequestPermissionsResult(int code, String[] p, int[] ergebnis) {
        Netz.mikroAntwort(code, ergebnis);
    }

    @Override
    protected void onDestroy() {
        web.destroy();
        super.onDestroy();
    }
}
