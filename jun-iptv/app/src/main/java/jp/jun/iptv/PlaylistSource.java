package jp.jun.iptv;

public class PlaylistSource {
    public enum Filter { TV, ALL }

    public final String name;
    public final String m3uUrl;
    public final String epgUrl;
    public final Filter filter;

    public PlaylistSource(String name, String m3uUrl, String epgUrl, Filter filter) {
        this.name = name;
        this.m3uUrl = m3uUrl;
        this.epgUrl = epgUrl;
        this.filter = filter;
    }
}
