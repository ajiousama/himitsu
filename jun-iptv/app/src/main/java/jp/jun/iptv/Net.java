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
    private Net() {}

    public static String getText(String url) throws IOException {
        HttpURLConnection c = open(url);
        try (InputStream in = new BufferedInputStream(c.getInputStream());
             BufferedReader br = new BufferedReader(new InputStreamReader(in, StandardCharsets.UTF_8))) {
            StringBuilder sb = new StringBuilder();
            char[] buf = new char[8192];
            int n;
            while ((n = br.read(buf)) >= 0) sb.append(buf, 0, n);
            return sb.toString();
        } finally {
            c.disconnect();
        }
    }

    public static InputStream openStream(String url) throws IOException {
        HttpURLConnection c = open(url);
        return new ConnectionInputStream(c);
    }

    private static HttpURLConnection open(String url) throws IOException {
        HttpURLConnection c = (HttpURLConnection) new URL(url).openConnection();
        c.setConnectTimeout(12000);
        c.setReadTimeout(20000);
        c.setInstanceFollowRedirects(true);
        c.setRequestProperty("User-Agent", "JunIPTV/0.1 AndroidTV");
        c.connect();
        int code = c.getResponseCode();
        if (code < 200 || code >= 300) {
            c.disconnect();
            throw new IOException("HTTP " + code + " : " + url);
        }
        return c;
    }

    private static class ConnectionInputStream extends InputStream {
        private final HttpURLConnection connection;
        private final InputStream input;
        ConnectionInputStream(HttpURLConnection c) throws IOException {
            connection = c;
            input = new BufferedInputStream(c.getInputStream());
        }
        public int read() throws IOException { return input.read(); }
        public int read(byte[] b, int off, int len) throws IOException { return input.read(b, off, len); }
        public void close() throws IOException {
            try { input.close(); } finally { connection.disconnect(); }
        }
    }
}
