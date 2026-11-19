# -*- coding: utf-8 -*-
"""change_phone_engine.py — ganti nomor Shopee by cookie.

FLOW YANG SUDAH TERVERIFIKASI (RE live pakai cookie Maker):

  A. Cookie valid -> get_account_info error:0 (dapat userid/username/phone)
  B. POST /api/v4/account/management/change_phone_init
       {} -> {seq_no, auth_required:[1]}
       auth_required[1] = ChangePhone (enum: 0=Na,1=ChangePhone,2=Login,
                                          3=DeleteAccount,4=ChangePassword,
                                          5=DeleteCreditCard)
  C. GET  /api/v4/account/management/get_password_verify_method?seq_no=X&scenario=1
       -> {verify_method: N}
       N=1 OTP, N=2 PASSWORD, N=3 SHOPEEPAY PIN (mapping dari UI Shopee)
  D. POST /api/v4/account/management/verify_payment_commit
       {seq_no, answer, scenario:1} -> error 0 = lolos verifikasi
       answer untuk password dienkripsi di sisi UI (butuh kunci RSA dari
       halaman) — ini yang belum ketemu endpoint publiknya.
  E. POST /api/v4/otp/get_settings_v2
       {operation, encrypted_phone, phone, supported_channels, support_session}
       -> daftar channel yang tersedia (SMS / WhatsApp / Viber / Zalo)
  F. POST /api/v4/otp/send_vcode
       {phone, channel, operation:0, force_channel, m_token}
       channel: 1=SMS, 2=WhatsApp  (a.pH.SMS / a.pH.WhatsApp)
  G. POST /api/v4/otp/verify_vcode {phone, vcode, vcode_token, operation:0}
  H. POST /api/v4/account/management/change_phone_precheck_v2 {phone}
  I. POST /api/v4/account/management/change_phone_commit_v2
       {change_phone_token, new_phone, vcode_token, ivs_signature, ivs_method}

Status RE: A,B,C,E,F,G terverifikasi. D butuh enkripsi answer (RSA),
H/I butuh ivs_signature dari SDK IVS Shopee.
"""
from __future__ import annotations

import json
import hashlib
import base64

# --- enum dari bundle Shopee ---
AUTH_SCENARIO = {0: "Na", 1: "ChangePhone", 2: "Login",
                 3: "DeleteAccount", 4: "ChangePassword",
                 5: "DeleteCreditCard"}

VERIFY_METHOD = {1: "OTP", 2: "PASSWORD", 3: "SHOPEEPAY_PIN"}

OTP_CHANNEL = {1: "SMS", 2: "WHATSAPP", 3: "VIBER", 4: "ZALO"}

ERR = {
    0: "OK",
    10002: "Parameter salah / token kedaluwarsa",
    10010: "Fingerprint device tidak valid",
    10013: "Nomor tidak ditemukan",
    12301004: "Kena limit pemakaian nomor",
    12301016: "Nomor tidak terdaftar",
    12301029: "Akun dibanned",
    12301031: "Nomor daur ulang",
    12301064: "Cooldown device baru",
    12301066: "Ada request ganti nomor berjalan",
    12301115: "Nomor tidak bisa di-unbind",
    12301116: "Akun/nomor restrict",
    23500153: "Kode OTP salah",
    23500158: "Diblokir rule engine",
    90309999: "Rate limit / anti-fraud",
    0xbbb2ca: "User tidak ada",
    0xbbb2cb: "Status akun tidak normal",
    0xbbb2cc: "Nomor kena limit pemakaian",
    0xbbb2d2: "Akun tidak punya password",
    0xbbb2d8: "Nomor tidak terdaftar",
    0xbbb2d9: "Nomor sudah dipakai",
    0xbbb2da: "Metode verifikasi tidak tersedia",
    0xbbb2db: "Verifikasi duplikat",
    0xbbb2dc: "Jawaban verifikasi salah",
    0xbbb2df: "Token kedaluwarsa",
    0xbbb2e0: "Akun merchant ShopeePay",
}


def err_msg(code):
    return ERR.get(code, f"Error {code}")


