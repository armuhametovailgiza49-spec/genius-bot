"""
Парсер файлов: извлекает текст из PDF, DOCX, TXT, изображений.
Использует только лёгкие библиотеки без тяжёлых зависимостей.
"""
import os
import io
import logging
from typing import Tuple

logger = logging.getLogger(__name__)


async def extract_text(file_bytes: bytes, filename: str) -> Tuple[str, str]:
    """
    Возвращает (extracted_text, file_type).
    file_type: 'pdf' | 'docx' | 'txt' | 'image' | 'unknown'
    """
    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""

    if ext == "pdf":
        return await _extract_pdf(file_bytes), "pdf"
    elif ext in ("docx", "doc"):
        return await _extract_docx(file_bytes), "docx"
    elif ext in ("txt", "md", "csv"):
        return file_bytes.decode("utf-8", errors="replace"), "txt"
    elif ext in ("png", "jpg", "jpeg", "webp"):
        return await _extract_image(file_bytes), "image"
    elif ext in ("xlsx", "xls"):
        return await _extract_xlsx(file_bytes), "xlsx"
    else:
        # Пробуем как текст
        try:
            return file_bytes.decode("utf-8", errors="replace"), "txt"
        except Exception:
            return "", "unknown"


async def _extract_pdf(data: bytes) -> str:
    try:
        import pypdf
        reader = pypdf.PdfReader(io.BytesIO(data))
        pages = []
        for page in reader.pages[:50]:  # максимум 50 страниц
            text = page.extract_text()
            if text:
                pages.append(text.strip())
        return "\n\n".join(pages)
    except ImportError:
        logger.warning("pypdf не установлен")
        return "[PDF: для чтения нужна библиотека pypdf]"
    except Exception as e:
        logger.error(f"PDF parse error: {e}")
        return f"[Не удалось прочитать PDF: {e}]"


async def _extract_docx(data: bytes) -> str:
    try:
        import docx
        doc = docx.Document(io.BytesIO(data))
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        return "\n\n".join(paragraphs)
    except ImportError:
        logger.warning("python-docx не установлен")
        return "[DOCX: для чтения нужна библиотека python-docx]"
    except Exception as e:
        logger.error(f"DOCX parse error: {e}")
        return f"[Не удалось прочитать DOCX: {e}]"


async def _extract_image(data: bytes) -> str:
    """Отправляет изображение в Claude Vision для OCR."""
    import base64
    import httpx
    import os

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return "[Изображение: нужен ANTHROPIC_API_KEY для распознавания текста]"

    try:
        b64 = base64.standard_b64encode(data).decode()
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json"
                },
                json={
                    "model": "claude-haiku-4-5-20251001",
                    "max_tokens": 2000,
                    "messages": [{
                        "role": "user",
                        "content": [
                            {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": b64}},
                            {"type": "text", "text": "Извлеки весь текст с этого изображения. Верни только текст, без пояснений."}
                        ]
                    }]
                }
            )
        if resp.status_code == 200:
            return resp.json()["content"][0]["text"]
        return "[Не удалось распознать текст на изображении]"
    except Exception as e:
        logger.error(f"Image OCR error: {e}")
        return f"[Ошибка OCR: {e}]"


async def _extract_xlsx(data: bytes) -> str:
    try:
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True)
        result = []
        for sheet in wb.worksheets[:3]:  # максимум 3 листа
            result.append(f"=== Лист: {sheet.title} ===")
            for row in sheet.iter_rows(max_row=100, values_only=True):
                row_text = "\t".join(str(c) if c is not None else "" for c in row)
                if row_text.strip():
                    result.append(row_text)
        return "\n".join(result)
    except ImportError:
        return "[XLSX: нужна библиотека openpyxl]"
    except Exception as e:
        return f"[Ошибка чтения XLSX: {e}]"
