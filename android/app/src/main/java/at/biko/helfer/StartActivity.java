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
        Netz.vorne++;
        web.onResume();
        BlaseService.sichtbar(false); // Biko ist ja schon groß da
        if (Settings.canDrawOverlays(this)) {
            BlaseService.starten(this);
            assistentAnbieten();
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

    private boolean assistentGefragt;

    /** Biko als Standard-Assistent: Einschaltknopf halten öffnet ihn, und er sieht den Bildschirm. */
    private void assistentAnbieten() {
        if (assistentGefragt || Build.VERSION.SDK_INT < 29) return;
        android.app.role.RoleManager rm = getSystemService(android.app.role.RoleManager.class);
        if (rm == null || rm.isRoleHeld(android.app.role.RoleManager.ROLE_ASSISTANT)) return;
        assistentGefragt = true;
        new AlertDialog.Builder(this)
                .setTitle("Biko als Assistent")
                .setMessage("Dann ist Biko immer bereit: Einschaltknopf gedrückt halten, und Biko hört zu. "
                        + "Er sieht dabei, was gerade auf dem Bildschirm ist, zum Beispiel einen Chat.\n\n"
                        + "Gleich öffnen sich die Einstellungen. Dort unter „Digitaler Assistent“ (oder „Assistent“) "
                        + "„Biko Helfer“ wählen und „Screenshot verwenden“ einschalten.")
                .setPositiveButton("Einstellen", (d, i) -> {
                    try {
                        startActivity(new Intent(Settings.ACTION_MANAGE_DEFAULT_APPS_SETTINGS));
                    } catch (Exception e) {
                        startActivity(new Intent(Settings.ACTION_SETTINGS));
                    }
                })
                .setNegativeButton("Später", null)
                .show();
    }

    @Override
    protected void onPause() {
        Netz.vorne--;
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
