import epg_build

# Force the six channels that previously matched empty EPGShare entries
# to known-good IDs with real programme data from japanterebi.
epg_build.EXPLICIT.update({
    "スペースシャワーTV_jp": ["SpaceShowerTV.jp"],
    "WOWOWプラス_jp": ["WOWOWPlus.jp"],
    "カートゥーン-ネットワーク_jp": ["CartoonNetwork.jp"],
    "ホームドラマチャンネル_jp": ["HomeDramaChannel.jp"],
    "チャンネル銀河_jp": ["ChannelGinga.jp"],
    "日テレプラス_jp": ["NipponTVPlus.jp", "NittelePlus.jp"],
})

if __name__ == "__main__":
    epg_build.main()
