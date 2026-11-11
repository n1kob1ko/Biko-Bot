package at.biko.helfer;

import android.app.AlarmManager;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.os.Build;
import android.webkit.JavascriptInterface;

import org.json.JSONArray;
import org.json.JSONObject;

/**
 * Biko meldet sich von selbst: zur Erinnerung und zur Morgenrunde, auch wenn die App gerade zu ist.
 * Die Biko-Seite schickt die Zeitpunkte der nächsten zwei Tage (planen), Android weckt die App dann pünktlich.
 * Ist die Blase zu sehen, sagt Biko es gleich selbst. Dazu kommt immer eine Mitteilung.
 */
public class Wecker extends BroadcastReceiver {
    private static final String KANAL = "erinnerung";
    private static final String MELDEN = "at.biko.helfer.MELDEN";
    private static final int ERSTER = 100; // Nummern der Wecker: 100, 101, ...
    private static final int HOECHSTENS = 30;

    /** Für die Biko-Seite (window.BikoWecker). */
    static class Bruecke {
        private final Context c;

        Bruecke(Context c) { this.c = c.getApplicationContext(); }

        @JavascriptInterface
        public void planen(String json) {
            prefs(c).edit().putString("wecker", json).apply(); // nach einem Neustart des Tablets wieder stellen
            stellen(c, json);
        }
    }

    private static SharedPreferences prefs(Context c) {
        return c.getSharedPreferences("biko", Context.MODE_PRIVATE);
    }

    private static PendingIntent wecker(Context c, int nr, Intent i) {
        return PendingIntent.getBroadcast(c, ERSTER + nr, i,
                PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
    }

    /** Alle alten Wecker weg, die neuen stellen. */
    static synchronized void stellen(Context c, String json) {
        AlarmManager am = c.getSystemService(AlarmManager.class);
        SharedPreferences p = prefs(c);
        int alt = p.getInt("wecker_anzahl", 0);
        for (int n = 0; n < alt; n++) am.cancel(wecker(c, n, new Intent(c, Wecker.class).setAction(MELDEN)));
        int n = 0;
        try {
            JSONArray liste = new JSONArray(json == null ? "[]" : json);
            long jetzt = System.currentTimeMillis();
            for (int k = 0; k < liste.length() && n < HOECHSTENS; k++) {
                JSONObject m = liste.getJSONObject(k);
                long wann = m.optLong("wann");
                if (wann <= jetzt) continue; // vorbei (z. B. nach einem Neustart)
                Intent i = new Intent(c, Wecker.class).setAction(MELDEN)
                        .putExtra("art", m.optString("art"))
                        .putExtra("id", m.optString("id"))
                        .putExtra("titel", m.optString("titel", "Biko"))
                        .putExtra("text", m.optString("text"));
                PendingIntent pi = wecker(c, n++, i);
                boolean genau = Build.VERSION.SDK_INT < 31 || am.canScheduleExactAlarms();
                if (genau) am.setExactAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, wann, pi);
                else am.setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, wann, pi);
            }
        } catch (Exception e) { /* kaputte Liste: dann eben keine Wecker */ }
        p.edit().putInt("wecker_anzahl", n).apply();
    }

    @Override
    public void onReceive(Context c, Intent i) {
        String was = i.getAction();
        if (Intent.ACTION_BOOT_COMPLETED.equals(was) || Intent.ACTION_MY_PACKAGE_REPLACED.equals(was)) {
            stellen(c, prefs(c).getString("wecker", "[]"));
            try { BlaseService.starten(c); } catch (Exception e) { /* Android lässt es gerade nicht zu */ }
            return;
        }
        if (!MELDEN.equals(was)) return;
        String art = i.getStringExtra("art"), id = i.getStringExtra("id");
        // Ist Biko groß offen, meldet sich die Seite selbst (mit "Erledigt" und "Später")
        if (Netz.vorne > 0) return;
        BlaseService.melden(art, id, i.getStringExtra("text"));
        mitteilen(c, art, id, i.getStringExtra("titel"), i.getStringExtra("text"));
    }

    private static void mitteilen(Context c, String art, String id, String titel, String text) {
        NotificationManager nm = c.getSystemService(NotificationManager.class);
        NotificationChannel k = new NotificationChannel(KANAL, "Erinnerungen und Morgenrunde",
                NotificationManager.IMPORTANCE_HIGH);
        k.enableVibration(true);
        nm.createNotificationChannel(k);
        // Morgenrunde: Biko kommt als Karte und erzählt. Erinnerung: Biko groß, mit "Erledigt".
        Intent auf = "morgenrunde".equals(art)
                ? new Intent(c, GespraechActivity.class).putExtra("seite", "morgenrunde")
                : new Intent(c, StartActivity.class);
        auf.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        PendingIntent tipp = PendingIntent.getActivity(c, ("tipp" + art + id).hashCode(), auf,
                PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
        Notification n = new Notification.Builder(c, KANAL)
                .setSmallIcon(R.drawable.ic_benachrichtigung)
                .setContentTitle(titel)
                .setContentText(text)
                .setStyle(new Notification.BigTextStyle().bigText(text))
                .setCategory("morgenrunde".equals(art) ? Notification.CATEGORY_EVENT : Notification.CATEGORY_REMINDER)
                .setContentIntent(tipp)
                .setAutoCancel(true)
                .build();
        try {
            nm.notify((art + id).hashCode(), n);
        } catch (SecurityException e) { /* Mitteilungen nicht erlaubt: dann bleibt nur die Blase */ }
    }
}
