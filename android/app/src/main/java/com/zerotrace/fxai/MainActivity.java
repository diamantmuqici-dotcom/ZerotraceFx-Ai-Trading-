package com.zerotrace.fxai;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.SharedPreferences;
import android.graphics.Color;
import android.graphics.Typeface;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.text.InputType;
import android.view.Gravity;
import android.view.View;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.Iterator;
import java.util.Locale;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/**
 * ZeroTrace FX AI companion: monitors and controls the desktop engine
 * through its token-protected remote API (REMOTE_API_* in .env).
 */
public class MainActivity extends Activity {

    private static final int BG = Color.parseColor("#0B0F17");
    private static final int CARD = Color.parseColor("#141B26");
    private static final int ACCENT = Color.parseColor("#2EE6A6");
    private static final int RED = Color.parseColor("#FF5C7A");
    private static final int TEXT = Color.parseColor("#E6EDF3");
    private static final int MUTED = Color.parseColor("#8B98A9");

    private final ExecutorService io = Executors.newSingleThreadExecutor();
    private final Handler main = new Handler(Looper.getMainLooper());
    private SharedPreferences prefs;

    private EditText urlInput;
    private EditText tokenInput;
    private TextView statusView;
    private TextView accountView;
    private TextView basketView;
    private TextView signalView;
    private TextView aiView;
    private TextView positionsView;
    private TextView tradesView;
    private Button pauseButton;
    private boolean paused = false;
    private boolean polling = false;

