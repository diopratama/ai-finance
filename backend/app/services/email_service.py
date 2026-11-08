import logging
from typing import Optional
import httpx
from app.config import settings

logger = logging.getLogger(__name__)

RESEND_API_URL = "https://api.resend.com/emails"


def _generate_email_html(full_name: str, otp_code: str) -> str:
    display_name = full_name or "Pengguna AI-Finance"
    return f"""<!DOCTYPE html>
<html lang="id">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Verifikasi Akun AI-Finance</title>
</head>
<body style="margin: 0; padding: 0; background-color: #0d1117; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #e6edf3;">
  <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%" style="background-color: #0d1117; padding: 40px 10px;">
    <tr>
      <td align="center">
        <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%" style="max-width: 540px; background-color: #161b22; border-radius: 16px; border: 1px solid #30363d; overflow: hidden; box-shadow: 0 10px 30px rgba(0,0,0,0.5);">
          <!-- Header -->
          <tr>
            <td style="padding: 32px 32px 20px 32px; text-align: center; border-bottom: 1px solid #21262d;">
              <div style="display: inline-block; padding: 8px 16px; background-color: rgba(240, 176, 0, 0.12); border-radius: 20px; border: 1px solid rgba(240, 176, 0, 0.3);">
                <span style="font-size: 18px; font-weight: 700; color: #f0b000; letter-spacing: -0.5px;">AI-Finance</span>
                <span style="font-size: 11px; font-weight: 700; background-color: #f0b000; color: #000000; padding: 2px 6px; border-radius: 4px; margin-left: 6px; text-transform: uppercase;">AI</span>
              </div>
              <h1 style="font-size: 20px; font-weight: 700; color: #ffffff; margin: 16px 0 4px 0;">Verifikasi Alamat Email Anda</h1>
              <p style="font-size: 13px; color: #8b949e; margin: 0;">Smart Wealth, Payday Budgeting & Financial Freedom</p>
            </td>
          </tr>

          <!-- Content -->
          <tr>
            <td style="padding: 32px;">
              <p style="font-size: 15px; color: #c9d1d9; line-height: 1.6; margin-top: 0;">
                Halo <strong>{display_name}</strong>,
              </p>
              <p style="font-size: 14px; color: #8b949e; line-height: 1.6;">
                Terima kasih telah mendaftar di <strong>AI-Finance</strong>. Untuk memastikan keamanan akun Anda, silakan masukkan kode verifikasi 6-digit berikut pada layar registrasi:
              </p>

              <!-- OTP Code Box -->
              <div style="margin: 28px 0; text-align: center;">
                <div style="display: inline-block; padding: 18px 36px; background: linear-gradient(135deg, rgba(240, 176, 0, 0.15), rgba(240, 176, 0, 0.05)); border: 2px dashed #f0b000; border-radius: 12px;">
                  <span style="font-size: 34px; font-weight: 800; letter-spacing: 10px; color: #f0b000; font-family: 'Courier New', Courier, monospace;">{otp_code}</span>
                </div>
              </div>

              <!-- Expiry Alert -->
              <div style="padding: 12px 16px; background-color: rgba(240, 176, 0, 0.08); border-left: 4px solid #f0b000; border-radius: 4px; margin-bottom: 24px;">
                <p style="font-size: 12px; color: #d29922; margin: 0; line-height: 1.5;">
                  ⏱️ <strong>Masa Berlaku:</strong> Kode ini hanya berlaku selama <strong>15 menit</strong>. Jangan berikan kode ini kepada siapapun demi keamanan finansial Anda.
                </p>
              </div>

              <p style="font-size: 13px; color: #8b949e; line-height: 1.5; margin-bottom: 0;">
                Jika Anda tidak merasa mendaftarkan akun di AI-Finance, Anda dapat mengabaikan email ini dengan aman.
              </p>
            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="padding: 20px 32px; background-color: #0d1117; text-align: center; border-top: 1px solid #21262d;">
              <p style="font-size: 11px; color: #6e7681; margin: 0;">
                © 2026 AI-Finance Platform. Dilindungi hak cipta.<br>
                Dioperasikan secara aman di K3s Cluster.
              </p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>
"""


async def send_verification_email(to_email: str, full_name: str, otp_code: str) -> bool:
    """Sends verification OTP email via Resend API or logs OTP in dev mode."""
    api_key = settings.RESEND_API_KEY
    from_email = settings.RESEND_FROM_EMAIL

    if not api_key:
        logger.warning(
            "RESEND_API_KEY not configured. [DEV MODE] Verification OTP for %s (%s): %s",
            to_email,
            full_name,
            otp_code,
        )
        return True

    payload = {
        "from": from_email,
        "to": [to_email],
        "subject": f"Kode Verifikasi AI-Finance: {otp_code}",
        "html": _generate_email_html(full_name, otp_code),
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
            resp = await client.post(RESEND_API_URL, json=payload, headers=headers)
            if resp.status_code in (200, 201):
                logger.info("Resend email sent successfully to %s: %s", to_email, resp.json())
                return True
            else:
                logger.error("Resend API failed [%s]: %s", resp.status_code, resp.text)
                return False
    except Exception as exc:
        logger.error("Failed to send verification email via Resend: %s", exc)
        return False
