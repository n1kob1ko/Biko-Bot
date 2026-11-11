package at.biko.helfer;

import android.animation.ValueAnimator;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.ServiceInfo;
import android.content.res.Configuration;
import android.graphics.PixelFormat;
import android.graphics.drawable.GradientDrawable;
import android.os.Build;
import android.os.IBinder;
import android.provider.Settings;
import android.util.DisplayMetrics;
import android.view.Gravity;
import android.view.MotionEvent;
import android.view.View;
import android.view.ViewConfiguration;
import android.view.WindowManager;
import android.view.animation.DecelerateInterpolator;
import android.widget.FrameLayout;
import android.widget.ImageView;
import android.widget.TextView;
import android.widget.Toast;
import android.webkit.JavascriptInterface;
import android.webkit.WebView;
import android.content.ClipData;
import android.content.ClipboardManager;
import android.Manifest;
import android.content.pm.PackageManager;
import org.json.JSONObject;

/**
 * Biko als Blase über allen Apps. Antippen: Biko hört gleich zu, ganz ohne Fenster, und die Blase zeigt,
 * ob er zuhört, nachdenkt oder spricht. Nochmal antippen legt auf. Lange drücken öffnet Biko groß.
 * Ziehen verschiebt ihn, auf das ✕ unten ziehen blendet ihn aus (bis man die App wieder öffnet).
 * Das Gespräch selbst führt die Biko-Seite in einem winzigen, unsichtbaren Fenster in der Blase (?mini).
 */
public class BlaseService extends Service {
    private static final String KANAL = "blase";
    private static final String AUS = "at.biko.helfer.AUS";
    private static BlaseService laeuft;

    private WindowManager wm;
    private FrameLayout blase;
    private WindowManager.LayoutParams blp;
    private TextView weg; // das ✕ unten, nur beim Ziehen sichtbar
    private ValueAnimator atmen;
    private View ring;        // farbiger Ring um die Blase: zeigt, was Biko gerade tut
    private ImageView bild;
    private WebView web;      // führt das Gespräch
    private String zustand = "aus"; // aus, hoert, denkt, spricht
    private float dp;
    private int groesse;

    static void starten(Context c) {
        if (!Settings.canDrawOverlays(c)) return;
        Intent i = new Intent(c, BlaseService.class);
        if (Build.VERSION.SDK_INT >= 26) c.startForegroundService(i); else c.startService(i);
    }

    /** Ein Wecker ist losgegangen: ist die Blase zu sehen, sagt Biko die Erinnerung (oder die Morgenrunde) selbst. */
    static void melden(String art, String id, String text) {
        BlaseService s = laeuft;
        if (s == null || s.web == null || s.blase == null || s.blase.getVisibility() != View.VISIBLE) return;
        if (!"aus".equals(s.zustand)) return; // mitten im Gespräch: die Mitteilung reicht
        s.web.onResume();
        s.web.evaluateJavascript("window.bikoMelden && bikoMelden(" + JSONObject.quote(art) + ","
                + JSONObject.quote(id) + "," + JSONObject.quote(text == null ? "" : text) + ")", null);
    }

    /** Während Biko groß offen ist, braucht es die Blase nicht. */
    static void sichtbar(boolean ja) {
        BlaseService s = laeuft;
        if (s == null || s.blase == null) return;
        if (!ja && !"aus".equals(s.zustand)) s.auflegen(); // Biko groß offen: das kleine Gespräch endet
        s.blase.setVisibility(ja ? View.VISIBLE : View.GONE);
    }

    @Override
    public void onCreate() {
        super.onCreate();
        laeuft = this;
        wm = (WindowManager) getSystemService(WINDOW_SERVICE);
        dp = getResources().getDisplayMetrics().density;
        groesse = Math.round(68 * dp);
        vordergrund();
        blaseBauen();
    }

    @Override
    public int onStartCommand(Intent i, int flags, int id) {
        if (i != null && AUS.equals(i.getAction())) { stopSelf(); return START_NOT_STICKY; }
        return START_STICKY;
    }

