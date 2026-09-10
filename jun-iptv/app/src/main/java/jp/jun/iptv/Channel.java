package jp.jun.iptv;

public class Channel {
    public final String name;
    public final String group;
    public final String tvgId;
    public final String logo;
    public final String url;
    public final String source;
    public volatile String nowProgram = "";
    public volatile String nextProgram = "";

    public Channel(String name, String group, String tvgId, String logo, String url, String source) {
        this.name = name == null ? "" : name.trim();
        this.group = group == null ? "" : group.trim();
        this.tvgId = tvgId == null ? "" : tvgId.trim();
        this.logo = logo == null ? "" : logo.trim();
        this.url = url == null ? "" : url.trim();
        this.source = source == null ? "" : source.trim();
    }
}
