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

/**
 * Biko als Blase über allen Apps. Antippen öffnet das Gespräch, ziehen verschiebt ihn,
 * auf das ✕ unten ziehen blendet ihn aus (bis man die App wieder öffnet).
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
    private float dp;
    private int groesse;

    static void starten(Context c) {
        if (!Settings.canDrawOverlays(c)) return;
        Intent i = new Intent(c, BlaseService.class);
        if (Build.VERSION.SDK_INT >= 26) c.startForegroundService(i); else c.startService(i);
    }

    /** Während Biko groß offen ist, braucht es die Blase nicht. */
    static void sichtbar(boolean ja) {
        BlaseService s = laeuft;
        if (s != null && s.blase != null) s.blase.setVisibility(ja ? View.VISIBLE : View.GONE);
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
        if (Build.VERSION.SDK_INT >= 34) startForeground(1, n, ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE);
        else startForeground(1, n);
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
        ImageView bild = new ImageView(this);
        bild.setImageResource(R.drawable.biko);
        bild.setContentDescription("Biko, zum Reden antippen");
        blase.addView(bild, new FrameLayout.LayoutParams(-1, -1));

        int platz = Math.round(12 * dp); // Platz für den Schatten
        blp = new WindowManager.LayoutParams(groesse + 2 * platz, groesse + 2 * platz, typ(),
                WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE | WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS,
                PixelFormat.TRANSLUCENT);
        blp.gravity = Gravity.TOP | Gravity.START;
        FrameLayout huelle = new FrameLayout(this);
        huelle.setPadding(platz, platz, platz, platz);
        huelle.setClipToPadding(false);
        huelle.addView(blase, new FrameLayout.LayoutParams(groesse, groesse));

        SharedPreferences p = getSharedPreferences("biko", MODE_PRIVATE);
        DisplayMetrics m = bildschirm();
        blp.x = p.getBoolean("links", false) ? 0 : m.widthPixels - blp.width;
        blp.y = Math.round(p.getFloat("hoehe", 0.45f) * m.heightPixels);
        einpassen();
        wm.addView(huelle, blp);
        blase.setOnTouchListener(new Ziehen(huelle));
        blase = huelle; // sichtbar() blendet die ganze Hülle aus
        atmenStarten(bild);
    }

    /** Biko atmet ganz leicht, damit er lebendig wirkt. */
    private void atmenStarten(View bild) {
        atmen = ValueAnimator.ofFloat(1f, 1.05f);
        atmen.setDuration(1800);
        atmen.setRepeatMode(ValueAnimator.REVERSE);
        atmen.setRepeatCount(ValueAnimator.INFINITE);
        atmen.addUpdateListener(a -> {
            float f = (float) a.getAnimatedValue();
            bild.setScaleX(f);
            bild.setScaleY(f);
        });
        atmen.start();
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

        Ziehen(View huelle) { this.huelle = huelle; }

        @Override
        public boolean onTouch(View v, MotionEvent e) {
            switch (e.getActionMasked()) {
                case MotionEvent.ACTION_DOWN:
                    startX = e.getRawX(); startY = e.getRawY();
                    vonX = blp.x; vonY = blp.y;
                    zieht = false;
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
                        oeffnen();
                    }
                    return true;
            }
            return false;
        }
    }

    private void oeffnen() {
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
        if (blase != null && blase.isAttachedToWindow()) wm.removeView(blase);
        blase = null;
        super.onDestroy();
    }

    @Override
    public IBinder onBind(Intent i) { return null; }
}