# JS yang di-inject ke halaman Shopee (browser context sudah login by cookie)
ENGINE_JS = r"""
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
  async function req(url, body, method) {
    const hex = Array.from(crypto.getRandomValues(new Uint8Array(8)))
                    .map(b => b.toString(16).padStart(2,'0')).join('');
    const h = {'Accept':'application/json','x-api-source':'pc',
      'x-requested-with':'XMLHttpRequest','x-shopee-language':'id',
      'af-ac-enc-dat': hex};
    if (method !== 'GET') h['Content-Type'] = 'application/json';
    if (csrf) h['x-csrftoken'] = csrf;
    const opt = {method: method || 'POST', headers: h, credentials:'include'};
    if (method !== 'GET' && body !== null && body !== undefined)
      opt.body = JSON.stringify(body);
    try {
      const r = await fetch(url, opt);
      const t = await r.text();
      if (!t) return {__empty:true, _status:r.status};
      const j = JSON.parse(t);
      j._status = r.status;
      return j;
    } catch(e) { return {__exc:String(e)}; }
  }

  const step = a.step;
  const p = a.phone || '';

  // 1. info akun
  if (step === 'account')
    return await req('/api/v4/account/basic/get_account_info', null, 'GET');

  // 2. mulai flow ganti nomor -> seq_no
  if (step === 'init') {
    const v1 = await req('/api/v4/account/management/change_phone_init', {});
    if (v1 && v1.error === 0 && v1.data && v1.data.seq_no) {
      return {ok:true, kind:'v1', seq_no: v1.data.seq_no,
              auth_required: v1.data.auth_required, raw: v1};
    }
    const v2 = await req('/api/v4/account/management/change_phone_init_v2', {});
    return {ok: !!(v2 && v2.error === 0), kind:'v2', raw: v2,
            ivs_required: (v2.data||{}).ivs_required,
            ivs_utoken: (v2.data||{}).ivs_utoken,
            change_phone_token: (v2.data||{}).change_phone_token};
  }

  // 3. metode verifikasi yang diminta
  if (step === 'methods') {
    const r = await req('/api/v4/account/management/get_password_verify_method'
                        + '?seq_no=' + encodeURIComponent(a.seq_no)
                        + '&scenario=1', null, 'GET');
    return {ok: !!(r && r.error === 0), verify_method:(r.data||{}).verify_method,
            raw: r};
  }


  // 3b. inisialisasi verifikasi (WAJIB sebelum commit)
  if (step === 'verify_init') {
    const r = await req('/api/v4/account/management/verify_payment_init',
      {seq_no: a.seq_no, scenario: 1});
    return {ok: !!(r && r.error === 0), error: r && r.error, raw: r,
            data: (r&&r.data)||null};
  }

  // 4. kirim jawaban verifikasi (password / pin)
  if (step === 'verify') {
    const r = await req('/api/v4/account/management/verify_payment_commit',
      {seq_no: a.seq_no, answer: a.answer, scenario: 1});
    return {ok: !!(r && r.error === 0), error: r && r.error, raw: r,
            data: (r&&r.data)||null};
  }

  // 5. daftar channel OTP untuk nomor baru
  if (step === 'channels') {
    const body = {operation: 0, phone: p, supported_channels: [1,2],
                  support_session: false};
    const r = await req('/api/v4/otp/get_settings_v2', body);
    return {ok: !!(r && r.error === 0), error: r && r.error, raw: r,
            data: (r&&r.data)||null};
  }

  // 6. kirim OTP ke nomor baru
  if (step === 'send') {
    const ch = a.channel || 1;
    const body = {phone: p, channel: ch, operation: 0, force_channel: false,
                  supported_channels: a.supported_channels || [ch],
                  seed: a.seed || a.m_token || ''};
    if (a.m_token) body.m_token = a.m_token;
    if (a.captcha_signature) body.captcha_signature = a.captcha_signature;
    if (a.captcha_id) body.captcha_id = a.captcha_id;
    const r = await req('/api/v4/otp/send_vcode', body);
    return {ok: !!(r && r.error === 0), error: r && r.error, raw: r,
            seed: (r&&r.data&&(r.data.seed||r.data.otp_tracking_id))||'',
            channels: (r&&r.data&&r.data.available_channels)||[],
            need_captcha: (r&&r.data&&r.data.need_captcha)||false};
  }

  // 7. verifikasi OTP nomor baru
  if (step === 'verify_otp') {
    const r = await req('/api/v4/otp/verify_vcode',
      {phone: p, vcode: a.vcode, vcode_token: a.vcode_token || '',
       operation: 0});
    return {ok: !!(r && r.error === 0), error: r && r.error, raw: r,
            token: (r&&r.data&&(r.data.vcode_token||r.data.token))||''};
  }

  // 8. precheck nomor baru
  if (step === 'precheck') {
    const r = await req('/api/v4/account/management/change_phone_precheck_v2',
      {phone: p});
    return {ok: !!(r && r.error === 0), error: r && r.error, raw: r,
            data: (r&&r.data)||null};
  }

  // 9. commit ganti nomor
  if (step === 'commit') {
    const r = await req('/api/v4/account/management/change_phone_commit_v2',
      {change_phone_token: a.change_phone_token, new_phone: p,
       vcode_token: a.vcode_token, ivs_signature: a.ivs_signature || '',
       ivs_method: a.ivs_method || ''});
    return {ok: !!(r && r.error === 0), error: r && r.error, raw: r,
            data: (r&&r.data)||null};
  }

  return {ok:false, error:-1, _reason:'step tidak dikenal: ' + step};
}
"""


def parse_cookie(raw: str) -> list:
    out = []
    for part in raw.replace("\n", ";").split(";"):
        part = part.strip()
        if "=" in part:
            k, v = part.split("=", 1)
            out.append({"name": k.strip(), "value": v.strip(),
                        "domain": ".shopee.co.id", "path": "/"})
    return out
