# -*- coding: utf-8 -*-
"""otp_flow.py — alur VERIFY NOMOR dan UNBIND NOMOR (ganti nomor).

Diimpor worker.py. Semua request dijalankan di dalam konteks halaman Shopee
supaya csrftoken + fingerprint browser tetap valid.

Endpoint (dari bundle SignupByOTP, sudah diverifikasi):
  1. POST /api/v4/otp/send_vcode
       {phone, channel:1, operation:0, force_channel:false}
  2. POST /api/v4/otp/verify_vcode           {phone, vcode_token, operation:0, vcode}
  3. POST /api/v4/account/management/check_unbind_phone_by_vcode
       {phone, vcode_token, operation:0}
  4. POST /api/v4/account/management/unbind_phone_by_vcode
       {phone, vcode_token, operation:0}
"""

# Satu JS untuk semua langkah — dipanggil dengan `step` berbeda.
OTP_JS = r"""
async (a) => {
  function readCsrf() {
    const m = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
    return m ? m[1] : '';
  }
  let csrf = readCsrf();
  if (!csrf) {
    try {
      await fetch('https://shopee.co.id/api/v4/account/basic/get_account_info',
                  {credentials:'include'});
      csrf = readCsrf();
    } catch(e) {}
  }
  async function post(url, body) {
    const hex = Array.from(crypto.getRandomValues(new Uint8Array(8)))
                    .map(b => b.toString(16).padStart(2,'0')).join('');
    const h = {
      'Content-Type':'application/json','Accept':'application/json',
      'x-api-source':'pc','x-requested-with':'XMLHttpRequest',
      'x-shopee-language':'id','af-ac-enc-dat': hex,
    };
    if (csrf) h['x-csrftoken'] = csrf;
    try {
      const r = await fetch(url, {method:'POST', headers:h,
                                  credentials:'include',
                                  body: JSON.stringify(body)});
      const t = await r.text();
      if (!t) return {__empty:true, _status:r.status};
      const j = JSON.parse(t);
      j._status = r.status;
      return j;
    } catch(e) { return {__exc: String(e)}; }
  }

  const p = a.phone;
  const step = a.step;

  // ---- langkah 1: minta OTP ----
  if (step === 'send') {
    let last = null;
    for (let i = 0; i < 4; i++) {
      const r = await post('/api/v4/otp/send_vcode',
        {phone: p, channel: 1, operation: 0, force_channel: false});
      if (r && typeof r.error === 'number') {
        if (r.error === 0) return {ok:true, step:'send', raw:r,
          seed: (r.data||{}).seed, need_captcha: (r.data||{}).need_captcha};
        last = r;
        // 23500158 = rule engine block; retry sekali kalau challenge
        if (r.error === 90309999) { await new Promise(s=>setTimeout(s,2500)); continue; }
        return {ok:false, step:'send', error:r.error, raw:r};
      }
      last = r || last;
      await new Promise(s => setTimeout(s, 2000));
    }
    return {ok:false, step:'send', error:(last&&last.error)||-1, raw:last};
  }

  // ---- langkah 2: verifikasi kode OTP ----
  if (step === 'verify') {
    const r = await post('/api/v4/otp/verify_vcode',
      {phone: p, vcode_token: a.vcode_token || '', operation: 0,
       vcode: a.vcode});
    const ok = r && typeof r.error === 'number' && r.error === 0;
    return {ok:ok, step:'verify', error:(r&&r.error), raw:r,
            token: (r&&r.data&&(r.data.vcode_token||r.data.token))||''};
  }

  // ---- langkah 3: cek bisa unbind dengan token OTP ----
  if (step === 'check') {
    const r = await post(
      '/api/v4/account/management/check_unbind_phone_by_vcode',
      {phone: p, vcode_token: a.vcode_token || '', operation: 0});
    const ok = r && typeof r.error === 'number' && r.error === 0;
    return {ok:ok, step:'check', error:(r&&r.error), raw:r,
            data:(r&&r.data)||null};
  }

  // ---- langkah 4: eksekusi unbind ----
  if (step === 'unbind') {
    const r = await post(
      '/api/v4/account/management/unbind_phone_by_vcode',
      {phone: p, vcode_token: a.vcode_token || '', operation: 0});
    const ok = r && typeof r.error === 'number' && r.error === 0;
    return {ok:ok, step:'unbind', error:(r&&r.error), raw:r,
            data:(r&&r.data)||null};
  }

  return {ok:false, error:-1, _reason:'step tidak dikenal: ' + step};
}
"""

# Pesan error OTP yang bisa dibaca manusia
OTP_ERR = {
    0: "OK",
    10002: "Token/kode salah atau kedaluwarsa",
    10010: "Fingerprint device tidak valid",
    12301115: "Nomor tidak bisa di-unbind",
    12301116: "Akun/nomor di-restrict",
    12301004: "Kena limit pemakaian nomor",
    12301029: "Akun dibanned",
    12301031: "Nomor daur ulang",
    12301016: "Nomor tidak terdaftar",
    10013: "Nomor tidak ditemukan",
    12301066: "Ada request ganti nomor berjalan",
    12301064: "Cooldown device baru",
    23500158: "Diblokir rule engine (terlalu sering minta OTP)",
    23500153: "Kode OTP salah",
    90309999: "Rate limit / anti-fraud",
    19: "Butuh login (SFU auth)",
}


def otp_msg(code) -> str:
    return OTP_ERR.get(code, f"Error {code}")
