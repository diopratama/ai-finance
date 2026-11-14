import asyncio
import base64
import json
import logging
import re
from typing import Dict, Any, Optional, AsyncGenerator, Union
import httpx

from app.config import settings
from app.services.planner_skills_loader import build_planner_system_prompt, route_planner_skills
from app.services.planner_tools import (
    PLANNER_TOOLS_SCHEMA,
    describe_planner_tool_call,
    execute_planner_tool,
)
from app.services.web_search_service import (
    format_search_results_for_prompt,
    search_internet,
    should_search_internet,
)

logger = logging.getLogger(__name__)


class RouterService:
    """Client for 9router API (OpenAI-compatible /v1 endpoints)."""

    def __init__(self):
        self.base_url = settings.LLM_BASE_URL.rstrip("/")
        self.api_key = settings.LLM_API_KEY
        self.model = settings.LLM_MODEL_NAME
        self.timeout = settings.LLM_TIMEOUT

    def _headers(self) -> Dict[str, str]:
        headers = {
            "Content-Type": "application/json",
        }
        if self.api_key and self.api_key != "placeholder_key":
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def is_available(self) -> bool:
        return bool(self.base_url and self.base_url.startswith("http"))

    async def parse_receipt_image(self, image_bytes: bytes, mime_type: str = "image/jpeg") -> Dict[str, Any]:
        """Extracts merchant, total amount, date, and items from a receipt image via 9router Vision."""
        prompt = """
        Kamu adalah AI receipt OCR analyzer spesialisasi struk belanja & kasir (Indonesia & Global).
        Analisis gambar struk ini dan kembalikan HANYA format JSON valid tanpa markdown formatting dengan struktur:
        {
          "merchant": "Nama Toko / Restoran",
          "total_amount": 0.0,
          "currency": "IDR" atau "USD",
          "date": "YYYY-MM-DD" atau null,
          "items": [{"name": "item", "price": 0.0}],
          "category_suggestion": "Makanan & Minuman" atau "Belanja" atau "Kesehatan" atau "Lain-lain"
        }
        """

        if not self.is_available():
            raise RuntimeError("Layanan AI Vision 9router belum terkonfigurasi. Silakan input transaksi manual.")

        try:
            b64_image = base64.b64encode(image_bytes).decode("utf-8")
            payload = {
                "model": self.model,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:{mime_type};base64,{b64_image}"
                                },
                            },
                        ],
                    }
                ],
                "temperature": 0.1,
            }

            url = f"{self.base_url}/chat/completions"
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                res = await client.post(url, json=payload, headers=self._headers())
                if res.status_code != 200:
                    logger.error("9router vision error: %s - %s", res.status_code, res.text)
                    raise RuntimeError(f"Gagal memproses struk via AI Vision (status {res.status_code}).")

                res_json = res.json()
                raw_text = res_json["choices"][0]["message"]["content"].strip()

                clean_json = re.sub(r"^```(?:json)?\n", "", raw_text)
                clean_json = re.sub(r"\n```$", "", clean_json)
                return json.loads(clean_json)

        except Exception as e:
            logger.error("Failed to parse receipt with 9router: %s", e)
            raise RuntimeError(f"Gagal membaca struk belanja: {e}")

    async def transcribe_audio_note(self, audio_bytes: bytes, mime_type: str = "audio/ogg") -> str:
        """Transcribes audio notes into text via 9router audio endpoint."""
        if not self.is_available():
            raise RuntimeError("Layanan transkripsi suara belum terkonfigurasi. Silakan ketik transaksi dalam teks.")

        try:
            url = f"{self.base_url}/audio/transcriptions"
            files = {"file": ("audio.ogg", audio_bytes, mime_type)}
            data = {"model": "whisper-1"}
            headers = {}
            if self.api_key and self.api_key != "placeholder_key":
                headers["Authorization"] = f"Bearer {self.api_key}"

            async with httpx.AsyncClient(timeout=self.timeout) as client:
                res = await client.post(url, files=files, data=data, headers=headers)
                if res.status_code == 200:
                    text = res.json().get("text", "").strip()
                    if text:
                        return text
        except Exception as e:
            logger.warning("9router audio transcription error: %s", e)
            raise RuntimeError(f"Gagal mentranskripsi pesan suara: {e}")

        raise RuntimeError("Transkripsi suara tidak menghasilkan teks. Silakan coba lagi atau ketik secara manual.")

    async def generate_planner_response_stream(
        self,
        conversation_history: list[dict],
        financial_context: dict,
        routing: Optional[dict] = None,
        user_id: Optional[str] = None,
        emit_status: bool = False,
    ) -> AsyncGenerator[Union[str, Dict[str, str]], None]:
        """Streams conversational guidance with hybrid LLM tool-calling + modular AI Financial Planner skills via 9router."""
        latest_user_msg = ""
        for item in reversed(conversation_history):
            if item.get("role") == "user":
                latest_user_msg = item.get("content", "")
                break

        active_routing = routing or route_planner_skills(latest_user_msg, conversation_history)

        web_search_context = ""
        if should_search_internet(latest_user_msg):
            if emit_status:
                yield {"status": "Mengambil data pasar & berita terkini..."}
            try:
                results = await asyncio.to_thread(search_internet, latest_user_msg, 4)
                web_search_context = format_search_results_for_prompt(results)
            except Exception as e:
                logger.debug("Live web search notice: %s", e)
                web_search_context = format_search_results_for_prompt([])

        system_instruction = build_planner_system_prompt(
            financial_context,
            active_routing,
            web_search_context=web_search_context,
        )

        messages_payload: list[dict[str, Any]] = [{"role": "system", "content": system_instruction}]
        for m in conversation_history:
            messages_payload.append(
                {
                    "role": m.get("role", "user"),
                    "content": m.get("content", ""),
                }
            )

        url = f"{self.base_url}/chat/completions"

        def _emit_chunk(text: str) -> Union[str, Dict[str, str]]:
            return {"chunk": text} if emit_status else text

        # Phase 1: Hybrid Tool-Calling Loop (max 3 iterations)
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                for _ in range(3):
                    tool_payload = {
                        "model": self.model,
                        "messages": messages_payload,
                        "tools": PLANNER_TOOLS_SCHEMA,
                        "tool_choice": "auto",
                        "stream": False,
                        "temperature": 0.65,
                    }
                    res = await client.post(url, json=tool_payload, headers=self._headers())
                    if res.status_code in (400, 404, 422):
                        # Provider/model does not support tools; fall back to standard streaming
                        logger.info("9router tools unsupported (HTTP %s); falling back to standard stream", res.status_code)
                        break
                    if res.status_code != 200:
                        logger.error("9router tool-calling error: %s %s", res.status_code, res.text)
                        yield _emit_chunk(
                            f"Maaf, koneksi ke 9router AI sedang terkendala (HTTP {res.status_code}). Coba kirim ulang sebentar lagi ya."
                        )
                        return

                    res_json = res.json()
                    msg = (res_json.get("choices") or [{}])[0].get("message") or {}
                    tool_calls = msg.get("tool_calls") or []
                    if tool_calls:
                        messages_payload.append(
                            {
                                "role": "assistant",
                                "content": msg.get("content") or "",
                                "tool_calls": tool_calls,
                            }
                        )
                        for idx, tc in enumerate(tool_calls):
                            fn = tc.get("function") or {}
                            fn_name = fn.get("name", "")
                            raw_args = fn.get("arguments") or "{}"
                            try:
                                fn_args = json.loads(raw_args) if isinstance(raw_args, str) else dict(raw_args)
                            except Exception:
                                fn_args = {}
                            if emit_status:
                                yield {"status": describe_planner_tool_call(fn_name, fn_args)}
                            _, tool_result = await asyncio.to_thread(
                                execute_planner_tool, fn_name, fn_args, user_id
                            )
                            messages_payload.append(
                                {
                                    "role": "tool",
                                    "tool_call_id": tc.get("id") or f"call_{idx}_{fn_name}",
                                    "name": fn_name,
                                    "content": tool_result,
                                }
                            )
                        continue

                    final_text = (msg.get("content") or "").strip()
                    if final_text:
                        yield _emit_chunk(final_text)
                        return
                    break
        except Exception as e:
            logger.error("9router tool-calling exception: %s", e)
            # Fall through to standard streaming / offline snapshot fallback below

        # Phase 2: Standard Streaming (after tool loop or tool fallback)
        payload = {
            "model": self.model,
            "messages": messages_payload,
            "stream": True,
            "temperature": 0.65,
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                async with client.stream("POST", url, json=payload, headers=self._headers()) as response:
                    if response.status_code != 200:
                        err_body = await response.aread()
                        logger.error(
                            "9router streaming error: %s %s",
                            response.status_code,
                            err_body.decode("utf-8", errors="ignore"),
                        )
                        yield _emit_chunk(
                            f"Maaf, koneksi ke 9router AI sedang terkendala (HTTP {response.status_code}). Coba kirim ulang sebentar lagi ya."
                        )
                        return

                    async for line in response.aiter_lines():
                        line = line.strip()
                        if not line or not line.startswith("data:"):
                            continue
                        data_str = line[5:].strip()
                        if data_str == "[DONE]":
                            break
                        try:
                            chunk_data = json.loads(data_str)
                            delta = chunk_data.get("choices", [{}])[0].get("delta", {})
                            content_piece = delta.get("content", "")
                            if content_piece:
                                yield _emit_chunk(content_piece)
                        except json.JSONDecodeError:
                            continue

        except Exception as e:
            logger.error("9router stream exception: %s", e)
            net_worth = financial_context.get("net_worth_formatted", "Rp 0")
            ef_months = financial_context.get("emergency_fund_months", 0)
            ef_target = financial_context.get("emergency_target_months", 3)
            fallback_parts = [
                f"Saat ini koneksi ke engine 9router sedang tidak terjangkau, tapi aku tetap bisa bantu baca snapshot dompetmu. Total aset terdatatmu ada di **{net_worth}** dengan dana darurat sekitar **{ef_months} dari target {ef_target} bulan** pengeluaran.\n\n",
                "Sambil menunggu koneksi AI pulih, mau kita fokus beresin bantalan dana darurat dulu atau cek pos anggaran bulan ini?",
            ]
            for part in fallback_parts:
                yield _emit_chunk(part)
                await asyncio.sleep(0.03)

    async def generate_cfp_response_stream(
        self,
        conversation_history: list[dict],
        financial_context: dict,
    ) -> AsyncGenerator[str, None]:
        """Backward-compatible alias delegating to generate_planner_response_stream."""
        async for chunk in self.generate_planner_response_stream(conversation_history, financial_context):
            yield chunk

    async def generate_planner_response(
        self,
        conversation_history: list[dict],
        financial_context: dict,
        routing: Optional[dict] = None,
        user_id: Optional[str] = None,
    ) -> str:
        """Generates a complete non-streaming response for Telegram/WhatsApp bot users."""
        chunks: list[str] = []
        async for chunk in self.generate_planner_response_stream(
            conversation_history, financial_context, routing, user_id=user_id, emit_status=False
        ):
            if isinstance(chunk, str):
                chunks.append(chunk)
        return "".join(chunks).strip()


router_service = RouterService()
