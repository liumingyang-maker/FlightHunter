import re

label = "香港出发 台湾 HK$800 · 大阪 HK$1500 機票優惠"
dest_pat = (
    r"(大阪|东京|名古屋|冲绳|首尔|釜山|曼谷|普吉|清迈|吉隆坡|新加坡|巴厘岛|河内|胡志明|"
    r"台北|台湾|台中|高雄|香港|澳门|上海|北京|成都|重庆|广州|深圳|杭州|武汉|昆明)"
)
price_pat = r"(MOP\$?\s*|HK\$?\s*|¥\s*|RMB\s*|US\$?\s*)(\d[\d,]{2,})"
pat1 = dest_pat + r"[^\dA-Za-z]{0,24}?" + price_pat
print("pat1 matches:")
for m in re.finditer(pat1, label, re.I):
    print(" ", m.group(0), m.groups())

# try wider gap
pat1b = dest_pat + r"[^\dA-Za-z]{0,40}?" + price_pat
print("pat1b:")
for m in re.finditer(pat1b, label, re.I):
    print(" ", m.groups())

# · might be special?
print(repr(label))
# check each segment
for part in ["台湾 HK$800", "大阪 HK$1500", "台湾 · HK$800"]:
    print(part, bool(re.search(dest_pat + r"[^\dA-Za-z]{0,24}?" + price_pat, part)))
