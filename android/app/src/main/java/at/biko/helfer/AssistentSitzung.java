package at.biko.helfer;

import android.content.Context;
import android.graphics.Bitmap;
import android.graphics.drawable.GradientDrawable;
import android.os.Bundle;
import android.service.voice.VoiceInteractionSession;
import android.util.DisplayMetrics;
import android.view.Gravity;
import android.view.View;
import android.webkit.WebView;
import android.widget.FrameLayout;

/** Biko als Karte von unten, über allem, was gerade offen ist. Er sieht den Bildschirm dahinter. */
public class AssistentSitzung extends VoiceInteractionSession {
    private FrameLayout karte;
    private WebView web;
    private boolean still; // nur das Bildschirmfoto holen (für die Blase), kein Fenster

    AssistentSitzung(Context c) { super(c); }

    @Override
    public View onCreateContentView() {
        Context c = getContext();
        DisplayMetrics m = c.getResources().getDisplayMetrics();
        float dp = m.density;
        FrameLayout wurzel = new FrameLayout(c);
        wurzel.setBackgroundColor(0x732B2140); // die App dahinter leicht abdunkeln
        wurzel.setOnClickListener(v -> hide()); // daneben getippt

        karte = new FrameLayout(c);
        GradientDrawable form = new GradientDrawable();
        form.setColor(0xFFFFF6E8);
        form.setCornerRadius(28 * dp);
        karte.setBackground(form);
        karte.setClipToOutline(true);
        karte.setElevation(16 * dp);
        karte.setClickable(true);
        int breite = Math.min(m.widthPixels - Math.round(24 * dp), Math.round(560 * dp));
        int hoehe = Math.round(Math.min(m.heightPixels * 0.78f, 860 * dp));
        FrameLayout.LayoutParams lp = new FrameLayout.LayoutParams(breite, hoehe, Gravity.BOTTOM | Gravity.CENTER_HORIZONTAL);
        lp.bottomMargin = Math.round(56 * dp); // über der Navigationsleiste
        wurzel.addView(karte, lp);
        return wurzel;
    }

    @Override
    public void onPrepareShow(Bundle args, int flags) {
        still = args != null && args.getBoolean("still");
        setUiEnabled(!still);
        super.onPrepareShow(args, flags);
    }

    @Override
    public void onShow(Bundle args, int flags) {
        super.onShow(args, flags);
        if (still) {
            new android.os.Handler(android.os.Looper.getMainLooper()).postDelayed(this::hide, 3000); // falls kein Bild kommt
            return;
        }
        BlaseService.sichtbar(false);
        if (web == null) {
            web = Netz.bauen(getContext(), null);
            karte.addView(web, new FrameLayout.LayoutParams(-1, -1));
        }
        web.onResume();
        web.loadUrl(BuildConfig.BIKO_ADRESSE + "?reden");
    }

    @Override
    public void onHandleScreenshot(Bitmap bild) {
        Netz.bildschirmSchicken(bild); // kommt kurz nach dem Öffnen; bis man fertig gefragt hat, ist es längst da
        if (still) hide();
    }

    @Override
    public void onHide() {
        if (still) { super.onHide(); return; }
        if (web != null) {
            web.onPause();
            web.loadUrl("about:blank"); // legt auf
        }
        Netz.sichern();
        BlaseService.sichtbar(true);
        super.onHide();
    }

    @Override
    public void onDestroy() {
        if (web != null) web.destroy();
        web = null;
        super.onDestroy();
    }
}
