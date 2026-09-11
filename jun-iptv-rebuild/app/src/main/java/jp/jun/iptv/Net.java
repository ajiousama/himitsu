package jp.jun.iptv;

import java.io.BufferedInputStream;
import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;

public final class Net {
    public static final String UA = "Mozilla/5.0 (Linux; Android TV) AppleWebKit/537.36 Chrome/140 Safari/537.36 JunIPTV/0.3";
    private Net() {}

    public static String text(String url) throws IOException {
        HttpURLConnection c = open(url);
        try (InputStream in = new BufferedInputStream(c.getInputStream());
             BufferedReader br = new BufferedReader(new InputStreamReader(in, StandardCharsets.UTF_8))) {
            StringBuilder sb = new StringBuilder();
            char[] buf = new char[16384];
            int n;
            while ((n = br.read(buf)) != -1) sb.append(buf, 0, n);
            return sb.toString();
        } finally {
            c.disconnect();
        }
    }

    public static InputStream stream(String url) throws IOException {
        return new ConnectionStream(open(url));
    }

    private static HttpURLConnection open(String url) throws IOException {
        URL u = new URL(url);
        for (int hop = 0; hop < 6; hop++) {
            HttpURLConnection c = (HttpURLConnection) u.openConnection();
            c.setConnectTimeout(12000);
            c.setReadTimeout(25000);
            c.setInstanceFollowRedirects(false);
            c.setRequestProperty("User-Agent", UA);
            c.setRequestProperty("Accept", "*/*");
            c.setRequestProperty("Connection", "keep-alive");
            c.connect();
            int code = c.getResponseCode();
            if (code >= 300 && code < 400) {
                String loc = c.getHeaderField("Location");
                c.disconnect();
                if (loc == null) throw new IOException("Redirect without Location");
                u = new URL(u, loc);
                continue;
            }
            if (code < 200 || code >= 300) {
                c.disconnect();
                throw new IOException("HTTP " + code);
            }
            return c;
        }
        throw new IOException("Too many redirects");
    }

    private static final class ConnectionStream extends InputStream {
        private final HttpURLConnection c;
        private final InputStream in;
        ConnectionStream(HttpURLConnection c) throws IOException {
            this.c = c;
            this.in = new BufferedInputStream(c.getInputStream());
        }
        @Override public int read() throws IOException { return in.read(); }
        @Override public int read(byte[] b, int off, int len) throws IOException { return in.read(b, off, len); }
        @Override public void close() throws IOException {
            try { in.close(); } finally { c.disconnect(); }
        }
    }
}
