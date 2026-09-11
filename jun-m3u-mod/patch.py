#!/usr/bin/env python3
import os
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

if len(sys.argv) != 2:
    raise SystemExit("usage: patch.py <apktool-decoded-dir>")

root_dir = Path(sys.argv[1])
manifest = root_dir / "AndroidManifest.xml"
ANDROID = "http://schemas.android.com/apk/res/android"
ET.register_namespace("android", ANDROID)

tree = ET.parse(manifest)
root = tree.getroot()
old_pkg = root.attrib.get("package", "de.herber_edevelopment.m3uiptv")
new_pkg = "jp.jun.iptv"
root.set("package", new_pkg)

# Bundle/split-only flags prevent a rebuilt base APK from installing alone.
for key in list(root.attrib):
    local = key.split("}")[-1]
    if local in {"requiredSplitTypes", "splitTypes", "isSplitRequired"}:
        del root.attrib[key]

app = root.find("application")
if app is not None:
    app.set(f"{{{ANDROID}}}label", "Jun IPTV")
    # The ABI split libraries are merged into the rebuilt APK. Extraction avoids
    # page-alignment requirements of the original app-bundle split.
    app.set(f"{{{ANDROID}}}extractNativeLibs", "true")

    for child in list(app):
        if child.tag == "meta-data":
            n = child.attrib.get(f"{{{ANDROID}}}name", "")
            if n in {"com.android.vending.splits", "com.android.vending.splits.required"}:
                app.remove(child)

# Keep original Java/Kotlin class names, but make package-scoped authorities and
# generated permissions unique so the stock app can remain installed alongside Jun IPTV.
for elem in root.iter():
    tag = elem.tag.split("}")[-1]
    for attr, value in list(elem.attrib.items()):
        local = attr.split("}")[-1]
        if not isinstance(value, str) or old_pkg not in value:
            continue
        if local in {"authorities", "taskAffinity", "permission"}:
            elem.set(attr, value.replace(old_pkg, new_pkg))
        elif local == "name" and tag in {"permission", "uses-permission"} and value.startswith(old_pkg + "."):
            elem.set(attr, value.replace(old_pkg, new_pkg, 1))

# Write a normal text manifest for apktool to compile.
tree.write(manifest, encoding="utf-8", xml_declaration=True)

# Patch only exact package/authority string constants. Do not rename class descriptors;
# the actual implementation classes deliberately stay in the vendor namespace.
safe_literals = {
    old_pkg: new_pkg,
    old_pkg + ".androidx-startup": new_pkg + ".androidx-startup",
    old_pkg + ".mobileadsinitprovider": new_pkg + ".mobileadsinitprovider",
    old_pkg + ".DYNAMIC_RECEIVER_NOT_EXPORTED_PERMISSION": new_pkg + ".DYNAMIC_RECEIVER_NOT_EXPORTED_PERMISSION",
}
for smali_dir in root_dir.glob("smali*"):
    if not smali_dir.is_dir():
        continue
    for p in smali_dir.rglob("*.smali"):
        text = p.read_text(encoding="utf-8", errors="ignore")
        changed = text
        for src, dst in safe_literals.items():
            changed = changed.replace('"' + src + '"', '"' + dst + '"')
        if changed != text:
            p.write_text(changed, encoding="utf-8")

print(f"patched package {old_pkg} -> {new_pkg}")
print("kept implementation classes in original namespace")