    private final Runnable poller = new Runnable() {
        @Override
        public void run() {
            if (!polling) return;
            refresh();
            main.postDelayed(this, 3000);
        }
    };

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        prefs = getSharedPreferences("zerotrace", MODE_PRIVATE);
        setContentView(buildUi());
    }

    @Override
    protected void onResume() {
        super.onResume();
        if (!prefs.getString("url", "").isEmpty()) startPolling();
    }

    @Override
    protected void onPause() {
        super.onPause();
        polling = false;
        main.removeCallbacks(poller);
    }

    // ---------------------------------------------------------------- UI --
    private View buildUi() {
        ScrollView scroll = new ScrollView(this);
        scroll.setBackgroundColor(BG);
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        int pad = dp(16);
        root.setPadding(pad, dp(28), pad, pad);
        scroll.addView(root);

        TextView title = text("ZeroTrace FX AI", 24, ACCENT, true);
        root.addView(title);
        root.addView(text("Remote monitor & control", 13, MUTED, false));

        LinearLayout conn = card(root);
        urlInput = input("http://192.168.1.10:8765", prefs.getString("url", ""), false);
        tokenInput = input("Remote API token", prefs.getString("token", ""), true);
        conn.addView(label("Desktop address"));
        conn.addView(urlInput);
        conn.addView(label("Token (REMOTE_API_TOKEN)"));
        conn.addView(tokenInput);
        Button connect = button("Connect", ACCENT);
        connect.setOnClickListener(v -> {
            prefs.edit()
                    .putString("url", urlInput.getText().toString().trim())
                    .putString("token", tokenInput.getText().toString().trim())
                    .apply();
            startPolling();
        });
        conn.addView(connect);
        statusView = text("Not connected", 13, MUTED, false);
        conn.addView(statusView);

        accountView = section(root, "Account");
        basketView = section(root, "Basket");
        signalView = section(root, "Last AI decision");
        aiView = section(root, "Adaptive learning");
        positionsView = section(root, "Open positions");
        tradesView = section(root, "Recent trades");

        LinearLayout controls = card(root);
        pauseButton = button("Pause trading", Color.parseColor("#F5B942"));
        pauseButton.setOnClickListener(v -> post("/api/pause",
                "{\"paused\":" + (!paused) + "}", "Pause state updated"));
        controls.addView(pauseButton);
        Button closeAll = button("CLOSE ALL POSITIONS", RED);
        closeAll.setOnClickListener(v -> new AlertDialog.Builder(this)
                .setTitle("Close every position?")
                .setMessage("This immediately closes all open trades on the desktop engine.")
                .setPositiveButton("Close all", (d, w) -> post("/api/close_all", "{}", "Close-all sent"))
                .setNegativeButton("Cancel", null)
                .show());
        controls.addView(closeAll);

        root.addView(text("Trading forex involves substantial risk of loss.", 11, MUTED, false));
        return scroll;
    }

    private LinearLayout card(LinearLayout parent) {
        LinearLayout c = new LinearLayout(this);
        c.setOrientation(LinearLayout.VERTICAL);
        c.setBackgroundColor(CARD);
        c.setPadding(dp(14), dp(12), dp(14), dp(12));
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT);
        lp.topMargin = dp(12);
        parent.addView(c, lp);
        return c;
    }

    private TextView section(LinearLayout parent, String name) {
        LinearLayout c = card(parent);
        c.addView(text(name, 15, ACCENT, true));
        TextView body = text("-", 14, TEXT, false);
        body.setTypeface(Typeface.MONOSPACE);
        c.addView(body);
        return body;
    }

    private TextView text(String s, int sp, int color, boolean bold) {
        TextView t = new TextView(this);
        t.setText(s);
        t.setTextSize(sp);
        t.setTextColor(color);
        if (bold) t.setTypeface(Typeface.DEFAULT_BOLD);
        t.setPadding(0, dp(2), 0, dp(2));
        return t;
    }

    private TextView label(String s) {
        return text(s, 12, MUTED, false);
    }

    private EditText input(String hint, String value, boolean secret) {
        EditText e = new EditText(this);
        e.setHint(hint);
        e.setText(value);
        e.setTextColor(TEXT);
        e.setHintTextColor(MUTED);
        e.setSingleLine(true);
        e.setInputType(secret
                ? InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_PASSWORD
                : InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_URI);
        return e;
    }

    private Button button(String s, int color) {
        Button b = new Button(this);
        b.setText(s);
        b.setTextColor(Color.BLACK);
        b.setBackgroundColor(color);
        b.setGravity(Gravity.CENTER);
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT);
        lp.topMargin = dp(8);
        b.setLayoutParams(lp);
        return b;
    }

    private int dp(int v) {
        return Math.round(v * getResources().getDisplayMetrics().density);
    }

    // ----------------------------------------------------------- network --
    private void startPolling() {
        polling = true;
        main.removeCallbacks(poller);
        main.post(poller);
    }

    private String baseUrl() {
        String u = prefs.getString("url", "").trim();
        if (!u.startsWith("http://") && !u.startsWith("https://")) u = "http://" + u;
        while (u.endsWith("/")) u = u.substring(0, u.length() - 1);
        return u;
    }

    private String request(String method, String path, String body) throws Exception {
        HttpURLConnection c = (HttpURLConnection) new URL(baseUrl() + path).openConnection();
        c.setRequestMethod(method);
        c.setConnectTimeout(5000);
        c.setReadTimeout(15000);
        c.setRequestProperty("Authorization", "Bearer " + prefs.getString("token", ""));
        if (body != null) {
            c.setDoOutput(true);
            c.setRequestProperty("Content-Type", "application/json");
            try (OutputStream os = c.getOutputStream()) {
                os.write(body.getBytes(StandardCharsets.UTF_8));
            }
        }
        int code = c.getResponseCode();
        if (code == 401) throw new Exception("Unauthorized - check token");
        if (code >= 400) throw new Exception("HTTP " + code);
        StringBuilder sb = new StringBuilder();
        try (BufferedReader r = new BufferedReader(
                new InputStreamReader(c.getInputStream(), StandardCharsets.UTF_8))) {
            String line;
            while ((line = r.readLine()) != null) sb.append(line);
        }
        return sb.toString();
    }

    private void refresh() {
        io.execute(() -> {
            try {
                JSONObject s = new JSONObject(request("GET", "/api/status", null));
                JSONObject ai = new JSONObject(request("GET", "/api/ai", null));
                main.post(() -> render(s, ai));
            } catch (Exception e) {
                main.post(() -> {
                    statusView.setText("Connection error: " + e.getMessage());
                    statusView.setTextColor(RED);
                });
            }
        });
    }

    private void post(String path, String body, String okMessage) {
        io.execute(() -> {
            try {
                request("POST", path, body);
                main.post(() -> {
                    statusView.setText(okMessage);
                    refresh();
                });
            } catch (Exception e) {
                main.post(() -> statusView.setText("Action failed: " + e.getMessage()));
            }
        });
    }

    // ------------------------------------------------------------ render --
    private static String money(double v) {
        return String.format(Locale.US, "%,.2f", v);
    }

    private void render(JSONObject s, JSONObject ai) {
        try {
            paused = s.optBoolean("paused");
            pauseButton.setText(paused ? "Resume trading" : "Pause trading");
            boolean kill = s.optBoolean("kill_switch");
            statusView.setTextColor(kill ? RED : ACCENT);
            statusView.setText((kill ? "KILL SWITCH - " : "") + s.optString("mode") + " | "
                    + s.optString("status_message"));

            accountView.setText(
                    "Balance   " + money(s.optDouble("balance")) + "\n"
                    + "Equity    " + money(s.optDouble("equity")) + "\n"
                    + "Floating  " + money(s.optDouble("floating")) + "\n"
                    + "Daily PnL " + money(s.optDouble("daily_pnl")) + "\n"
                    + String.format(Locale.US, "Drawdown  %.2f%%\nWin rate  %.1f%% (%d trades)",
                    s.optDouble("drawdown_pct"), s.optDouble("win_rate"), s.optInt("total_trades")));

            basketView.setText(
                    "Profit " + money(s.optDouble("basket_profit"))
                    + " / target " + money(s.optDouble("basket_target")) + "\n"
                    + "Direction " + s.optString("basket_direction")
                    + (s.optBoolean("trailing_active") ? "  (trailing)" : ""));

            StringBuilder sig = new StringBuilder();
            sig.append(s.optString("active_symbol")).append("  ")
                    .append(s.optString("last_signal"))
                    .append(String.format(Locale.US, "  %.1f%%", s.optDouble("last_confidence")));
            JSONArray reasons = s.optJSONArray("last_reasoning");
            if (reasons != null) {
                for (int i = 0; i < Math.min(8, reasons.length()); i++) {
                    sig.append("\n- ").append(reasons.optString(i));
                }
            }
            signalView.setText(sig.toString());

            StringBuilder a = new StringBuilder();
            a.append("Trades learned  ").append(ai.optInt("trades_learned")).append("\n");
            a.append("Signals scored  ").append(ai.optInt("signals_inspected"))
                    .append(" (rejected ").append(ai.optInt("signals_rejected")).append(")\n");
            JSONObject mult = ai.optJSONObject("multipliers");
            if (mult != null && mult.length() > 0) {
                a.append("Learned weights:");
                Iterator<String> keys = mult.keys();
                while (keys.hasNext()) {
                    String k = keys.next();
                    a.append(String.format(Locale.US, "\n  %-16s x%.2f", k, mult.optDouble(k)));
                }
            }
            JSONObject syms = ai.optJSONObject("symbols");
            if (syms != null && syms.length() > 0) {
                a.append("\nPer-symbol:");
                Iterator<String> keys = syms.keys();
                while (keys.hasNext()) {
                    String k = keys.next();
                    JSONObject o = syms.optJSONObject(k);
                    if (o == null) continue;
                    a.append(String.format(Locale.US, "\n  %-7s %d tr  %.0f%% win  thr %+.1f",
                            k, o.optInt("trades"), o.optDouble("winrate"),
                            o.optDouble("threshold_offset")));
                }
            }
            aiView.setText(a.toString());

            JSONArray pos = s.optJSONArray("open_positions");
            StringBuilder p = new StringBuilder();
            if (pos == null || pos.length() == 0) p.append("No open positions");
            else for (int i = 0; i < pos.length(); i++) {
                JSONObject o = pos.getJSONObject(i);
                if (i > 0) p.append("\n");
                p.append(String.format(Locale.US, "%s %s %.2f @ %s  %s",
                        o.optString("symbol"), o.optString("action"), o.optDouble("volume"),
                        o.optString("entry"), money(o.optDouble("profit"))));
            }
            positionsView.setText(p.toString());

            JSONArray tr = s.optJSONArray("recent_trades");
            StringBuilder t = new StringBuilder();
            if (tr == null || tr.length() == 0) t.append("No closed trades yet");
            else for (int i = 0; i < Math.min(10, tr.length()); i++) {
                JSONObject o = tr.getJSONObject(i);
                if (i > 0) t.append("\n");
                t.append(o.optString("symbol")).append(" ").append(o.optString("action"))
                        .append("  ").append(money(o.optDouble("profit")));
            }
            tradesView.setText(t.toString());
        } catch (Exception e) {
            statusView.setText("Render error: " + e.getMessage());
        }
    }
}
