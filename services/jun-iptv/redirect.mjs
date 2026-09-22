export default function handler(req, res) {
  res.setHeader('Cache-Control', 'no-store');
  res.statusCode = 302;
  res.setHeader('Location', 'https://raw.githubusercontent.com/ajiousama/himitsu/jun-iptv-build/jun-iptv/releases/JunIPTV_TS401_latest.apk');
  res.end();
}
