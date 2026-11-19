#!/bin/bash
# auto_run.sh — cek window generate, kalau buka langsung gas FINAL_OTP
cd /root/shopee-verify || exit 1
LOG=/root/shopee-verify/AUTO.log
for i in $(seq 1 40); do
  echo "[$(date '+%H:%M:%S')] attempt $i: cek window" >> "$LOG"
  RES=$(timeout 90 /root/sniffenv/bin/python3 - <<'PY' 2>&1
import json,base64,hashlib,os,requests
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
K=b"dRgUkXp2r5u8x/A?D(G+KbPeShVmYq3t"
def evp(pw,salt):
    d,prev=b"",b""
    while len(d)<48: prev=hashlib.md5(prev+pw+salt).digest(); d+=prev
    return d[:32],d[32:48]
def enc(o):
    salt=os.urandom(8); k,iv=evp(K,salt)
    return base64.b64encode(b"Salted__"+salt+AES.new(k,AES.MODE_CBC,iv).encrypt(pad(json.dumps(o,separators=(",",":")).encode(),16))).decode()
def dec(b):
    try:
        raw=base64.b64decode(b)
        if not raw.startswith(b"Salted__"): return {"_plain":raw[:100].decode("utf8","ignore")}
        k,iv=evp(K,raw[8:16])
        return json.loads(__import__("Crypto.Util.Padding",fromlist=["unpad"]).unpad(AES.new(k,AES.MODE_CBC,iv).decrypt(raw[16:]),16))
    except Exception as e: return {"_err":str(e)[:40]}
ck=open("ck_new234.txt").read().strip()
c={p.split("=",1)[0].strip():p.split("=",1)[1].strip() for p in ck.split(";") if "=" in p}
s=requests.Session(); s.cookies.update(c)
s.proxies={"http":"http://127.0.0.1:18080","https":"http://127.0.0.1:18080"}
s.headers.update({"user-agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36","x-api-source":"pc","af-ac-enc-dat":"0123456789abcdef","x-sz-sdk-version":"1.12.45","x-requested-with":"XMLHttpRequest","referer":"https://shopee.co.id/","accept":"application/json","content-type":"application/json"})
TRK=open("TRK_OS.txt").read().strip()
p={"app_key":"FlashSale.PC","scene":"crawler_item","captcha_type":1,"image_version":"","client_id":c.get("SPC_CLIENTID",""),"captcha_extra_info":{"tracking_id":TRK},"captcha_id":""}
r=s.post("https://shopee.co.id/api/v4/anti_fraud/captcha/generate",json={"encrypted_data":enc(p)},timeout=50)
j=r.json(); d=dec(j["encrypted_data"]) if j.get("encrypted_data") else j
print(d.get("error"))
PY
)
  echo "  -> $RES" >> "$LOG"
  if [ "$RES" = "0" ]; then
    echo "[$(date '+%H:%M:%S')] ✅ WINDOW BUKA — gas FINAL_OTP" >> "$LOG"
    timeout 540 xvfb-run -a --server-args="-screen 0 1366x900x24" \
      /root/sniffenv/bin/python3 FINAL_OTP.py ck_new234.txt 6282323737822 >> "$LOG" 2>&1
    if grep -q "OTP TERKIRIM" "$LOG"; then
      echo "[$(date '+%H:%M:%S')] 🎉🎉🎉 OTP SENT" >> "$LOG"
      exit 0
    fi
    echo "[$(date '+%H:%M:%S')] verify gagal, lanjut nunggu" >> "$LOG"
  fi
  sleep 360
done
echo "[$(date '+%H:%M:%S')] timeout 4 jam" >> "$LOG"
