package at.biko.helfer;

import android.Manifest;
import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.provider.Settings;
import android.webkit.WebView;

import java.util.ArrayList;
import java.util.List;

/**
 * Was man sieht, wenn man das Biko-Symbol antippt: Biko groß.
 * Beim ersten Mal fragt die App nach den Erlaubnissen und schaltet dann die schwebende Blase ein.
 */
public class StartActivity extends Activity {
    private WebView web;
    private boolean gefragt; // nur einmal pro Start nach "Über anderen Apps" fragen

    @Override
    protected void onCreate(Bundle b) {
        super.onCreate(b);
        web = Netz.bauen(this);
        setContentView(web);
        if (b != null) web.restoreState(b);
        else web.loadUrl(BuildConfig.BIKO_ADRESSE);
        erlaubnisseHolen();
    }

    private void erlaubnisseHolen() {
        List<String> fehlt = new ArrayList<>();
        if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
            fehlt.add(Manifest.permission.RECORD_AUDIO);
        }
        if (Build.VERSION.SDK_INT >= 33
                && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
            fehlt.add(Manifest.permission.POST_NOTIFICATIONS);
        }
        if (!fehlt.isEmpty()) requestPermissions(fehlt.toArray(new String[0]), 1);
    }

    @Override
    protected void onResume() {
        super.onResume();
        web.onResume();
        BlaseService.sichtbar(false); // Biko ist ja schon groß da
        if (Settings.canDrawOverlays(this)) {
            BlaseService.starten(this);
        } else if (!gefragt) {
            gefragt = true;
            new AlertDialog.Builder(this)
                    .setTitle("Biko immer dabei")
                    .setMessage("Damit Biko als kleine Blase über anderen Apps schweben kann, braucht er eine Erlaubnis.\n\n"
                            + "Gleich öffnen sich die Einstellungen. Dort bei „Biko Helfer“ den Schalter einschalten "
                            + "und dann zurück.")
                    .setPositiveButton("Erlauben", (d, i) -> startActivity(new Intent(
                            Settings.ACTION_MANAGE_OVERLAY_PERMISSION, Uri.parse("package:" + getPackageName()))))
                    .setNegativeButton("Später", null)
                    .show();
        }
    }

    @Override
    protected void onPause() {
        web.onPause(); // legt auf, wie beim Weglegen in der Web-App
        Netz.sichern();
        super.onPause();
    }

    @Override
    protected void onStop() {
        BlaseService.sichtbar(true);
        super.onStop();
    }

    @Override
    protected void onSaveInstanceState(Bundle b) {
        super.onSaveInstanceState(b);
        web.saveState(b);
    }

    @Override
    public void onBackPressed() {
        if (web.canGoBack()) web.goBack();
        else super.onBackPressed();
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