    /** Android verlangt für Dauerdienste eine Mitteilung. Sie sagt nur, dass Biko da ist. */
    private void vordergrund() {
        NotificationManager nm = getSystemService(NotificationManager.class);
        NotificationChannel k = new NotificationChannel(KANAL, "Biko schwebt", NotificationManager.IMPORTANCE_MIN);
        k.setShowBadge(false);
        nm.createNotificationChannel(k);
        PendingIntent aus = PendingIntent.getService(this, 1,
                new Intent(this, BlaseService.class).setAction(AUS), PendingIntent.FLAG_IMMUTABLE);
        PendingIntent oeffnen = PendingIntent.getActivity(this, 2,
                new Intent(this, StartActivity.class), PendingIntent.FLAG_IMMUTABLE);
        Notification n = new Notification.Builder(this, KANAL)
                .setSmallIcon(R.drawable.ic_benachrichtigung)
                .setContentTitle("Biko ist da")
                .setContentText("Tipp auf die Blase, dann hört Biko zu.")
                .setContentIntent(oeffnen)
                .addAction(new Notification.Action.Builder(null, "Ausblenden", aus).build())
                .setOngoing(true)
                .build();
        if (Build.VERSION.SDK_INT >= 34) {
            // Mit "Mikrofon" darf Biko auch zuhören, während eine andere App vorne ist
            boolean mikro = checkSelfPermission(Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED;
            try {
                startForeground(1, n, ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE
                        | (mikro ? ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE : 0));
            } catch (Exception e) {
                startForeground(1, n, ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE);
            }
        } else if (Build.VERSION.SDK_INT >= 30) {
            startForeground(1, n, ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE);
        } else {
            startForeground(1, n);
        }
    }

    private static int typ() {
        return WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY;
    }

    private void blaseBauen() {
        blase = new FrameLayout(this);
        GradientDrawable kreis = new GradientDrawable();
        kreis.setShape(GradientDrawable.OVAL);
        kreis.setColor(0xFFFFF6E8);
        kreis.setStroke(Math.round(3.5f * dp), 0xFFFFC94D);
        blase.setBackground(kreis);
        blase.setElevation(8 * dp);
        int rand = Math.round(6 * dp);
        blase.setPadding(rand, rand, rand, rand);
        bild = new ImageView(this);
        bild.setImageResource(R.drawable.biko);
        bild.setContentDescription("Biko, zum Reden antippen");
        blase.addView(bild, new FrameLayout.LayoutParams(-1, -1));

        int platz = Math.round(22 * dp); // Platz für Schatten und Ring
        blp = new WindowManager.LayoutParams(groesse + 2 * platz, groesse + 2 * platz, typ(),
                WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE | WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS,
                PixelFormat.TRANSLUCENT);
        blp.gravity = Gravity.TOP | Gravity.START;
        FrameLayout huelle = new FrameLayout(this);
        huelle.setPadding(platz, platz, platz, platz);
        huelle.setClipToPadding(false);
        // Der Ring liegt hinter der Blase und wächst beim Zuhören und Sprechen über sie hinaus
        ring = new View(this);
        ring.setAlpha(0f);
        huelle.addView(ring, new FrameLayout.LayoutParams(groesse, groesse));
        huelle.addView(blase, new FrameLayout.LayoutParams(groesse, groesse));
        // Das unsichtbare Fenster für das Gespräch: 1 Pixel, damit die Seite als sichtbar gilt
        web = Netz.bauen(this, null);
        web.addJavascriptInterface(new Bruecke(), "BikoNativ");
        web.loadUrl(BuildConfig.BIKO_ADRESSE + "?mini");
        huelle.addView(web, new FrameLayout.LayoutParams(1, 1));

        SharedPreferences p = getSharedPreferences("biko", MODE_PRIVATE);
        DisplayMetrics m = bildschirm();
        blp.x = p.getBoolean("links", false) ? 0 : m.widthPixels - blp.width;
        blp.y = Math.round(p.getFloat("hoehe", 0.45f) * m.heightPixels);
        einpassen();
        wm.addView(huelle, blp);
        blase.setOnTouchListener(new Ziehen(huelle));
        blase = huelle; // sichtbar() blendet die ganze Hülle aus
        zustandZeigen("aus");
    }

    private void ringFarbe(int farbe) {
        GradientDrawable g = new GradientDrawable();
        g.setShape(GradientDrawable.OVAL);
        g.setColor(farbe & 0x55FFFFFF);
        g.setStroke(Math.round(4 * dp), farbe);
        ring.setBackground(g);
    }

    /** Wie Biko sich bewegt: atmet (aus), Ring pulst (hoert), wackelt (denkt), hüpft beim Reden (spricht). */
    private void zustandZeigen(String z) {
        zustand = z;
        if (atmen != null) atmen.cancel();
        bild.setRotation(0f);
        bild.setScaleX(1f);
        bild.setScaleY(1f);
        ring.setScaleX(1f);
        ring.setScaleY(1f);
        ring.setAlpha(0f);
        long dauer;
        switch (z) {
            case "hoert": ringFarbe(0xFF3FC7A6); dauer = 1300; break;   // mint: ich höre dich
            case "denkt": ringFarbe(0xFFFFC94D); dauer = 700; break;    // gelb: ich überlege
            case "spricht": ringFarbe(0xFFFF9F43); dauer = 650; break;  // orange: ich rede
            default: dauer = 1800;
        }
        atmen = ValueAnimator.ofFloat(0f, 1f);
        atmen.setDuration(dauer);
        atmen.setRepeatCount(ValueAnimator.INFINITE);
        atmen.setRepeatMode("aus".equals(z) || "denkt".equals(z) ? ValueAnimator.REVERSE : ValueAnimator.RESTART);
        atmen.addUpdateListener(a -> {
            float f = (float) a.getAnimatedValue();
            switch (zustand) {
                case "hoert": // Welle nach außen
                    ring.setScaleX(1f + 0.45f * f); ring.setScaleY(1f + 0.45f * f); ring.setAlpha(0.9f * (1f - f));
                    bild.setScaleX(1.03f); bild.setScaleY(1.03f);
                    break;
                case "denkt": // Kopf leicht hin und her
                    ring.setAlpha(0.6f + 0.3f * f); ring.setScaleX(1.12f); ring.setScaleY(1.12f);
                    bild.setRotation(-7f + 14f * f);
                    break;
                case "spricht": // hüpft im Takt
                    double w = Math.sin(f * Math.PI * 2);
                    ring.setScaleX(1f + 0.3f * f); ring.setScaleY(1f + 0.3f * f); ring.setAlpha(0.8f * (1f - f));
                    bild.setScaleY(1f + 0.07f * (float) Math.abs(w)); bild.setScaleX(1f - 0.02f * (float) Math.abs(w));
                    break;
                default: // atmet ganz leicht
                    bild.setScaleX(1f + 0.05f * f); bild.setScaleY(1f + 0.05f * f);
            }
        });
        atmen.start();
    }

    /** Was die Biko-Seite der App sagt. */
    private class Bruecke {
        @JavascriptInterface
        public void zustand(String z) {
            if (bild != null) bild.post(() -> { if (!z.equals(zustand)) zustandZeigen(z); });
        }

        @JavascriptInterface
        public void hinweis(String text) {
            if (bild != null) bild.post(() -> Toast.makeText(BlaseService.this, text, Toast.LENGTH_LONG).show());
        }

        @JavascriptInterface
        public void kopieren(String text) {
            if (bild == null) return;
            bild.post(() -> {
                ClipboardManager cm = getSystemService(ClipboardManager.class);
                cm.setPrimaryClip(ClipData.newPlainText("Biko", text));
                Toast.makeText(BlaseService.this, "Nachricht kopiert. Im Chat lange drücken und „Einfügen“.",
                        Toast.LENGTH_LONG).show();
            });
        }
    }

    /** Antippen: reden oder auflegen. */
    private void tippen() {
        if (web == null) return;
        if ("aus".equals(zustand)) {
            AssistentService.stillesFoto(); // ist Biko der Assistent, sieht er den Bildschirm mit
            zustandZeigen("denkt");
            web.onResume();
            web.evaluateJavascript("window.bikoReden ? bikoReden() : (window.BikoNativ && BikoNativ.zustand('aus'))", null);
            // Kommt nach 12 Sekunden nichts, war die Seite nicht bereit
            bild.postDelayed(() -> { if ("denkt".equals(zustand)) zustandZeigen("aus"); }, 12000);
        } else {
            auflegen();
        }
    }

    private void auflegen() {
        if (web != null) web.evaluateJavascript("window.bikoAuflegen && bikoAuflegen()", null);
        zustandZeigen("aus");
    }

    private DisplayMetrics bildschirm() {
        DisplayMetrics m = new DisplayMetrics();
        wm.getDefaultDisplay().getRealMetrics(m);
        return m;
    }

    private void einpassen() {
        DisplayMetrics m = bildschirm();
        blp.x = Math.max(0, Math.min(blp.x, m.widthPixels - blp.width));
        blp.y = Math.max(Math.round(40 * dp), Math.min(blp.y, m.heightPixels - blp.height - Math.round(60 * dp)));
    }

    /** Nach dem Loslassen gleitet Biko an den nächsten Rand. */
    private void anRand(View huelle) {
        DisplayMetrics m = bildschirm();
        boolean links = blp.x + blp.width / 2 < m.widthPixels / 2;
        int ziel = links ? 0 : m.widthPixels - blp.width;
        ValueAnimator a = ValueAnimator.ofInt(blp.x, ziel);
        a.setDuration(220);
        a.setInterpolator(new DecelerateInterpolator());
        a.addUpdateListener(v -> {
            blp.x = (int) v.getAnimatedValue();
            if (huelle.isAttachedToWindow()) wm.updateViewLayout(huelle, blp);
        });
        a.start();
        getSharedPreferences("biko", MODE_PRIVATE).edit()
                .putBoolean("links", links)
                .putFloat("hoehe", blp.y / (float) m.heightPixels)
                .apply();
    }

    private void wegZeigen(boolean ja) {
        if (ja && weg == null) {
            weg = new TextView(this);
            weg.setText("✕");
            weg.setTextSize(26);
            weg.setTextColor(0xFFFFFFFF);
            weg.setGravity(Gravity.CENTER);
            GradientDrawable g = new GradientDrawable();
            g.setShape(GradientDrawable.OVAL);
            g.setColor(0x992B2140);
            g.setStroke(Math.round(2 * dp), 0xFFFFFFFF);
            weg.setBackground(g);
            int s = Math.round(64 * dp);
            WindowManager.LayoutParams lp = new WindowManager.LayoutParams(s, s, typ(),
                    WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE | WindowManager.LayoutParams.FLAG_NOT_TOUCHABLE,
                    PixelFormat.TRANSLUCENT);
            lp.gravity = Gravity.BOTTOM | Gravity.CENTER_HORIZONTAL;
            lp.y = Math.round(48 * dp);
            wm.addView(weg, lp);
        } else if (!ja && weg != null) {
            wm.removeView(weg);
            weg = null;
        }
    }

    /** Liegt Biko gerade über dem ✕? */
    private boolean ueberWeg() {
        DisplayMetrics m = bildschirm();
        float bx = blp.x + blp.width / 2f, by = blp.y + blp.height / 2f;
        float wx = m.widthPixels / 2f, wy = m.heightPixels - 48 * dp - 32 * dp;
        return Math.hypot(bx - wx, by - wy) < 70 * dp;
    }

    private class Ziehen implements View.OnTouchListener {
        private final View huelle;
        private final int schwelle = ViewConfiguration.get(BlaseService.this).getScaledTouchSlop();
        private float startX, startY;
        private int vonX, vonY;
        private boolean zieht;
        private long seit;

        Ziehen(View huelle) { this.huelle = huelle; }

        @Override
        public boolean onTouch(View v, MotionEvent e) {
            switch (e.getActionMasked()) {
                case MotionEvent.ACTION_DOWN:
                    startX = e.getRawX(); startY = e.getRawY();
                    vonX = blp.x; vonY = blp.y;
                    zieht = false;
                    seit = System.currentTimeMillis();
                    v.animate().scaleX(0.93f).scaleY(0.93f).setDuration(120).start();
                    return true;
                case MotionEvent.ACTION_MOVE:
                    float dx = e.getRawX() - startX, dy = e.getRawY() - startY;
                    if (!zieht && Math.hypot(dx, dy) > schwelle) { zieht = true; wegZeigen(true); }
                    if (zieht) {
                        blp.x = vonX + Math.round(dx);
                        blp.y = vonY + Math.round(dy);
                        wm.updateViewLayout(huelle, blp);
                        if (weg != null) {
                            float f = ueberWeg() ? 1.25f : 1f;
                            weg.animate().scaleX(f).scaleY(f).setDuration(120).start();
                        }
                    }
                    return true;
                case MotionEvent.ACTION_UP:
                case MotionEvent.ACTION_CANCEL:
                    v.animate().scaleX(1f).scaleY(1f).setDuration(160).start();
                    if (zieht) {
                        boolean aus = ueberWeg();
                        wegZeigen(false);
                        if (aus) { stopSelf(); return true; }
                        einpassen();
                        anRand(huelle);
                    } else if (e.getActionMasked() == MotionEvent.ACTION_UP) {
                        if (System.currentTimeMillis() - seit > 550) oeffnen(); // lange gedrückt: Biko groß
                        else tippen();
                    }
                    return true;
            }
            return false;
        }
    }

    /** Biko groß, zum Lesen und Schreiben. */
    private void oeffnen() {
        if (!"aus".equals(zustand)) auflegen();
        if (AssistentService.oeffnen()) return; // Biko ist Assistent: dann sieht er auch den Bildschirm
        Intent i = new Intent(this, GespraechActivity.class);
        i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        startActivity(i);
    }

    @Override
    public void onConfigurationChanged(Configuration c) {
        super.onConfigurationChanged(c);
        if (blase == null) return;
        einpassen(); // Tablet gedreht: Biko bleibt auf dem Bildschirm und am Rand
        anRand(blase);
    }

    @Override
    public void onDestroy() {
        laeuft = null;
        if (atmen != null) atmen.cancel();
        wegZeigen(false);
        if (web != null) { web.destroy(); web = null; }
        if (blase != null && blase.isAttachedToWindow()) wm.removeView(blase);
        blase = null;
        super.onDestroy();
    }

    @Override
    public IBinder onBind(Intent i) { return null; }
}
